from utils import *

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
    def __init__(self, card, target):
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
    def __init__(self, attr, value, target):
        self.type = "give buff"
        self.attr = attr
        self.value = value
        self.target = target

class Heal(Action):
    def __init__(self, value, target):
        self.type = "heal"
        self.value = value
        self.target = target

class DealDamage(Action):
    def __init__(self, value, target):
        self.type = "deal damage"
        self.value = value
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