"""食灵 专属卡牌（cards 238-245）

现场烹饪 / 开锅 / 梦想料理 / 觉醒·食灵 / 热血主厨 /
快速烹饪 / 热浪 / 食神

数据来源：cards.json + tmp_cards_json/ShiLing.json（描述逐字拷贝）。
引擎缺失/语义无法核实的机制一律标注 TODO（需引擎支持，等审批）。
"""
import sys
sys.path.insert(0, "E:/more_random_project_vibe")
from game_core.action import *
from game_core.event import *
from game_core.enums import *
from game_core.manager import Listener
from game_core.selector import *


# ── 通用工具 ────────────────────────────────────────────────────────────────

def _count_hand_jiaoyao(player):
    """手牌中「佳肴」的数量。"""
    return sum(1 for c in player.hand.cards if getattr(c, "eng_name", "") == "JiaYao")


def _enemy_heroes(player):
    """敌方存活且已升级的式神（无帷幕）。"""
    return [h for h in player.opponent.heroes
            if h.is_alive and h.level > 0 and HeroAttributes.VEIL not in h.attributes]


# ── 佳肴获得跟踪（本局累计 + 实时回调） ─────────────────────────────────────
# 与 YiXiGong 的跟踪逻辑相同，属性前缀 _sll_ 区分（两个式神同队时可并存）。
# 热浪增强需要「本局获得了 X 张佳肴」；梦想料理/觉醒·食灵需要「获得佳肴时」回调。

def _install_sll_tracker(player, on_gain=None):
    """在牌手层安装「获得佳肴」跟踪（幂等，tag 去重）。详见 YiXiGong._install_yxg_tracker。"""
    tag = "sll_jiaoyao_tracker"
    if getattr(player, "_sll_tracker_installed", False):
        if on_gain is not None and on_gain not in getattr(player, "_sll_jiaoyao_callbacks", []):
            player._sll_jiaoyao_callbacks.append(on_gain)
        return
    player._sll_tracker_installed = True
    player._sll_jiaoyao_total = 0
    player._sll_jiaoyao_baseline = _count_hand_jiaoyao(player)
    player._sll_jiaoyao_callbacks = []
    if on_gain is not None:
        player._sll_jiaoyao_callbacks.append(on_gain)
    l_cook = Listener("cook", lambda e, p: e.event.player == p, (_on_sll_cook,))
    l_cook._tag = tag
    l_play = Listener("play card", _sll_play_cond, (_on_sll_play,), phase="after")
    l_play._tag = tag
    player.listeners += [l_cook, l_play]


def _sll_play_cond(e, p):
    c = getattr(e.event, "card", None)
    return c is not None and c.owner is p and getattr(c, "eng_name", "") == "JiaYao"


def _on_sll_cook(e, p):
    now = _count_hand_jiaoyao(p)
    gained = now - p._sll_jiaoyao_baseline
    if gained > 0:
        p._sll_jiaoyao_total += gained
        for cb in list(getattr(p, "_sll_jiaoyao_callbacks", [])):
            cb(gained, p)
    p._sll_jiaoyao_baseline = now


def _on_sll_play(e, p):
    p._sll_jiaoyao_baseline = max(0, p._sll_jiaoyao_baseline - 1)


def _sll_jiaoyao_gained(player):
    """本局累计获得「佳肴」张数（未安装跟踪时返回 0）。"""
    return getattr(player, "_sll_jiaoyao_total", 0)


# ── 1勾卡牌 ─────────────────────────────────────────────────────────────────

class XianChangPengRen:
    """现场烹饪：己方回合结束时若食灵在战斗区，烹饪。"""
    id = 238
    type = "morph"
    hero = "ShiLing"
    name = "现场烹饪"
    level_req = 1
    atk = 2
    hp = 6
    on_play = (lambda s: _xianchang_on_play(s),)


def _xianchang_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "xianchang"]
    l = Listener("begin turn",
                 lambda e, h: (e.next_player != h.owner and h.morphed_id == 238
                               and h.is_alive and h.owner.attack_zone is h),
                 (lambda e, h: h.owner.game.cook(h.owner, h),))
    l._tag = "xianchang"
    hero.listeners.append(l)


class KaiGuo:
    """开锅：烹饪。"""
    id = 239
    type = "attack"
    hero = "ShiLing"
    name = "开锅"
    level_req = 1
    buff_def = 1
    on_play = (lambda s: s.owner.game.cook(s.owner, s.get_corresponding_hero()),)


class MengXiangLiaoLi:
    """梦想料理（幻境）：进场时烹饪。当你获得「佳肴」时，抽一张牌。"""
    id = 240
    type = "illusion"
    hero = "ShiLing"
    name = "梦想料理"
    level_req = 1
    duration = 5
    on_play = (lambda s: _mengxiang_on_play(s),)


def _mengxiang_on_play(s):
    player = s.owner
    # 幻境被破坏后停止触发「获得佳肴抽牌」。
    if not getattr(s, "_mxl_destroyed_installed", False):
        s._mxl_destroyed_installed = True
        tag = f"mxl_destroyed_{id(s)}"
        player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
        l = Listener("illusion destroyed",
                     lambda e, p: getattr(e.event, "card", None) is s,
                     (lambda e, p: setattr(s, "_mxl_destroyed", True),))
        l._tag = tag
        player.listeners.append(l)

    def _draw(gained, p):
        if not getattr(s, "_mxl_destroyed", False):
            p.game.handle_event(DrawEvent(p, 1))

    _install_sll_tracker(player, _draw)
    # 进场时烹饪
    player.game.cook(player, s.get_corresponding_hero())


# ── 2勾卡牌 ─────────────────────────────────────────────────────────────────

class JueXingShiLing:
    """觉醒·食灵：觉醒：每当己方式神烹饪时，食灵获得1力量。每当你获得「佳肴」时，复活食灵。

    「每当己方式神烹饪时食灵+1力量」与基础能力相同（heroes.py 已实现，觉醒不重复叠加），
    觉醒额外提供「获得佳肴时复活食灵」与永久 +1/+1。"""
    id = 241
    type = "spell"
    hero = "ShiLing"
    name = "觉醒·食灵"
    level_req = 2
    on_play = (lambda s: _juexing_shiling_on_play(s),)


def _juexing_shiling_on_play(s):
    hero = s.get_corresponding_hero()
    hero.get_permanent_buff("atk", 1)
    hero.get_permanent_buff("hp", 1)
    hero.is_awakened = True

    def _revive(gained, p):
        sl = next((h for h in p.heroes if h.type_name == "ShiLing"), None)
        if sl is not None and not sl.is_alive:
            p.game.handle_event(Revive(s, [sl]))

    _install_sll_tracker(s.owner, _revive)


class ReXueZhuChu:
    """热血主厨：每当己方式神烹饪时，鼓舞：获得+1力量和+1护甲。"""
    id = 242
    type = "morph"
    hero = "ShiLing"
    name = "热血主厨"
    level_req = 2
    atk = 5
    hp = 7
    on_play = (lambda s: _rexue_on_play(s),)


def _rexue_on_play(s):
    hero = s.get_corresponding_hero()
    hero.listeners = [l for l in hero.listeners if getattr(l, "_tag", "") != "rexue"]
    l = Listener("cook",
                 lambda e, h: h.morphed_id == 242 and e.event.player == h.owner,
                 (lambda e, h: _rexue_inspire(h),))
    l._tag = "rexue"
    hero.listeners.append(l)


def _rexue_inspire(h):
    h.owner.inspiration_atk += 1
    h.owner.inspiration_def += 1


class KuaiSuPengRen:
    """快速烹饪：瞬发，弹回，烹饪。

    弹回（一次性，wiki 关键字-弹回）：使用后回手并失去此能力，再次使用进弃牌堆。
    """
    id = 243
    type = "spell"
    hero = "ShiLing"
    name = "快速烹饪"
    level_req = 2
    attributes = (CardAttributes.INSTANT,)
    bounce = True
    on_play = (lambda s: _kuaisu_on_play(s),)


def _kuaisu_on_play(s):
    s.owner.game.cook(s.owner, s.get_corresponding_hero())


# ── 3勾卡牌 ─────────────────────────────────────────────────────────────────

class ReLang:
    """热浪：追猎 增强：本局游戏你每获得一张「佳肴」，此牌便获得+2力量和+2护甲。戏法：追猎。

    戏法·追猎（使用时获得追猎）与基础追猎在引擎中同为「本次攻击带追猎」，
    故只在攻击期间临时附加 HUNTING 词条（毛乱步模式）。
    """
    id = 244
    type = "attack"
    hero = "ShiLing"
    name = "热浪"
    level_req = 3
    buff_atk = 0    # 初始 0，增强按本局佳肴数累加（与正义必胜同模式）
    buff_def = 0
    require_target = (lambda s: _enemy_heroes(s.owner),)
    select_target = (lambda s: select_target(s.owner, _enemy_heroes(s.owner), s),)
    on_play = (lambda s: _relang_on_play(s),)
    after_play = (lambda s: _relang_after(s),)


def _relang_on_play(s):
    hero = s.get_corresponding_hero()
    s._relang_had_hunting = HeroAttributes.HUNTING in hero.attributes
    if not s._relang_had_hunting:
        hero.attributes.append(HeroAttributes.HUNTING)
    _install_sll_tracker(s.owner, None)
    n = _sll_jiaoyao_gained(s.owner)
    s.buff_atk += 2 * n
    s.buff_def += 2 * n


def _relang_after(s):
    hero = s.get_corresponding_hero()
    if not getattr(s, "_relang_had_hunting", True) and HeroAttributes.HUNTING in hero.attributes:
        hero.attributes.remove(HeroAttributes.HUNTING)


class ShiShen:
    """食神：当你对己方式神使用「食材」或「佳肴」时，对所有其他己方式神都额外使用一次。
    每回合一次，你的「食材」和「佳肴」不消耗鬼火。"""
    id = 245
    type = "morph"
    hero = "ShiLing"
    name = "食神"
    level_req = 3
    atk = 6
    hp = 7
    on_play = (lambda s: _shishen_on_play(s),)


def _shishen_on_play(s):
    player = s.owner
    _wrap_all_food(player)
    # 烹饪产生的新食材/佳肴也包装（食神离场后包装仍在，但包装体按 morphed_id 判定失效）
    tag = "shishen_wrap"
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag]
    l = Listener("cook", lambda e, p: e.event.player == p, (_shishen_wrap_cook,))
    l._tag = tag
    player.listeners.append(l)
    # 每回合一次：食材/佳肴不消耗鬼火（以返还鬼火近似；代价：仍需先持有 1 鬼火才能打出）
    tag2 = "shishen_refund"
    player.listeners = [l for l in player.listeners if getattr(l, "_tag", "") != tag2]
    l2 = Listener("play card", _shishen_refund_cond, (_shishen_refund,), phase="after")
    l2._tag = tag2
    player.listeners.append(l2)


def _wrap_all_food(player):
    for c in player.hand.cards:
        if getattr(c, "is_ingredient", False) or getattr(c, "eng_name", "") == "JiaYao":
            _wrap_food_card(c)


def _shishen_wrap_cook(e, p):
    _wrap_all_food(p)


def _wrap_food_card(card):
    """把食材/佳肴的 on_play 包装：食神在场时，对其余己方式神也额外使用一次。"""
    if getattr(card, "_shishen_wrapped", False):
        return
    card._shishen_wrapped = True
    orig = card.on_play
    if not orig:
        return
    cbs = tuple(orig) if isinstance(orig, tuple) else (orig,)

    def wrapped(s):
        owner = s.owner
        game = owner.game
        # 原效果（作用于所选目标）
        for cb in cbs:
            r = cb(s)
            if isinstance(r, Event):
                game.handle_event(r)
        # 食神在场：对所有其他己方式神额外使用一次
        shiling = next((h for h in owner.heroes if h.type_name == "ShiLing"), None)
        if shiling is None or not shiling.is_alive or shiling.morphed_id != 245:
            return
        sel = owner.selected_targets or []
        others = [h for h in owner.heroes if h.is_alive and h not in sel]
        if not others:
            return
        prev = owner.selected_targets
        owner.selected_targets = others
        try:
            for cb in cbs:
                r = cb(s)
                if isinstance(r, Event):
                    game.handle_event(r)
        finally:
            owner.selected_targets = prev

    card.on_play = (wrapped,)


def _shishen_refund_cond(e, p):
    c = getattr(e.event, "card", None)
    if c is None or c.owner is not p:
        return False
    if not (getattr(c, "is_ingredient", False) or getattr(c, "eng_name", "") == "JiaYao"):
        return False
    shiling = next((h for h in p.heroes if h.type_name == "ShiLing"), None)
    if shiling is None or not shiling.is_alive or shiling.morphed_id != 245:
        return False
    return True


def _shishen_refund(e, p):
    turn = getattr(p.game, "turn_count", 0)
    if getattr(p, "_shishen_refund_turn", -1) == turn:
        return
    p._shishen_refund_turn = turn
    p.fire_cnt += 1
