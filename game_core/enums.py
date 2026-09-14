from enum import IntEnum

class CardAttributes(IntEnum):
    INSTANT = 1
    NO_FIRE_CONSUMPTION = 2
    CAN_PLAY_WHEN_DEAD = 3
    RESPONSE = 4         # 响应：可在敌方回合满足条件时自动使用
    ENHANCE = 5          # 增强：满足条件时获得额外效果
    BLAST = 6            # 爆能：可额外消耗能量触发增强
    IS_INGREDIENT = 7    # 食材标记：用于烹饪合成检测
    CHARGE = 8           # 蓄力：可蓄力打出，下个己方回合开始结算并获得强化效果


class HeroAttributes(IntEnum):
    AGILE = 1            # 迅捷：下一次出击不消耗鬼火
    PENETRATE = 2        # 贯通：过量伤害转移给敌方牌手
    HUNTING = 3          # 追猎：可指定攻击任一敌方式神
    RANGED = 4           # 远程：可在准备区攻击，不受反击
    PROJECTILE = 5       # 投射：移动时对敌方战斗区造成伤害
    FATAL = 6            # 必杀：消灭受到此伤害的式神
    DOUBLE_STRIKE = 7    # 连击：额外先造成一次战斗伤害
    LIFESTEAL = 8        # 吸血：造成伤害时恢复等量生命
    TENACIOUS = 9        # 不屈：hp>1时最多受到使其减为1的伤害，触发后移除
    VEIL = 10            # 帷幕：不能被敌方卡牌选为目标
    BARRIER = 11         # 屏障：免疫一次伤害后移除
    FIRST_STRIKE = 12    # 先攻：战斗时先于对方造成伤害
    DIRECT_ATTACK = 13   # 直击：直接攻击敌方牌手
    PIERCING = 14        # 穿刺：造成伤害前移除目标护甲和屏障
    CRITICAL = 15        # 暴击：伤害翻倍
    VALIANT = 16         # 昂扬：出击不消耗出击次数
    ENERGY_CHARGE = 17   # 充能：己方回合开始获得 1 能量
    FUSE = 18            # 融合：进场时与己方场上同组（fuse_group）融合体合并（wiki 关键字-融合）


class CardType(IntEnum):
    ATTACK = 1           # 战斗牌
    SPELL = 2            # 法术牌
    MORPH = 3            # 形态牌
    AWAKEN = 4           # 觉醒牌（独立类型以支持觉醒特有机制）
    ILLUSION = 5         # 幻境牌（Phase 2）
    SPIRIT_CURSE = 6     # 灵咒牌（Phase 2）
    TOKEN = 7            # 衍生牌（黄金羽、食材等）
    COOP = 8             # 协战牌（两位式神共享，打出时选择由谁打出）


class PlayerState(IntEnum):
    INITIAL_PICK = 1
    PLAYING = 2
    WAITING = 3
    SELECTING_TARGET = 4
    LOST = 5
    WON = 6
    SELECTING_OPTION = 7  # 从多个效果中选择一个
    DIVINATING = 8        # 占卜中（Phase 2）


# Card type 字符串到枚举的映射，保持向后兼容
CARD_TYPE_STRING_MAP = {
    "attack": CardType.ATTACK,
    "spell": CardType.SPELL,
    "morph": CardType.MORPH,
    "awaken": CardType.AWAKEN,
    "illusion": CardType.ILLUSION,
    "spirit_curse": CardType.SPIRIT_CURSE,
    "token": CardType.TOKEN,
    "coop": CardType.COOP,
}


def get_card_enum(card_type_str: str) -> CardType:
    """将字符串卡牌类型转换为 CardType 枚举"""
    if isinstance(card_type_str, CardType):
        return card_type_str
    return CARD_TYPE_STRING_MAP.get(card_type_str, CardType.SPELL)
