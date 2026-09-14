import json
import sys
sys.path.insert(0, "E:/more_random_project_vibe")

from game_core.game import Game
from game_core.player import Player
from game_core.card import Card
from game_core import heroes as hero_defs
from rl.actor_critic import ActorCritic
from rl_dqn.agent import DoubleDQNAgent
from .actions import *
from game_core.action import *
import itertools
import torch
import numpy as np
import os
import random as r

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ═══════════════════════════════════════════════════════════════════════════════
#  模块级 helper — 式神块写入 numpy buffer
# ═══════════════════════════════════════════════════════════════════════════════

def _fill_hero_block_np(buf: np.ndarray, base: int, hero) -> None:
    """将一个式神的状态写入 numpy buffer[base : base+HERO_BLOCK] (29 维)。"""
    hf = HeroField

    buf[base + hf.ID]                = hero.id
    buf[base + hf.MORPHED_ID]        = hero.morphed_id
    buf[base + hf.CURRENT_MAX_HP]    = hero.current_max_hp
    buf[base + hf.HP]                = hero.hp
    buf[base + hf.ATK]               = hero.atk
    buf[base + hf.ROUND_BUFF_ATK]    = hero.round_buff_atk
    buf[base + hf.DEFENSE]           = hero.defense
    buf[base + hf.LEVEL]             = hero.level
    buf[base + hf.ROUND_UNTIL_ALIVE] = hero.round_until_alive

    # position_state: 0=准备区 1=战斗区 2=气绝
    state = hero.state
    if state == "attacking":
        buf[base + hf.POSITION_STATE] = 1.0
    elif state == "dead":
        buf[base + hf.POSITION_STATE] = 2.0
    else:
        buf[base + hf.POSITION_STATE] = 0.0

    buf[base + hf.IS_STUNNED]  = 1.0 if hero.stunned else 0.0
    buf[base + hf.IS_AWAKENED] = 1.0 if hero.is_awakened else 0.0

    # countdown_ratio
    if hero.countdown_max > 0:
        buf[base + hf.COUNTDOWN_RATIO] = hero.countdown / hero.countdown_max
    else:
        buf[base + hf.COUNTDOWN_RATIO] = 0.0

    # 全部 16 个 HeroAttributes — 枚举值 1~16 → ATTR_START + (val-1)
    for attr in hero.attributes:
        attr_val = int(attr)
        if 1 <= attr_val <= 16:
            buf[base + hf.ATTR_START + attr_val - 1] = 1.0


class Env:
    def __init__(self):
        root_dict = "E:/more_random_project_vibe"
        with open(os.path.join(root_dict, "game_core/cards/cards.json"), 'r', encoding='utf-8') as file:
            self.card_data = json.load(file)
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            self.hero_names = [line.strip() for line in file if line.strip()]
        self._precompute_deck_tables()

    # ═════════════════════════════════════════════════════════════════════════
    #  阵容/卡组随机构筑（DQNRandomDeckGameEnv 使用；协战构筑规则见 faq.md）
    # ═════════════════════════════════════════════════════════════════════════

    def _precompute_deck_tables(self):
        """预计算随机构筑所需的静态表（一次性，reset 时只做采样）。

        - 候选式神：id=16 与 id>=31 的式神卡牌尚未备齐，暂不入选（放开时只改这里）；
        - 基础牌池：式神的起始牌（非 PLACEHOLDER/token）+ 伙伴不可上场的协战牌
          （后者对阵容而言就是普通卡）；
        - 合法阵容：4 式神且派系 ≤2 的全部组合，reset 时 r.choice——与拒绝采样
          同分布，但零拒绝成本。
        """
        selectable = {}
        for name in self.hero_names:
            cls = getattr(hero_defs, name, None)
            hid = getattr(cls, "id", None)
            if hid is not None and hid != 16 and hid < 31:
                selectable[name] = getattr(cls, "type", None)

        def _is_deck_card(c):
            return (c.get("is_beginning_card") and c["type"] != "PLACEHOLDER"
                    and not c.get("is_token"))

        # 协战牌：heroes 字段列出两名协战式神
        coop_cards = [c for c in self.card_data
                      if len(c.get("heroes", [])) > 1 and _is_deck_card(c)]

        self.hero_factions = dict(selectable)
        self.base_pools = {}
        for name in selectable:
            # 协战牌（heroes 列出多名式神）不进个人基础池：按预算路径入池，
            # 避免与 hero 字段归属重复计数
            own = [c["eng_name"] for c in self.card_data
                   if c["hero"] == name and _is_deck_card(c)
                   and len(c.get("heroes", [])) <= 1]
            # 伙伴不可上场 → 协战牌当普通卡并入池
            extra = [c["eng_name"] for c in coop_cards
                     if name in c["heroes"]
                     and not any(h in selectable for h in c["heroes"] if h != name)]
            self.base_pools[name] = own + extra

        # 牌池抽 8 张且同种卡 ≤2 → 每式神至少 4 张不同卡才能凑满
        self.allowed_heroes = [n for n in selectable if len(self.base_pools[n]) >= 4]
        if not self.allowed_heroes:
            raise ValueError("no selectable hero has enough deck cards")

        # 双方可上场的协战牌 → 共享「整个阵容最多 2 张」预算（faq.md）
        self.shared_coop = {c["eng_name"]: tuple(c["heroes"]) for c in coop_cards
                            if all(h in selectable for h in c["heroes"])}
        self.hero_shared_coop = {n: [] for n in self.allowed_heroes}
        for card_name, (ha, hb) in self.shared_coop.items():
            self.hero_shared_coop[ha].append(card_name)
            self.hero_shared_coop[hb].append(card_name)

        self.valid_lineups = [
            combo for combo in itertools.combinations(self.allowed_heroes, 4)
            if len({self.hero_factions[h] for h in combo}) <= 2
        ]
        if not self.valid_lineups:
            raise ValueError("no valid lineup satisfies the 2-faction constraint")

    def _build_deck(self, hero_names):
        """为阵容构筑 4×8=32 张卡组，返回卡牌 eng_name 列表。

        - 洗牌决定抽卡顺序：共享协战牌的预算属于先抽的一方，洗牌消除固定顺序
          的位置偏差（卡组内牌序不影响对局）；
        - 每个式神从「牌池×2」中不放回抽 8 张，天然保证同种卡 ≤2 张；
        - 双方都在阵容的协战牌：先抽方按普通卡处理（2 份入池），记账已用张数，
          后抽方只把剩余预算份数入池——阵容合计 ≤2，无需裁剪。
        """
        names = list(hero_names)
        r.shuffle(names)
        in_lineup = set(names)
        drawn = set()
        coop_left = {}   # 共享协战牌名 -> 先抽方用后剩余的可分配张数
        deck = []
        for name in names:
            pool = self.base_pools[name] * 2
            for card_name in self.hero_shared_coop[name]:
                ha, hb = self.shared_coop[card_name]
                other = hb if name == ha else ha
                if other in in_lineup and other in drawn:
                    pool.extend([card_name] * coop_left.get(card_name, 0))
                else:
                    # 仅己方在阵容，或己方先抽：整份预算（2 份）入池
                    pool.extend([card_name] * 2)
            if len(pool) < 8:
                raise ValueError(f"hero {name} has too few deck cards: {len(pool)}")
            picks = r.sample(pool, 8)
            deck.extend(picks)
            drawn.add(name)
            for card_name in self.hero_shared_coop[name]:
                ha, hb = self.shared_coop[card_name]
                other = hb if name == ha else ha
                if other in in_lineup and other not in drawn:
                    coop_left[card_name] = 2 - picks.count(card_name)
        return deck


    def step(self, action):
        raise NotImplementedError


    def reset(self):
        raise NotImplementedError


    def get_obs(self, player) -> torch.Tensor:
        """构建 709 维 observation tensor (numpy CPU → 最后一次性转 GPU)。"""
        o = ObsIdx
        opponent = player.opponent
        game = self.game
        buf = np.zeros(OBS_DIM, dtype=np.float32)

        # ── 基础标量 (5) ──────────────────────────────────────────────
        buf[o.PLAYER_STATE] = player.state
        buf[o.GAME_STATE]   = 0
        buf[o.TURN_COUNT]   = game.turn_count
        buf[o.PLAYER_HP]    = player.hp
        buf[o.OPPONENT_HP]  = opponent.hp

        # ── 己方式神 (4 × 29) ─────────────────────────────────────────
        # 召唤物会作为额外式神加入 heroes，obs 槽位固定为 NUM_HEROES，截断避免越界写入
        for i, h in enumerate(player.heroes[:NUM_HEROES]):
            _fill_hero_block_np(buf, o.PLAYER_HERO_START + i * HERO_BLOCK, h)

        # ── 对手式神 (4 × 29) ─────────────────────────────────────────
        for i, h in enumerate(opponent.heroes[:NUM_HEROES]):
            _fill_hero_block_np(buf, o.OPP_HERO_START + i * HERO_BLOCK, h)

        # ── 牌手标量 (14) ─────────────────────────────────────────────
        buf[o.PLAYER_DECK]        = len(player.deck)
        buf[o.OPPONENT_DECK]      = len(opponent.deck)
        buf[o.OPPONENT_HAND_SIZE] = len(opponent.hand)
        buf[o.FIRE_REMAINING]     = player.fire_cnt
        buf[o.ATTACK_AVAILABLE]   = 1.0 if player.attack_available else 0.0
        buf[o.IS_FIRST_PLAYER]    = 1.0 if player.is_first_player   else 0.0
        buf[o.PENDING_CARD]       = player.pending_card.id if player.pending_card is not None else 0.0
        buf[o.PLAYER_INSP_ATK]    = player.inspiration_atk
        buf[o.PLAYER_INSP_DEF]    = player.inspiration_def
        buf[o.PLAYER_DEFENSE]     = player.defense
        buf[o.OPPONENT_DEFENSE]   = opponent.defense
        buf[o.UPGRADE_REMAINING]  = player.upgrade_remaining
        buf[o.INSTANT_USED]       = 1.0 if player.instant_used else 0.0
        buf[o.OPPONENT_FIRE]      = opponent.fire_cnt

        # ── 手牌 multi-hot (100) ──────────────────────────────────────
        for c in player.hand.cards:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.PLAYER_HAND_START + cid - 1] += 1.0

        # ── 起始牌组 multi-hot (100) ──────────────────────────────────
        for name in player.starting_deck:
            cid = Card.get_id_by_name(name)
            if cid == 0:
                try:
                    cid = Card.GetCard(name).id
                except Exception:
                    cid = 0
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.STARTING_DECK_START + cid - 1] += 1.0

        # ── 己方已用牌 multi-hot (100) ────────────────────────────────
        for c in player.used_card:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.PLAYER_USED_START + cid - 1] += 1.0

        # ── 对手已用牌 multi-hot (100) ────────────────────────────────
        for c in opponent.used_card:
            cid = Card.get_id_by_name(c.eng_name) if hasattr(c, 'eng_name') else c.id
            if cid == 0:
                cid = c.id
            if 1 <= cid <= MAX_CARD_ID:
                buf[o.OPP_USED_START + cid - 1] += 1.0

        # ── 正在攻击的己方式神 (29) ───────────────────────────────────
        for h in player.heroes:
            if h.state == "attacking":
                _fill_hero_block_np(buf, o.PLAYER_ATTACKING_START, h)
                break

        # ── 正在攻击的对手式神 (29) ───────────────────────────────────
        for h in opponent.heroes:
            if h.state == "attacking":
                _fill_hero_block_np(buf, o.OPP_ATTACKING_START, h)
                break

        return torch.from_numpy(buf).to(device=_DEVICE, dtype=torch.float32)


    def get_legal_actions(self, player):
        """合法动作ID列表（卡牌ID编码）——委托 env.actions.get_legal_action_ids。"""
        return get_legal_action_ids(player)


    def get_action_masks(self, player) -> torch.Tensor:
        """反向掩码（True=非法）——委托 env.actions.build_action_mask。"""
        return build_action_mask(player, _DEVICE)


    def decode_action(self, player, action_id):
        """动作ID → 引擎 Action（可能为 None）——委托 env.actions.decode_action。"""
        return decode_action(player, action_id)


    def get_reward(self, obs_before: torch.Tensor, obs_after: torch.Tensor) -> float:
        o = ObsIdx
        reward = 0.0

        if obs_after[o.PLAYER_STATE] == 5:
            reward -= 50.0
        if obs_after[o.OPPONENT_HP] <= 0 or obs_after[o.OPPONENT_DECK] <= 0:
            reward += 50.0

        reward += float(obs_after[o.PLAYER_HP]  - obs_before[o.PLAYER_HP])  * 0.8
        reward += float(obs_before[o.OPPONENT_HP] - obs_after[o.OPPONENT_HP]) * 1.5

        reward += float(obs_before[o.FIRE_REMAINING] - obs_after[o.FIRE_REMAINING]) * 0.6

        if obs_before[o.PLAYER_STATE] == 2:
            for hp_idx, def_idx in zip(OPP_HERO_HP, OPP_HERO_DEF):
                reward += 1.0 * float(
                    (obs_before[hp_idx]  - obs_after[hp_idx]) +
                    (obs_before[def_idx] - obs_after[def_idx])
                )

        hand_after = obs_after[o.PLAYER_HAND_START : o.PLAYER_HAND_START + MAX_CARD_ID]
        hand_size  = int(hand_after.sum())
        if hand_size > HAND_LIMIT:
            reward -= 2.5 * (hand_size - HAND_LIMIT)

        turn_changed   = obs_after[o.TURN_COUNT] != obs_before[o.TURN_COUNT]
        not_init_state = obs_before[o.PLAYER_STATE] != 1
        fire_was_full  = obs_before[o.FIRE_REMAINING] == 2
        if not_init_state and turn_changed and fire_was_full:
            reward -= 2.0

        return reward


class RandomOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = ActorCritic(OBS_DIM, 36).to(device="cuda")
        self.model.load_state_dict(torch.load("./logs/dqn/2026-03-17_14-34-54/dqn_model.pt"))


    def step(self, action):
        original_state = self.game.get_observations(self.player1)
        decoded = self.decode_action(self.player1, action)
        if decoded is None:
            return self.get_obs(self.player1), 0, False, {}
        self.game.step(self.player1, decoded)
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.act_inference(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))

        done = self.game.check_end_condition()
        new_state = self.game.get_observations(self.player1)
        reward = self.get_reward(original_state, new_state)
        obs = self.get_obs(self.player1)
        return obs, reward, done, {}


    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        self.get_opponent_agent()
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.act_inference(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.get_obs(self.player1)


    def get_opponent_agent(self):
        import random as _r
        x = _r.random()
        self.opponent = "random" if x < 0.03 else "trained"


    def load_model(self, model_path):
        self.model.load_state_dict(torch.load(model_path))


class DQNOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = DoubleDQNAgent(OBS_DIM, ACTION_DIM, "cuda")


    def step(self, action):
        obs_before = self.game.get_obs_tensor(self.player1, "cpu")
        decoded = self.decode_action(self.player1, action)
        if decoded is None:
            obs_after = self.game.get_obs_tensor(self.player1, "cpu")
            return obs_after.to(device=_DEVICE), 0, False, {}
        self.game.step(self.player1, decoded)
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = self.game.get_obs_tensor(self.player2, _DEVICE)
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))

        done = self.game.check_end_condition()
        obs_after = self.game.get_obs_tensor(self.player1, "cpu")
        reward = self.get_reward(obs_before, obs_after)
        return obs_after.to(device=_DEVICE), reward, done, {}


    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        self.get_opponent_agent()
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = self.game.get_obs_tensor(self.player2, _DEVICE)
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.game.get_obs_tensor(self.player1, _DEVICE)


    def get_opponent_agent(self):
        import random as _r
        x = _r.random()
        self.opponent = "random" if x < 0.02 else "trained"


    def load_model(self, model_path):
        self.model.load_model(model_path)


class DQNRandomDeckGameEnv(DQNOpponentGameEnv):
    def __init__(self):
        super().__init__()
        # self.model.load_model("./logs/dqn/2026-07-27_15-18-00/dqn_model.pt")

    def reset(self):
        # 阵容：4 式神、派系 ≤2（预计算的合法组合中均匀抽取）；卡组：见 _build_deck
        player1_heroes = list(r.choice(self.valid_lineups))
        player2_heroes = list(r.choice(self.valid_lineups))
        player1_deck = self._build_deck(player1_heroes)
        player2_deck = self._build_deck(player2_heroes)
        self.player1 = Player(player1_deck, player1_heroes)
        self.player2 = Player(player2_deck, player2_heroes)
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        self.get_opponent_agent()
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = self.game.get_obs_tensor(self.player2, _DEVICE)
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.game.get_obs_tensor(self.player1, _DEVICE)
