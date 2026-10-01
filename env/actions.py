# ═══════════════════════════════════════════════════════════════════════════════
# 动作/观测空间 — 卡牌ID 编码版（移植自 experiments/deck_strength/spaces.py）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 卡牌 ID 编码约定（token 侧的 id 声明见 game_core/cards/_ingredients.py 与
# game_core/cards/TuYuMenHuTao.py）：
#   正式卡 id = cards.json 中的 id（1..MAX_CARD_ID，连续无空洞）
#   token 卡 id = MAX_CARD_ID + 偏移（食材/佳肴 +1..+10，胡桃物品 +11..+32）
#   ⇒ 全空间 1..TOTAL_CARD_NUM 连续，index = id - 1 数到每一张可打出/可观测的卡
#
# MAX_CARD_ID 由 cards.json 推导（见下方 _load_max_card_id），token 相对它偏移，
# 因此新增正式卡时 token 自动后移，不需要手工同步。旧版把 token 写死在 300-331
# 且 MAX_CARD_ID 停在 282：cards.json 长到 334 后 token 与鬼王/好拳等正式卡撞车，
# 而 id > 282 的卡在 obs 的 multi-hot 与 PLAY_CARD/REJECT 动作里被静默丢弃
# （食灵烹饪产出的食材/佳肴因此看不见也打不出）。
#
# 相对旧版（709 维 / 48 动作）的三处修复（保留）：
#   1. 卡牌 multi-hot 覆盖全 id 空间。旧 100 维版本使 id > 100 的卡完全不可见。
#   2. PLAY_CARD / REJECT 按卡牌ID 编码（动作ID = START + card.id - 1）：旧版按
#      手牌位置编码，而 obs 的手牌是（式神顺序, 等级, 到手顺序）排序后的
#      multi-hot 集合，两套索引互相错位。手牌中同 id 的多张副本折叠为一个
#      动作（打出任意一张等价）。
#   3. SELECT_TARGET 按 candidate_targets 列表下标编码：旧版固定类别槽
#      （0=对手牌手, 1-4 对手式神, 5-8 己方式神, 9=自己），与真实候选顺序无关。
#
# 卡牌 id 直接取 card.id。spaces.py（deck_strength 实验）版本优先走
# Card.get_id_by_name（cards.json），二者仅在 3 张旧编号卡牌类上不同
# （LuJiaoChongZhuang / JueXingXiaoLuNan / JueXingLianYou，id 仍停留在 197/200/206），
# 待这些卡牌类文件的 id 修正后自动与 cards.json 对齐。
#
# 注意 A：旧 709 维 / 48 动作的 checkpoint 与本空间不兼容（size mismatch）。
# 注意 B：本模块模块级 import torch，而 game_core/cards/*.py 需要 MAX_CARD_ID，
#         故引擎侧导入会连带引入 torch。

import json
import os

import torch

from game_core.action import (EndTurn, UpgradeHero, HeroAttack, PlayCard,
                              SelectTarget, RejectInitialPick, MoveHero)

# ── 卡牌 id 空间 ─────────────────────────────────────────────────────────────

_CARDS_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "game_core", "cards", "cards.json")


def _load_cards_json() -> list:
    """读 cards.json，并校验 id 唯一（重复 id 会让卡牌下标空间撞车）。"""
    with open(_CARDS_JSON, "r", encoding="utf-8") as f:
        card_data = json.load(f)
    ids = [c["id"] for c in card_data]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"cards.json 存在重复 id: {dupes}")
    return card_data


_CARD_DATA      = _load_cards_json()
MAX_CARD_ID     = max(c["id"] for c in _CARD_DATA)   # 正式卡最大 id
TOKEN_NUM       = 32                    # token 卡总数（食材/佳肴 10 + 胡桃物品 22）
TOTAL_CARD_NUM  = MAX_CARD_ID + TOKEN_NUM   # 卡牌 id 空间总长 = obs/动作下标上界

#: 幻境卡密集编号（按 cards.json 顺序，写入 obs 时用 编号 本身；0 保留给空槽）。
#: 直接写卡牌 id（0..366）当标量范围太大、噪声高，密集编号更利于网络分卡学效果。
ILLUSION_IDS     = {c["eng_name"]: i + 1
                    for i, c in enumerate(c for c in _CARD_DATA if c["type"] == "illusion")}
#: 表外幻境卡（正常情况下不会出现；写非 0 值，避免被误读成空槽）
ILLUSION_UNKNOWN = len(ILLUSION_IDS) + 1

# ── 式神槽位 ─────────────────────────────────────────────────────────────────

HERO_BLOCK     = 29   # 单个式神块宽度
NUM_HEROES     = 4    # 阵容式神数（= obs 的式神块数）
# 召唤物会作为额外式神追加到 player.heroes 末尾，同时至多 1 个、且必定是战斗区
# 占用者（player.advance_hero 顶替时 dismiss_summon 离场 / 换人时被顶到准备区），
# 所以 player.heroes 里可出击的下标最多到 NUM_HEROES（第 5 个）。
# 升级/移动仍只对 4 个阵容式神开放——引擎从不为召唤物提供这两类动作。
NUM_HERO_SLOTS = NUM_HEROES + 1

# ── 动作空间 ─────────────────────────────────────────────────────────────────

MAX_SELECT_TARGETS      = 10   # 候选目标槽位上限（超出部分丢弃）
HAND_LIMIT              = 12   # 手牌上限（get_reward 超量惩罚用）

END_TURN                = 0
UPGRADE_HERO_START      = 1                                       # +NUM_HEROES（式神下标）
HERO_ATTACK_START       = UPGRADE_HERO_START + NUM_HEROES         # +NUM_HERO_SLOTS（含召唤物）
PLAY_CARD_START         = HERO_ATTACK_START + NUM_HERO_SLOTS      # +TOTAL_CARD_NUM（按卡牌ID）
SELECT_TARGET_START     = PLAY_CARD_START + TOTAL_CARD_NUM        # +MAX_SELECT_TARGETS
REJECT_START            = SELECT_TARGET_START + MAX_SELECT_TARGETS
MOVE_HERO_START         = REJECT_START + TOTAL_CARD_NUM           # +NUM_HEROES×2
ACTION_DIM              = MOVE_HERO_START + NUM_HEROES * 2

REJECT_INITIAL_PICK_START = REJECT_START   # 旧名兼容别名（防外部 import 断裂）

# ── 观测空间 ─────────────────────────────────────────────────────────────────
# 召唤物不需要额外的 obs 块：它是战斗区占用者（state == "attacking"），已由
# PLAYER/OPP_ATTACKING 块表示（那两个循环遍历 player.heroes 全部元素、不做
# NUM_HEROES 截断，见 env.get_obs 与 game.get_obs_tensor）。

# ── 幻境区 ───────────────────────────────────────────────────────────────────
# 幻境区里所有幻境的效果同时生效；牌手受伤时「最早进入的」那个同步扣等量耐久
# ——**并行不减免**，伤害照样全额扣牌手血（见 player.receive_damage），耐久 ≤0
# 才离场。所以耐久表示「这个效果还能持续多久」+「≥10 / ≥15 这类阈值是否成立」，
# 不是护盾。据此两条编码约束：
#   ① 同名幻境可重复叠加（实测 300 局中 2507 个快照的幻境区有同名条目）→ 必须按
#      「条目」编码，不能只给「哪些卡在场」的 multi-hot（那样会丢掉各自耐久）；
#   ② 只有 index 0 承伤 → 槽位次序本身有语义，槽 0 = 当前承伤位。
# 实测幻境区长度最大 8（分布 0..8 递减）；理论上限受 32 张卡组约束达不到。
MAX_ILLUSIONS     = 8
ILLUSION_BLOCK    = 2   # ID（密集编号，0=空槽）+ 当前耐久
ILLUSION_ZONE_DIM = MAX_ILLUSIONS * ILLUSION_BLOCK

# OBS_DIM 计算
# ============
#   基础标量          = 5
#   8 式神块          = 8 * HERO_BLOCK         = 232
#   幻境区 ×2         = 2 * ILLUSION_ZONE_DIM  = 32
#   牌手标量          = 14
#   卡牌多热 ×4       = 4 * TOTAL_CARD_NUM     = 1464
#   攻击式神 ×2       = 2 * HERO_BLOCK         = 58
#   ────────────────────────────────────────────────
#   TOTAL                                      = 1805

BASE_SCALARS     = 5
PLAYER_SCALARS   = 14
ATTACKING_HEROES = 2

OBS_DIM = (
    BASE_SCALARS
    + 2 * NUM_HEROES * HERO_BLOCK
    + 2 * ILLUSION_ZONE_DIM
    + PLAYER_SCALARS
    + 4 * TOTAL_CARD_NUM
    + ATTACKING_HEROES * HERO_BLOCK
)

assert OBS_DIM == 1805, f"OBS_DIM expected 1805, got {OBS_DIM}"
assert ACTION_DIM == 760, f"ACTION_DIM expected 760, got {ACTION_DIM}"


# ═══════════════════════════════════════════════════════════════════════════════
#  Hero Block 内偏移 (29 维)
# ═══════════════════════════════════════════════════════════════════════════════

class HeroField:
    """式神块 (29 维) 中各字段的偏移量"""
    ID                = 0
    MORPHED_ID        = 1
    CURRENT_MAX_HP    = 2
    HP                = 3
    ATK               = 4
    ROUND_BUFF_ATK    = 5
    DEFENSE           = 6
    LEVEL             = 7
    ROUND_UNTIL_ALIVE = 8
    POSITION_STATE    = 9    # 0=准备区 1=战斗区 2=气绝
    IS_STUNNED        = 10   # 0/1
    IS_AWAKENED       = 11   # 0/1
    COUNTDOWN_RATIO   = 12   # 当前倒计时/最大倒计时 (无则为0)

    # 全部 16 个 HeroAttributes 起始偏移
    ATTR_START        = 13
    # 13: AGILE          (迅捷)
    # 14: PENETRATE      (贯通)
    # 15: HUNTING        (追猎)
    # 16: RANGED         (远程)
    # 17: PROJECTILE     (投射)
    # 18: FATAL          (必杀)
    # 19: DOUBLE_STRIKE  (连击)
    # 20: LIFESTEAL      (吸血)
    # 21: TENACIOUS      (不屈)
    # 22: VEIL           (帷幕)
    # 23: BARRIER        (屏障)
    # 24: FIRST_STRIKE   (先攻)
    # 25: DIRECT_ATTACK  (直击)
    # 26: PIERCING       (穿刺)
    # 27: CRITICAL       (暴击)
    # 28: VALIANT        (昂扬)


# ═══════════════════════════════════════════════════════════════════════════════
#  观测索引
# ═══════════════════════════════════════════════════════════════════════════════

class ObsIdx:
    # ── 基础标量 (5) ──────────────────────────────────────────────────
    # 顺序与 deck_strength 实验的 spaces.py 一致；GAME_STATE 为预留位，从不写入
    PLAYER_STATE       = 0
    TURN_COUNT         = 1
    PLAYER_HP          = 2
    OPPONENT_HP        = 3
    GAME_STATE         = 4    # 从不写入（恒 0）

    # ── 己方式神 (4 × 29) ─────────────────────────────────────────────
    PLAYER_HERO_START  = BASE_SCALARS                        #   5 ~  120

    # ── 对手式神 (4 × 29) ─────────────────────────────────────────────
    OPP_HERO_START     = PLAYER_HERO_START + NUM_HEROES * HERO_BLOCK   # 121 ~  236

    # ── 幻境区 (2 × MAX_ILLUSIONS × ILLUSION_BLOCK) ───────────────────
    # 槽 i 对应 illusion_zone[i]，槽 0 = 当前承伤位；无幻境时全 0
    PLAYER_ILLUSION_START = OPP_HERO_START + NUM_HEROES * HERO_BLOCK   # 237 ~  252
    OPP_ILLUSION_START    = PLAYER_ILLUSION_START + ILLUSION_ZONE_DIM  # 253 ~  268

    # ── 牌手标量 (14) ─────────────────────────────────────────────────
    PLAYER_DECK        = OPP_ILLUSION_START + ILLUSION_ZONE_DIM       # 269
    OPPONENT_DECK      = PLAYER_DECK + 1
    OPPONENT_HAND_SIZE = PLAYER_DECK + 2
    FIRE_REMAINING     = PLAYER_DECK + 3
    ATTACK_AVAILABLE   = PLAYER_DECK + 4
    IS_FIRST_PLAYER    = PLAYER_DECK + 5
    PENDING_CARD       = PLAYER_DECK + 6
    PLAYER_INSP_ATK    = PLAYER_DECK + 7
    PLAYER_INSP_DEF    = PLAYER_DECK + 8
    PLAYER_DEFENSE     = PLAYER_DECK + 9      # 牌手护甲
    OPPONENT_DEFENSE   = PLAYER_DECK + 10     # 对手护甲
    UPGRADE_REMAINING  = PLAYER_DECK + 11     # 当前回合剩余升级次数
    INSTANT_USED       = PLAYER_DECK + 12     # 是否已用掉本回合免费瞬发
    OPPONENT_FIRE      = PLAYER_DECK + 13     # 对手剩余鬼火

    # ── 卡牌多热编码 (4 × TOTAL_CARD_NUM) ─────────────────────────────
    PLAYER_HAND_START   = OPPONENT_FIRE + 1                          #  283 ~  648
    STARTING_DECK_START = PLAYER_HAND_START + TOTAL_CARD_NUM         #  649 ~ 1014
    PLAYER_USED_START   = STARTING_DECK_START + TOTAL_CARD_NUM       # 1015 ~ 1380
    OPP_USED_START      = PLAYER_USED_START + TOTAL_CARD_NUM         # 1381 ~ 1746

    # ── 正在攻击的式神 (2 × 29) ──────────────────────────────────────
    PLAYER_ATTACKING_START = OPP_USED_START + TOTAL_CARD_NUM         # 1747 ~ 1775
    OPP_ATTACKING_START    = PLAYER_ATTACKING_START + HERO_BLOCK     # 1776 ~ 1804


# ObsIdx 必须正好铺满 OBS_DIM：改任何一段的宽度都会在这里报错
assert ObsIdx.OPP_ATTACKING_START + HERO_BLOCK == OBS_DIM, (
    f"ObsIdx layout ends at {ObsIdx.OPP_ATTACKING_START + HERO_BLOCK}, OBS_DIM={OBS_DIM}")


# ── reward 函数便捷索引 ──────────────────────────────────────────────────

OPP_HERO_HP  = [ObsIdx.OPP_HERO_START + i * HERO_BLOCK + HeroField.HP
                for i in range(NUM_HEROES)]
OPP_HERO_DEF = [ObsIdx.OPP_HERO_START + i * HERO_BLOCK + HeroField.DEFENSE
                for i in range(NUM_HEROES)]
PLAYER_HERO_HP = [ObsIdx.PLAYER_HERO_START + i * HERO_BLOCK + HeroField.HP
                  for i in range(NUM_HEROES)]


# ═══════════════════════════════════════════════════════════════════════════════
#  动作映射：引擎 Action ⇄ 动作ID（移植自 experiments/deck_strength/spaces.py）
# ═══════════════════════════════════════════════════════════════════════════════

def get_legal_action_ids(player):
    """当前 player 的合法动作ID列表（引擎真值 → id，去重排序）。"""
    ids = set()
    for action in player.get_legal_actions():
        aid = _action_to_id(player, action)
        if aid is not None:
            ids.add(aid)
    return sorted(ids)


def _action_to_id(player, action):
    t = action.type
    if t == "end turn":
        return END_TURN
    if t == "upgrade hero":
        idx = player.heroes.index(action.hero)
        return UPGRADE_HERO_START + idx if idx < NUM_HEROES else None
    if t == "hero attack":
        # 召唤物在 heroes 末尾（下标 NUM_HEROES），故上界用 NUM_HERO_SLOTS
        idx = player.heroes.index(action.hero)
        return HERO_ATTACK_START + idx if idx < NUM_HERO_SLOTS else None
    if t == "play card action":
        cid = action.card.id
        if not (1 <= cid <= TOTAL_CARD_NUM):
            return None
        return PLAY_CARD_START + cid - 1
    if t == "select target":
        # 候选目标可能多于槽位（召唤物进场等）：超出部分丢弃
        try:
            idx = player.candidate_targets.index(action.target)
        except ValueError:
            return None
        return SELECT_TARGET_START + idx if idx < MAX_SELECT_TARGETS else None
    if t == "reject initial pick":
        cid = action.card.id
        if not (1 <= cid <= TOTAL_CARD_NUM):
            return None
        return REJECT_START + cid - 1
    if t == "move hero":
        idx = player.heroes.index(action.hero)
        if idx >= NUM_HEROES:
            return None
        return MOVE_HERO_START + idx * 2 + (0 if action.to_battle else 1)
    return None


def decode_action(player, action_id):
    """动作ID → 引擎 Action；无法解码（牌已离手等）返回 None。"""
    if action_id == END_TURN:
        return EndTurn()
    if UPGRADE_HERO_START <= action_id < HERO_ATTACK_START:
        idx = action_id - UPGRADE_HERO_START
        if idx < len(player.heroes):
            return UpgradeHero(player.heroes[idx])
        return None
    if HERO_ATTACK_START <= action_id < PLAY_CARD_START:
        idx = action_id - HERO_ATTACK_START
        if idx < len(player.heroes):
            return HeroAttack(player.heroes[idx])
        return None
    if PLAY_CARD_START <= action_id < SELECT_TARGET_START:
        cid = action_id - PLAY_CARD_START + 1
        for card in player.hand.cards:
            if card.id == cid:
                return PlayCard(card, None)
        return None
    if SELECT_TARGET_START <= action_id < REJECT_START:
        idx = action_id - SELECT_TARGET_START
        if idx < len(player.candidate_targets):
            return SelectTarget(player.candidate_targets[idx])
        return None
    if REJECT_START <= action_id < MOVE_HERO_START:
        cid = action_id - REJECT_START + 1
        for card in player.hand.cards:
            if card.id == cid:
                return RejectInitialPick(card)
        return None
    if MOVE_HERO_START <= action_id < ACTION_DIM:
        off = action_id - MOVE_HERO_START
        idx, to_battle = divmod(off, 2)
        if idx < len(player.heroes):
            return MoveHero(player.heroes[idx], to_battle)
        return None
    return None


def build_action_mask(player, device):
    """反向动作掩码（True=非法）的 bool tensor——接口与 rl_dqn 一致。"""
    mask = torch.ones(ACTION_DIM, dtype=torch.bool, device=device)
    for aid in get_legal_action_ids(player):
        mask[aid] = False
    return mask