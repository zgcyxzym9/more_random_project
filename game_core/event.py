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
    def __init__(self, value, source, target):
        self.type = "deal damage"
        self.value = value
        self.source = source
        self.target = target
    
    def __str__(self):
        return f"Dealing {self.value} damage to {self.target} from {self.source}"

class Revive(Event):
    def __init__(self, source, target):
        self.type = "revive"
        self.source = source
        self.target = target

class HeroAttackEvent(Event):
    def __init__(self, player, hero, card=None):
        self.type = "hero attack event"
        self.player = player
        self.hero = hero
        self.card = card

    def __str__(self):
        return f"Attack with {self.hero.name}" + (f" by {self.card.name}" if self.card else "")
    
class EntitiesAttack(Event):
    def __init__(self, entity1, entity2):
        self.type = "entities attack"
        self.entity1 = entity1
        self.entity2 = entity2

class DrawSelectedCardFromDeck(Event):
    def __init__(self, player, card):
        self.type = "draw selected card from deck"
        self.player = player
        self.card = card