# ═══════════════════════════════════════════════════════════════════════════════
# 动作/观测空间 — 卡牌ID 编码版（移植自 experiments/deck_strength/spaces.py）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 相对旧版（709 维 / 48 动作）的三处修复：
#   1. MAX_CARD_ID 100 → 282：cards.json 全量（1..282 连续）。旧 100 维 multi-hot
#      使 id > 100 的手牌/牌库/弃牌在 obs 中完全不可见。
#   2. PLAY_CARD / REJECT 按卡牌ID 编码（动作ID = START + card.id - 1）：旧版按
#      手牌位置编码，而 obs 的手牌是（式神顺序, 等级, 到手顺序）排序后的
#      multi-hot 集合，两套索引互相错位。手牌中同 id 的多张副本折叠为一个
#      动作（打出任意一张等价）。
#   3. SELECT_TARGET 按 candidate_targets 列表下标编码：旧版固定类别槽
#      （0=对手牌手, 1-4 对手式神, 5-8 己方式神, 9=自己），与真实候选顺序无关。
#
# 卡牌 id 直接取 card.id（卡牌类文件声明的 id）。spaces.py（deck_strength 实验）
# 版本优先走 Card.get_id_by_name（cards.json），二者仅在 4 张旧编号卡牌类上
# 不同（LuJiaoChongZhuang / JueXingXiaoLuNan / JueXingLianYou / JueXingRiHeFang），
# 待这些卡牌类文件的 id 修正后自动与 cards.json 对齐。
#
# 注意：旧 709 维 / 48 动作的 checkpoint 与本空间不兼容（size mismatch）。

import torch

from game_core.action import (EndTurn, UpgradeHero, HeroAttack, PlayCard,
                              SelectTarget, RejectInitialPick, MoveHero)

# ── 动作空间（591 维）─────────────────────────────────────────────────────────

END_TURN                = 0
UPGRADE_HERO_START      = 1                                    # +4（式神下标）
HERO_ATTACK_START       = 5                                    # +4（式神下标）
PLAY_CARD_START         = 9                                    # +282（按卡牌ID）
SELECT_TARGET_START     = 291                                  # +10（候选目标下标）
REJECT_START            = 301                                  # +282（按卡牌ID）
MOVE_HERO_START         = 583                                  # +4×2（式神 × 战斗区/准备区）
ACTION_DIM              = 591

REJECT_INITIAL_PICK_START = REJECT_START   # 旧名兼容别名（防外部 import 断裂）

MAX_SELECT_TARGETS      = 10   # 候选目标槽位上限（超出部分丢弃）
HAND_LIMIT              = 12   # 手牌上限（get_reward 超量惩罚用）

# ── 观测空间 — 1437 维 ────────────────────────────────────────────────────────

HERO_BLOCK   = 29
NUM_HEROES   = 4
MAX_CARD_ID  = 282

# OBS_DIM 计算
# ============
#   基础标量          = 5
#   8 式神块          = 8 * HERO_BLOCK  = 232
#   牌手标量          = 14
#   卡牌多热 ×4       = 4 * MAX_CARD_ID = 1128
#   攻击式神 ×2       = 2 * HERO_BLOCK  = 58
#   ─────────────────────────────────────────
#   TOTAL                               = 1437

BASE_SCALARS     = 5
PLAYER_SCALARS   = 14
ATTACKING_HEROES = 2

OBS_DIM = (
    BASE_SCALARS
    + 2 * NUM_HEROES * HERO_BLOCK
    + PLAYER_SCALARS
    + 4 * MAX_CARD_ID
    + ATTACKING_HEROES * HERO_BLOCK
)

assert OBS_DIM == 1437, f"OBS_DIM expected 1437, got {OBS_DIM}"


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
    PLAYER_HERO_START  = 5       #   5 ~ 120

    # ── 对手式神 (4 × 29) ─────────────────────────────────────────────
    OPP_HERO_START     = 121     # 121 ~ 236

    # ── 牌手标量 (14) ─────────────────────────────────────────────────
    PLAYER_DECK        = 237
    OPPONENT_DECK      = 238
    OPPONENT_HAND_SIZE = 239
    FIRE_REMAINING     = 240
    ATTACK_AVAILABLE   = 241
    IS_FIRST_PLAYER    = 242
    PENDING_CARD       = 243
    PLAYER_INSP_ATK    = 244
    PLAYER_INSP_DEF    = 245
    PLAYER_DEFENSE     = 246     # 牌手护甲
    OPPONENT_DEFENSE   = 247     # 对手护甲
    UPGRADE_REMAINING  = 248     # 当前回合剩余升级次数
    INSTANT_USED       = 249     # 是否已用掉本回合免费瞬发
    OPPONENT_FIRE      = 250     # 对手剩余鬼火

    # ── 卡牌多热编码 (4 × 282) ────────────────────────────────────────
    PLAYER_HAND_START   = 251    #  251 ~  532
    STARTING_DECK_START = 533    #  533 ~  814
    PLAYER_USED_START   = 815    #  815 ~ 1096
    OPP_USED_START      = 1097   # 1097 ~ 1378

    # ── 正在攻击的式神 (2 × 29) ──────────────────────────────────────
    PLAYER_ATTACKING_START = 1379  # 1379 ~ 1407
    OPP_ATTACKING_START    = 1408  # 1408 ~ 1436


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
        idx = player.heroes.index(action.hero)
        return HERO_ATTACK_START + idx if idx < NUM_HEROES else None
    if t == "play card":
        cid = action.card.id
        if not (1 <= cid <= MAX_CARD_ID):
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
        if not (1 <= cid <= MAX_CARD_ID):
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