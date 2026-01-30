from .heroes import *
from .entity import Entity
from .enums import HeroAttributes

class Hero(Entity):
    original_hp: int = 0
    original_atk: int = 0
    hp: int = 0
    atk: int = 0
    current_max_hp: int = 0
    defense: int = 0
    round_buff_atk: int = 0
    level: int = 0
    state: str = None
    is_alive: bool = False
    round_until_alive: int = 0

    def __init__(self, hero_obj):
        self.id = hero_obj.id
        self.morphed_id = 0
        self.entity_type = "hero"
        self.type_name = type(hero_obj).__name__
        self.name = hero_obj.name
        self.owner = None
        self.original_hp = hero_obj.hp
        self.original_atk = hero_obj.atk
        self.current_max_hp = hero_obj.hp
        self.hp = hero_obj.hp
        self.atk = hero_obj.atk
        self.round_buff_atk = 0
        self.defense = 0
        self.level = 0
        self.is_alive = True
        self.round_until_alive = 0
        self.listeners = hero_obj.listeners if hasattr(hero_obj, "listeners") else []
        self.inspiration_atk = 0
        self.inspiration_hp = 0
        self.inspiration_def = 0
        self.attributes = []
        self.counter = hero_obj.counter if hasattr(hero_obj, "counter") else {}

    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"

    def GetHero(id:str):
        hero_class = globals()[id]
        hero_obj = hero_class()
        hero = Hero(hero_obj)
        for attr_name, attr_value in vars(hero_obj).items():
            setattr(hero, attr_name, attr_value)
        return hero

        # should be legacy
        # return Hero(hero_obj)
    
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
            self.round_buff_atk = 0
            if self.owner.attack_zone == self:
                self.owner.attack_zone = None
    
    def assign_owner(self, player):
        self.owner = player
    
    def revive(self):
        self.is_alive = True
        self.hp = self.original_hp
        self.current_max_hp = self.original_hp
        self.atk = self.original_atk
        self.defense = 0
        self.listeners = self.GetHero(self.type_name).listeners
        self.morphed_id = 0
        self.round_until_alive = 0
        self.state = "pending"
    
    def receive_damage(self, damage:int):
        effective_damage = damage - self.defense
        if effective_damage < 0:
            self.defense -= damage
        else:
            self.hp -= effective_damage
            self.defense = 0
        
    def get_permanent_buff(self, field:str, value):
        if field == "hp":
            self.original_hp += value
            self.current_max_hp += value
            self.hp += value
        elif field == "atk":
            self.original_atk += value
            self.atk += value