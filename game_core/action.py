class Action:
    type: str = None

class RejectInitialPick(Action):
    def __init__(self, card):
        self.card = card
        self.type = "reject initial pick"

    def __str__(self):
        return f"Reject initial pick: {self.card.name}"

class EndTurn(Action):
    def __init__(self):
        self.type = "end turn"

    def __str__(self):
        return f"End turn"

class UpgradeHero(Action):
    def __init__(self, hero):
        self.type = "upgrade hero"
        self.hero = hero

    def __str__(self):
        return f"Upgrade hero {self.hero.name}"

class PlayCard(Action):
    def __init__(self, card, target=None, use_blast: bool = False, use_charge: bool = False):
        self.type = "play card"
        self.card = card
        self.target = target
        self.use_blast = use_blast   # 爆能：额外消耗能量触发增强
        self.use_charge = use_charge # 蓄力：出牌动作=发起蓄力（step 拦截）；挂起重放=蓄力结算

    def __str__(self):
        if self.use_blast:
            return f"Play card {self.card.name} (blast)"
        if self.use_charge:
            return f"Play card {self.card.name} (charge)"
        return f"Play card {self.card.name}"

class HeroAttack(Action):
    def __init__(self, hero):
        self.type = "hero attack"
        self.hero = hero

    def __str__(self):
        return f"Attack with {self.hero.name}"

class SelectTarget(Action):
    def __init__(self, target):
        self.type = "select target"
        self.target = target

    def __str__(self):
        return f"Select target {self.target}"


# ── 新增 Action 类型 (Phase 1) ──────────────────────────────────────────────

class MoveHero(Action):
    """将式神移入/移出战斗区（鸦天狗机制）。

    to_battle=True  → 移入战斗区
    to_battle=False → 移出战斗区（回到准备区）
    """
    def __init__(self, hero, to_battle: bool = True):
        self.type = "move hero"
        self.hero = hero
        self.to_battle = to_battle

    def __str__(self):
        direction = "to battle" if self.to_battle else "to standby"
        return f"Move {self.hero.name} {direction}"


class SelectOption(Action):
    """从多个效果/选项中选择一个。

    用于：幻境选择（未来）、多效果卡牌选择。
    """
    def __init__(self, option_index: int):
        self.type = "select option"
        self.option_index = option_index

    def __str__(self):
        return f"Select option {self.option_index}"
