class Event:
    def __init__(self, type, **kwargs):
        self.type = type
        self.__dict__.update(kwargs)

class GiveBuff(Event):
    def __init__(self, attr, value, source, target):
        self.type = "give buff"
        self.attr = attr
        self.value = value
        self.source = source
        self.target = target

    def __str__(self):
        return f"Give {self.attr} buff of {self.value} to {self.target} from {self.source}"

class Heal(Event):
    def __init__(self, value, source, target):
        self.type = "heal"
        self.value = value
        self.source = source
        self.target = target

    def __str__(self):
        return f"Healing {self.target} for {self.value} from {self.source}"

class DealDamage(Event):
    def __init__(self, value, source, target, damage_type="spell"):
        self.type = "deal damage"
        self.value = value
        self.source = source
        self.target = target
        self.damage_type = damage_type  # "spell" | "combat" | "projectile"

    def __str__(self):
        return f"Dealing {self.value} damage to {self.target} from {self.source}"

class Revive(Event):
    def __init__(self, source, target):
        self.type = "revive"
        self.source = source
        self.target = target

# 复活完成后广播（case "revive" 中 revive() 执行之后）。与 "revive"（复活动作
# 事件，广播时目标仍处气绝态，give buff 会跳过气绝目标）区分：治疗/加成类
# 复活被动（桃花妖等）须监听本事件，结算时目标已存活。
class AfterRevive(Event):
    def __init__(self, source, target):
        self.type = "after revive"
        self.source = source
        self.target = target

class HeroAttackEvent(Event):
    def __init__(self, player, hero, card=None):
        self.type = "hero attack"
        self.player = player
        self.hero = hero
        self.card = card

    def __str__(self):
        return f"Attack with {self.hero.name}" + (f" by {self.card.name}" if self.card else "")

class PlayCardEvent(Event):
    """使用牌事件（两阶段广播，同一事件类型广播两次）。

    - phase="before"（结算前）：目标选择完成后、实际结算（扣费/效果）前广播，
      供必须在结算生效前介入的监听器：否定（魔音扰心 revert 拦截）与注入
      （不夜之舞/心技一体把鼓舞/增强写入本牌 buff_atk/buff_def）。revert 置位
      后 play_card 放弃本次打出（费用未扣）。
    - phase="after"（结算后）：结算与卡牌去向均已落定后在 play_card 末尾广播，
      「使用牌时」类触发被动（凤凰火投射、火取魔计数等）监听此阶段——监听器
      读到的是结算后的战场状态（如对手战斗区是否已被打出的牌清空）。
      被拒绝/放弃的打出不广播；被否定的打出只有 before 没有 after。

    response：是否经响应通道打出（_play_response_card）。响应战斗牌只施加
    效果不消耗鼓舞（既有语义），供「仅主动打出」类监听器区分。
    """
    def __init__(self, player, card, response=False):
        self.type = "play card"
        self.player = player
        self.card = card
        self.response = response

    def __str__(self):
        return f"Play card {getattr(self.card, 'name', self.card)}"

class InspireEvent(Event):
    """鼓舞生效事件（可修改）：某牌手的鼓舞即将生效，监听器可修改 atk/defense。

    四个鼓舞消费点在应用/消耗前广播本事件：
    - 引擎出击（game.step "hero attack" else 分支）；
    - 不夜之舞（战斗牌注入鼓舞并消耗，BuZhiHuo.py）；
    - 夜袭（战斗牌注入鼓舞并消耗，HuoQuMo.py）；
    - 烬染不夜特殊攻击（伤害 = 攻击力 + 鼓舞攻击，heroes.py）。

    atk/defense 为本次即将生效的鼓舞数值（= 当前鼓舞池），监听器直接修改
    这两个字段即可调整实际生效值（先例：座敷童子修改 e.event.result）；
    池子本身的消耗由各消费点自行完成，与本事件无关。数值可能为 0（空池
    出击），监听器按需过滤（如觉醒·不知火仅在 >0 时额外 +1/+1）。
    """
    def __init__(self, player, hero, atk, defense):
        self.type = "inspire"
        self.player = player
        self.hero = hero
        self.atk = atk
        self.defense = defense

    def __str__(self):
        return f"inspire (+{self.atk}/+{self.defense}) applies to {self.hero.name}"

class EntitiesAttack(Event):
    def __init__(self, entity1, entity2):
        self.type = "entities attack"
        self.entity1 = entity1
        self.entity2 = entity2

class DamageDealt(Event):
    """伤害已造成事件（结算后的纯通知，监听方不得再次应用伤害）。

    三条伤害通道在伤害实际结算后统一广播：
    - 法术/能力：DealDamage 的 "deal damage" 分支结算后；
    - 战斗：_resolve_single_hit 实际造成伤害（damage_dealt）后；
    - 投射：ProjectileEvent 结算后。

    value 为本次造成伤害的数值（战斗取实际 damage_dealt，法术/投射取名义值）；
    target 恒为列表（多目标同时结算视为一次 atomic 操作，监听方用 in 判断）；
    damage_type 为 "spell" | "combat" | "projectile"。
    """
    def __init__(self, value, source, target, damage_type):
        self.type = "damage dealt"
        self.value = value
        self.source = source
        self.target = target
        self.damage_type = damage_type

    def __str__(self):
        return f"{self.source} dealt {self.value} {self.damage_type} damage to {self.target}"

class DrawSelectedCardFromDeck(Event):
    def __init__(self, player, card):
        self.type = "draw selected card from deck"
        self.player = player
        self.card = card


# ── 新增事件类型 (Phase 1) ──────────────────────────────────────────────────

class MoveEvent(Event):
    """式神移动事件（移入/移出战斗区）"""
    def __init__(self, hero, from_zone: str, to_zone: str):
        self.type = "move"
        self.hero = hero
        self.from_zone = from_zone     # "battle" / "standby"
        self.to_zone = to_zone

    def __str__(self):
        return f"Move {self.hero.name} from {self.from_zone} to {self.to_zone}"


class CountdownEvent(Event):
    """倒计时触发事件"""
    def __init__(self, hero):
        self.type = "countdown"
        self.hero = hero

    def __str__(self):
        return f"Countdown triggered for {self.hero.name}"


class ProjectileEvent(Event):
    """投射伤害事件"""
    def __init__(self, value, source, target):
        self.type = "projectile"
        self.value = value
        self.source = source
        self.target = target

    def __str__(self):
        return f"Projectile {self.value} damage to {self.target} from {self.source}"


class StunEvent(Event):
    """眩晕/解除眩晕事件"""
    def __init__(self, target, stunned: bool):
        self.type = "stun" if stunned else "unstun"
        self.target = target
        self.stunned = stunned


class PermanentDeathEvent(Event):
    """永久死亡事件（如九命猫堆满 5 层九命）"""
    def __init__(self, hero):
        self.type = "permanent death"
        self.hero = hero

    def __str__(self):
        return f"Permanent death of {self.hero.name}"


# ── 新增事件类型 (Phase 2：机制扩展) ──────────────────────────────────────

class FortuneRollEvent(Event):
    """运势判定事件（含结果；监听器可修改 result 实现重投/覆写）。"""
    def __init__(self, source_hero, threshold, result):
        self.type = "fortune roll"
        self.source_hero = source_hero
        self.threshold = threshold
        self.result = result

    def __str__(self):
        return f"Fortune roll {self.result} (threshold {self.threshold}) for {self.source_hero.name}"


class FortuneSuccessEvent(Event):
    """运势判定成功事件。"""
    def __init__(self, source_hero, result):
        self.type = "fortune success"
        self.source_hero = source_hero
        self.result = result

    def __str__(self):
        return f"Fortune success ({self.result}) for {self.source_hero.name}"


class IllusionPlayedEvent(Event):
    """幻境入场事件。"""
    def __init__(self, player, card):
        self.type = "illusion played"
        self.player = player
        self.card = card

    def __str__(self):
        return f"{self.player} plays illusion {self.card.name}"


class IllusionDestroyedEvent(Event):
    """幻境消灭事件。"""
    def __init__(self, player, card):
        self.type = "illusion destroyed"
        self.player = player
        self.card = card

    def __str__(self):
        return f"Illusion {self.card.name} destroyed"


class MorphLeaveEvent(Event):
    """形态牌离场/被消灭事件。

    reason="replace" 表示已有形态被新形态替换而离场（常见于连续形态牌切换）；
    reason="destroy" 表示形态牌随式神气绝而被消灭（或未来被「消灭形态」类效果破坏）。

    供「形态牌离场或被消灭时触发 XXX」类被动（如一目连）监听。
    """
    def __init__(self, hero, morph_id, reason):
        self.type = "morph leave"
        self.hero = hero
        self.morph_id = morph_id
        self.reason = reason

    def __str__(self):
        return f"{self.hero}'s morph #{self.morph_id} left ({self.reason})"


class IllusionDamageEvent(Event):
    """幻境承伤事件（耐久削减）。"""
    def __init__(self, card, damage):
        self.type = "illusion damage"
        self.card = card
        self.damage = damage

    def __str__(self):
        return f"Illusion {self.card.name} takes {self.damage} damage"


class IllusionDurabilityGainEvent(Event):
    """幻境耐久增长事件（耐久增益，与 IllusionDamageEvent 承伤对称）。

    由 Game.gain_illusion_durability 统一入口广播；直接 `durability +=` 不会触发。
    供「当此牌获得幻境耐久时…」类被动监听（如月坠）。
    """
    def __init__(self, card, amount):
        self.type = "illusion durability gain"
        self.card = card
        self.amount = amount

    def __str__(self):
        return f"Illusion {self.card.name} gains {self.amount} durability"


class CookEvent(Event):
    """烹饪触发事件。"""
    def __init__(self, player, hero, ingredient):
        self.type = "cook"
        self.player = player
        self.hero = hero
        self.ingredient = ingredient

    def __str__(self):
        return f"{self.hero.name} cooks {self.ingredient}"


class EnergyGainEvent(Event):
    """充能获得能量事件。"""
    def __init__(self, hero, amount):
        self.type = "energy gain"
        self.hero = hero
        self.amount = amount

    def __str__(self):
        return f"{self.hero.name} gains {self.amount} energy"


class EnergySpendEvent(Event):
    """爆能消耗能量事件。"""
    def __init__(self, hero, amount, card):
        self.type = "energy spend"
        self.hero = hero
        self.amount = amount
        self.card = card

    def __str__(self):
        return f"{self.hero.name} spends {self.amount} energy for {self.card.name}"


class ArmorBreakApplyEvent(Event):
    """破甲被结附事件。"""
    def __init__(self, source, target, amount):
        self.type = "armor break applied"
        self.source = source
        self.target = target
        self.amount = amount

    def __str__(self):
        return f"{self.source} applies {self.amount} armor break to {self.target}"


class HeroKillEvent(Event):
    """式神击杀事件（修复妖刀姬等已引用但从未广播的事件）。

    killer 为击杀者、killed 为被杀者；hero 是 killer 的别名，
    兼容妖刀姬等既有监听器 `e.event.hero == s` 的匹配方式。
    """
    def __init__(self, killer, killed):
        self.type = "hero kill"
        self.killer = killer
        self.killed = killed
        self.hero = killer

    def __str__(self):
        return f"{self.killer} kills {self.killed}"


class AboutToDieEvent(Event):
    """式神将气绝事件：在死亡结算前广播，供响应牌（如「射怪鸟事」）触发。

    在 hero.check_death 置死亡态之前广播；响应牌打出后死亡仍照常发生。
    """
    def __init__(self, hero):
        self.type = "about to die"
        self.hero = hero

    def __str__(self):
        return f"{self.hero} is about to die"


class SummonEvent(Event):
    """召唤事件：召唤一个式神（召唤物）进场。

    hero_class 为 heroes.py 中的式神类名（如 "JinRanBuYe"），
    由 handle_event 的 "summon" 分支实例化并放入战斗区。
    """
    def __init__(self, player, hero_class: str):
        self.type = "summon"
        self.player = player
        self.hero_class = hero_class

    def __str__(self):
        return f"{self.player} summons {self.hero_class}"
