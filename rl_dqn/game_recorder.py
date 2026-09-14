"""
game_recorder.py — 真实对局推理的对局记录器。

把整局游戏以 JSONL（每行一个 JSON 对象）落到 runs/ 目录，供出问题时复现/排查：

  setup      开局信息：随机种子（game.rng 与全局 random 同种子）、双方式神、卡组
  step       每次 game.step（模型动作 / 对手动作 / 引擎内部动作），含：
             - 完整状态快照 state_before（双方血量/鬼火/鼓舞/手牌/牌库序/式神面板/
               关键字/计数器/监听器 tag 等）
             - 结构化动作 action（类型、卡牌及其所在区域、式神、目标等）
             - 异常时 step_error（含完整 traceback）后原样重抛
  event      每次 game.broadcast 的事件流（引擎唯一广播咽喉点，handle_event
             首步也经它；deal damage / heal / inspire / ... 按类型提取关键字段）。
             在广播完成后落账：监听器对 event 的原地修改（如觉醒鼓舞 +1/+1）
             已生效，记录的是引擎实际使用的最终值。in_step 指向所属 step 的
             begin 序号（嵌套广播先记内层后记外层）。
  note       step 之外的状态改动与上下文：初始手牌、手牌覆写、对手卡牌注入、
             模型决策（action_id/Q 值）、先后手判定等
  log / ask  bridge.log 的 GUI 日志与 bridge.ask 的用户输入（提问+回答）

复现方式：同 seed 下重放 setup + step 动作序列，并按 ask 记录回放所有
用户输入（真实对局中每回合抽牌由用户报牌名，InferencePlayer.draw 每次抽牌
都会经 bridge.ask 询问，这些答案是复现输入的一部分，不只是诊断信息）；
event/note/log 用于定位真实对局与数字对局的漂移点。

用法（见 inference_full_game_gui_base.game_loop）：
    rec = GameRecorder()
    rec.hook_bridge(bridge)          # 尽早调用，捕获开局全部输入
    ...
    rec.bind(game, player1, player2)
    rec.record_setup(seed=seed, deck=DECK, ...)
    rec.attach()                     # 包装 game.step / game.broadcast
    ...                              # 对局中可 rec.note("xxx", ...) 补充记录
    rec.close()
"""
from __future__ import annotations

import json
import os
import random
import threading
import time
import traceback
from typing import Optional

# 项目根目录（rl_dqn/ 的上一级）；runs/ 默认落在这里
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _KwargEvent:
    """裸字段广播（无 event 对象，如 broadcast("begin turn", next_player=...)）
    的轻量垫片，供 _event_info 按统一接口提取字段。"""
    def __init__(self, event_type, kwargs):
        self.type = event_type
        for k, v in kwargs.items():
            setattr(self, k, v)


class GameRecorder:
    """对局记录器：包装引擎入口与 GUI 桥，把对局全程写入 runs/*.jsonl。"""

    def __init__(self, runs_dir: Optional[str] = None):
        self.runs_dir = runs_dir or os.path.join(_ROOT, "runs")
        os.makedirs(self.runs_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(self.runs_dir, f"run_{stamp}.jsonl")
        n = 1
        while os.path.exists(self.path):
            n += 1
            self.path = os.path.join(self.runs_dir, f"run_{stamp}_{n}.jsonl")
        self._fh = open(self.path, "w", encoding="utf-8")

        self._seq = 0
        self._lock = threading.Lock()
        self._closed = False

        self.game = None            # bind() 后可用
        self.model_player = None    # 模型操控的 Player（推理方）
        self.opp_player = None      # 对手 Player

        self._orig_step = None      # 被包装的原 engine 方法
        self._orig_broadcast = None
        self._orig_ask = None       # 被包装的原 bridge 方法
        self._orig_log = None
        self._step_stack: list[int] = []   # 活跃 step 的 begin 序号栈（step 可嵌套）

    # ── 绑定 ────────────────────────────────────────────────────────────────

    def bind(self, game, model_player, opp_player) -> None:
        """绑定对局与双方玩家（model_player 用于区分 model/opponent 视角）。"""
        self.game = game
        self.model_player = model_player
        self.opp_player = opp_player

    # ── 写入 ────────────────────────────────────────────────────────────────

    def _write(self, entry: dict) -> None:
        with self._lock:
            if self._closed:
                return
            self._seq += 1
            entry["seq"] = self._seq
            entry["ts"] = round(time.time(), 3)
            self._fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()

    def note(self, category: str, with_state: bool = False, **fields) -> None:
        """记录 step 之外的事件；with_state=True 时附带当前完整状态快照。"""
        entry = {"t": "note", "category": category, **fields}
        if with_state and self.game is not None:
            entry["state"] = self._snapshot()
        self._write(entry)

    def close(self) -> None:
        """写入结束记录（含终局快照）并关闭文件。重复调用安全。"""
        with self._lock:
            if self._closed:
                return
        if self.game is not None:
            self._write({"t": "end", "final_state": self._snapshot()})
        with self._lock:
            self._closed = True
            try:
                self._fh.close()
            except Exception:
                pass

    # ── GUI 桥挂钩（尽早调用，覆盖开局输入）─────────────────────────────────

    def hook_bridge(self, bridge) -> None:
        """包装 bridge.ask / bridge.log：记录所有用户输入与 GUI 日志。

        ask 记录 (prompt, answer)；log 记录 (level, msg)。后续代码再包装
        bridge.ask（如英雄自动作答）时链条保持：上层短路时不经记录（其结果
        会经 record_setup / note 单独落账）。
        """
        rec = self
        self._orig_ask = bridge.ask

        def logged_ask(prompt: str = "") -> str:
            answer = rec._orig_ask(prompt)
            rec._write({"t": "ask", "prompt": str(prompt), "answer": str(answer)})
            return answer

        bridge.ask = logged_ask

        self._orig_log = bridge.log

        def logged_log(msg, level="sys"):
            rec._write({"t": "log", "level": str(level), "msg": str(msg)})
            return rec._orig_log(msg, level)

        bridge.log = logged_log

    # ── 引擎挂钩 ────────────────────────────────────────────────────────────

    def attach(self) -> None:
        """包装 game.step / game.broadcast（引擎事件唯一咽喉点）。

        须在 bind() 之后调用。包装的是实例属性，引擎内部 self.step /
        self.broadcast 的递归调用同样被捕获。
        """
        g = self.game
        rec = self
        self._orig_step = g.step
        self._orig_broadcast = g.broadcast

        def logged_step(player, action, *args, **kwargs):
            begin_seq = rec._seq + 1
            rec._write({
                "t": "step", "phase": "begin",
                "actor": rec._side(player),
                "seat": rec._seat(player),
                "turn": getattr(g, "turn_count", None),
                "action": rec._serialize_action(action),
                "state_before": rec._snapshot(),
            })
            rec._step_stack.append(begin_seq)
            try:
                result = rec._orig_step(player, action, *args, **kwargs)
            except BaseException:
                rec._write({"t": "step_error", "begin_seq": begin_seq,
                            "error": traceback.format_exc()})
                rec._step_stack.pop()
                raise
            rec._step_stack.pop()
            rec._write({"t": "step", "phase": "end", "begin_seq": begin_seq})
            return result

        def logged_broadcast(event_type, *args, **kwargs):
            orig_evt = kwargs.get("event")
            try:
                result = rec._orig_broadcast(event_type, *args, **kwargs)
            except BaseException:
                rec._write({"t": "event_error", "type": event_type,
                            "error": traceback.format_exc()})
                raise
            # 广播完成后落账：监听器对 event 的原地修改（如觉醒鼓舞 +1/+1）
            # 已生效，记录的是引擎实际使用的最终值
            obj = orig_evt if orig_evt is not None else _KwargEvent(event_type, kwargs)
            rec._write({
                "t": "event",
                "type": event_type,
                "in_step": rec._step_stack[-1] if rec._step_stack else None,
                "info": rec._event_info(obj),
            })
            return result

        g.step = logged_step
        g.broadcast = logged_broadcast

    # ── 开局记录 ────────────────────────────────────────────────────────────

    def record_setup(self, *, seed: int, deck, player_heroes, opponent_heroes,
                     extra: Optional[dict] = None) -> None:
        """记录开局信息。seed 同时用于 game.rng（Game(seed=...)）与全局 random。"""
        self._write({
            "t": "setup",
            "seed": seed,
            "seeded": ["Game.rng", "random module (CardList.shuffle 等)"],
            "deck": list(deck),
            "player_heroes": list(player_heroes),
            "opponent_heroes": list(opponent_heroes),
            **(extra or {}),
        })

    # ── 视角辅助 ────────────────────────────────────────────────────────────

    def _side(self, entity) -> str:
        if entity is self.model_player:
            return "model"
        if entity is self.opp_player:
            return "opponent"
        return f"?{type(entity).__name__}"

    def _seat(self, entity) -> Optional[str]:
        if self.game is None:
            return None
        if entity is self.game.player1:
            return "first"
        if entity is self.game.player2:
            return "second"
        return None

    # ── 实体序列化 ──────────────────────────────────────────────────────────

    def _card_info(self, c) -> dict:
        d = {
            "n": getattr(c, "eng_name", None),
            "id": getattr(c, "id", None),
            "lv": getattr(c, "level_req", None),
            "attrs": [a.name for a in getattr(c, "attributes", []) if hasattr(a, "name")],
        }
        ba, bd = getattr(c, "buff_atk", 0), getattr(c, "buff_def", 0)
        if ba or bd:
            d["buff"] = [ba, bd]
        pb = getattr(c, "played_by", None)
        if pb is not None:
            d["played_by"] = getattr(pb, "type_name", None)
        return d

    def _hero_info(self, h) -> dict:
        return {
            "n": getattr(h, "type_name", None),
            "lv": getattr(h, "level", None),
            "hp": getattr(h, "hp", None),
            "max": getattr(h, "current_max_hp", None),
            "atk": getattr(h, "atk", None),
            "def": getattr(h, "defense", None),
            "insp": getattr(h, "inspiration_atk", None),
            "pen": getattr(h, "penetration", None),
            "state": getattr(h, "state", None),
            "alive": getattr(h, "is_alive", None),
            "stunned": getattr(h, "stunned", None),
            "awakened": getattr(h, "is_awakened", None),
            "summoned": getattr(h, "is_summoned", None),
            "form": getattr(h, "form", None),
            "morphed_id": getattr(h, "morphed_id", None),
            "countdown": getattr(h, "countdown", None),
            "countdown_max": getattr(h, "countdown_max", None),
            "revive_in": getattr(h, "round_until_alive", None),
            "attrs": [a.name for a in getattr(h, "attributes", []) if hasattr(a, "name")],
            "counters": dict(getattr(getattr(h, "counters", None), "_values", {}) or {}),
            "charging": getattr(getattr(h, "charging_card", None), "eng_name", None),
            "listeners": [getattr(l, "_tag", None) or getattr(l, "event_type", "?")
                          for l in getattr(h, "listeners", [])],
        }

    def _player_info(self, p) -> dict:
        hand = getattr(p, "hand", None)
        deck = getattr(p, "deck", None)
        used = getattr(p, "used_card", None)
        az = getattr(p, "attack_zone", None)
        la = getattr(p, "last_attacking_hero", None)
        return {
            "hp": getattr(p, "hp", None),
            "max": getattr(p, "current_max_hp", None),
            "def": getattr(p, "defense", None),
            "pen": getattr(p, "penetration", None),
            "fire": getattr(p, "fire_cnt", None),
            "atk_ok": getattr(p, "attack_available", None),
            "instant_used": getattr(p, "instant_used", None),
            "upgrade_left": getattr(p, "upgrade_remaining", None),
            "state": getattr(getattr(p, "state", None), "name", getattr(p, "state", None)),
            "insp": [getattr(p, "inspiration_atk", None), getattr(p, "inspiration_def", None)],
            "hand": [self._card_info(c) for c in (hand or [])],
            "deck": [self._card_info(c) for c in (deck or [])],
            "used": [getattr(c, "eng_name", None) for c in (used or [])],
            "attack_zone": getattr(az, "type_name", None),
            "last_attacker": getattr(la, "type_name", None),
            "charging_order": [getattr(h, "type_name", None)
                               for h in getattr(p, "charging_order", [])],
            "counters": dict(getattr(getattr(p, "counters", None), "_values", {}) or {}),
            "listeners": [getattr(l, "_tag", None) or getattr(l, "event_type", "?")
                          for l in getattr(p, "listeners", [])],
            "heroes": [self._hero_info(h) for h in getattr(p, "heroes", [])],
        }

    def _snapshot(self) -> dict:
        """完整对局状态快照（step 前与关键时刻落账）。"""
        g = self.game
        snap = {
            "turn": getattr(g, "turn_count", None),
            "current": self._side(g.current_player) if g is not None else None,
            "model": self._player_info(self.model_player),
            "opponent": self._player_info(self.opp_player),
            "game_counters": dict(getattr(getattr(g, "counters", None), "_values", {}) or {}),
        }
        lds = getattr(g, "_last_damage_source", None)
        if lds is not None:
            snap["last_damage_source"] = getattr(lds, "type_name", None)
        return snap

    def _locate(self, card) -> Optional[str]:
        """卡牌实例当前位置（model/opponent 的 hand[i]/deck[i]/used[i]）。"""
        for side, p in (("model", self.model_player), ("opponent", self.opp_player)):
            for zone in ("hand", "deck", "used_card"):
                cards = getattr(p, zone, None)
                if cards is None:
                    continue
                for i, c in enumerate(cards):
                    if c is card:
                        return f"{side}:{zone}[{i}]"
        return None

    def _describe(self, v):
        """把任意引擎对象转成 JSON 友好的简述。"""
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, (list, tuple)):
            return [self._describe(x) for x in v]
        if hasattr(v, "name") and not isinstance(v, type):   # 枚举
            return v.name
        if getattr(v, "entity_type", None) == "player":
            return self._side(v)
        if hasattr(v, "type_name") and hasattr(v, "hp"):     # Hero
            return f"{v.type_name}(lv{getattr(v, 'level', '?')})"
        if hasattr(v, "eng_name"):                            # Card
            return v.eng_name
        return str(v)

    def _serialize_action(self, action) -> Optional[dict]:
        if action is None:
            return None
        d = {"type": getattr(action, "type", type(action).__name__)}
        card = getattr(action, "card", None)
        if card is not None:
            d["card"] = self._card_info(card)
            loc = self._locate(card)
            if loc:
                d["card"]["loc"] = loc
        hero = getattr(action, "hero", None)
        if hero is not None:
            d["hero"] = getattr(hero, "type_name", None)
        if hasattr(action, "target"):
            d["target"] = self._describe(getattr(action, "target"))
        for f in ("use_blast", "use_charge", "option_index"):
            v = getattr(action, f, None)
            if v is not None:
                d[f] = v
        return d

    # ── 事件字段提取 ────────────────────────────────────────────────────────

    def _event_info(self, event) -> dict:
        t = getattr(event, "type", None)
        info: dict = {}
        if t == "deal damage":
            info = {"v": getattr(event, "value", None),
                    "src": self._describe(getattr(event, "source", None)),
                    "tgt": self._describe(getattr(event, "target", None)),
                    "dtype": getattr(event, "damage_type", None)}
        elif t == "heal":
            info = {"v": getattr(event, "value", None),
                    "src": self._describe(getattr(event, "source", None)),
                    "tgt": self._describe(getattr(event, "target", None))}
        elif t == "give buff":
            info = {"attr": getattr(event, "attr", None),
                    "v": getattr(event, "value", None),
                    "tgt": self._describe(getattr(event, "target", None))}
        elif t == "play card":
            card = getattr(event, "card", None)
            info = {"card": getattr(card, "eng_name", None),
                    "owner": self._side(getattr(card, "owner", None))}
        elif t in ("hero attack",):
            info = {"hero": getattr(getattr(event, "hero", None), "type_name", None)}
            card = getattr(event, "card", None)
            if card is not None:
                info["card"] = getattr(card, "eng_name", None)
            tgt = getattr(event, "target", None)
            if tgt is not None:
                info["target"] = self._describe(tgt)
        elif t == "inspire":
            info = {"atk": getattr(event, "atk", None),
                    "def": getattr(event, "defense", None),
                    "hero": getattr(getattr(event, "hero", None), "type_name", None)}
        elif t in ("revive", "after revive"):
            info = {"tgt": self._describe(getattr(event, "target", None))}
        elif t == "hero kill":
            info = {"killer": self._describe(getattr(event, "killer", None)),
                    "killed": getattr(getattr(event, "killed", None), "type_name", None)}
        elif t in ("fortune roll", "fortune success"):
            info = {"result": getattr(event, "result", None),
                    "threshold": getattr(event, "threshold", None),
                    "hero": getattr(getattr(event, "source_hero", None), "type_name", None)}
        elif t == "begin turn":
            info = {"next": self._describe(getattr(event, "next_player", None))}
        elif t == "end turn":
            info = {"player": self._describe(getattr(event, "player", None))}
        elif t in ("draw selected card from deck", "move", "countdown", "projectile",
                   "stun", "unstun", "permanent death", "summon", "entities attack",
                   "illusion played", "illusion destroyed", "illusion damage",
                   "illusion durability gain", "cook", "energy gain", "energy spend",
                   "armor break applied", "about to die", "morph leave"):
            info = {}   # 低信息量事件只留类型
        else:
            # 兜底：把事件/垫片的字段尽量转成简述（比 repr 更可读）
            try:
                raw = vars(event)
            except TypeError:
                raw = {}
            info = {k: self._describe(v) for k, v in list(raw.items())[:12]
                    if k != "type"} or {"repr": str(event)[:200]}
        return info


def new_seed() -> int:
    """生成一局的新种子（记录后可完整复现）。"""
    return random.randrange(2 ** 32)