"""obs 各子树的编码器。

布局常量（ObsIdx / HeroField / ...）在 env/actions.py。本模块只负责「把一个引擎
对象写进 buffer 的指定区段」，供 env.env.get_obs 与 game_core.game.get_obs_tensor
共用——这两条 obs 路径此前各写一份实现，改一边漏一边的风险很高（式神块就是被重复
实现了几百行的那种）。

新增观测子树（hero encoder / card encoder / ...）时按同一形状追加即可：

    def encode_xxx(buf, base, obj) -> None

约定：
  · 只写 buf[base : base + XXX_DIM]，不越界、不读全局状态、无返回值；
  · 起始下标由调用方从 ObsIdx 取，本模块不认识「己方/对方」的语义。
"""

from .actions import (HeroField, HERO_BLOCK, ILLUSION_BLOCK, ILLUSION_IDS,
                      ILLUSION_UNKNOWN, MAX_ILLUSIONS)


def encode_hero_block(buf, base: int, hero) -> None:
    """写一个 29 维式神块（HERO_BLOCK）到 buf[base:base+HERO_BLOCK]。"""
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


def encode_illusion_zone(buf, base: int, player) -> None:
    """写一个幻境区（MAX_ILLUSIONS 槽 × ILLUSION_BLOCK 维）。

    槽 i = player.illusion_zone[i]；槽 0 是当前承伤位（牌手受伤时它同步扣等量
    耐久，见 player.receive_damage），所以槽位次序本身携带信息。

    每槽两维：
      ID         幻境卡密集编号（ILLUSION_IDS，0 = 空槽）
      耐久       当前耐久（≥10 / ≥15 这类阈值条件依赖精确值）

    超过 MAX_ILLUSIONS 的条目截断——实测对局最大 8 条，且只有队首承伤，尾部对
    当前决策影响最小。
    """
    for i, card in enumerate(player.illusion_zone[:MAX_ILLUSIONS]):
        off = base + i * ILLUSION_BLOCK
        buf[off]     = ILLUSION_IDS.get(card.eng_name, ILLUSION_UNKNOWN)
        buf[off + 1] = card.durability