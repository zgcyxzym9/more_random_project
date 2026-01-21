from heroes import *

class Hero:
    hp: int = 0
    atk: int = 0
    defense: int = 0
    level: int = 0
    state: str = None
    is_alive: bool = False
    round_until_alive: int = 0

    def __init__(self, hero_obj):
        self.id = hero_obj.id
        self.name = hero_obj.name
        self.owner = None
        self.hp = hero_obj.hp
        self.atk = hero_obj.atk
        self.defense = 0
        self.level = 0
        self.is_alive = True
        self.round_until_alive = 0

    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"

    def GetHero(id:str):
        hero_class = globals()[id]
        hero_obj = hero_class()
        return Hero(hero_obj)
    
    def GetHeroes(ids:list[str]):
        heroes = []
        for id in ids:
            heroes.append(Hero.GetHero(id))
        return heroes
    
    def Upgrade(self):
        self.level += 1
    
    def check_death(self):
        if self.hp <= 0:
            self.is_alive = False
            self.state = "dead"
            self.round_until_alive = 3
            if self.owner.attack_zone == self:
                self.owner.attack_zone = None