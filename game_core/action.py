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
    def __init__(self, card, target = None):
        self.type = "play card"
        self.card = card
        self.target = target
    
    def __str__(self):
        return f"Play card {self.card.name}"

class HeroAttack(Action):
    def __init__(self, hero):
        self.type = "hero attack"
        self.hero = hero
    
    def __str__(self):
        return f"Attack with {self.hero.name}"

class HeroAttackByCard(Action):
    def __init__(self, hero, card):
        self.type = "hero attack by card"
        self.hero = hero
        self.card = card
    
    def __str__(self):
        return f"Attack with {self.hero.name} by {self.card.name}"

class GiveBuff(Action):
    def __init__(self, attr, value, source, target):
        self.type = "give buff"
        self.attr = attr
        self.value = value
        self.source = source
        self.target = target

class Heal(Action):
    def __init__(self, value, source, target):
        self.type = "heal"
        self.value = value
        self.source = source
        self.target = target
    
    def __str__(self):
        return f"Healing {self.target} for {self.value} from {self.source}"

class DealDamage(Action):
    def __init__(self, value, source, target):
        self.type = "deal damage"
        self.value = value
        self.source = source
        self.target = target

class CallSelector(Action):
    def __init__(self, func, player, target_list, card):
        self.type = "call selector"
        self.func = func
        self.player = player
        self.target_list = target_list
        self.card = card

class SelectTarget(Action):
    def __init__(self, target):
        self.type = "select target"
        self.target = target
    
    def __str__(self):
        return f"Select target {self.target}"

class EntitiesAttack(Action):
    def __init__(self, entity1, entity2):
        self.type = "entities attack"
        self.entity1 = entity1
        self.entity2 = entity2

class DrawSelectedCardFromDeck(Action):
    def __init__(self, player, card):
        self.type = "draw selected card from deck"
        self.player = player
        self.card = card