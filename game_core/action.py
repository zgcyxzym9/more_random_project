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

class SelectTarget(Action):
    def __init__(self, target):
        self.type = "select target"
        self.target = target
    
    def __str__(self):
        return f"Select target {self.target}"