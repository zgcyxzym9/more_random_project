from .cards import *
from .entity import Entity
import copy

class Card(Entity):
    def __init__(self, card_obj):
        self.id = card_obj.id
        self.entity_type = "card"
        self.type = card_obj.type
        self.hero = card_obj.hero
        self.level_req = card_obj.level_req
        self.name = card_obj.name
        if self.type == "attack":
            if hasattr(card_obj, "buff_atk"):
                self.buff_atk = card_obj.buff_atk
            if hasattr(card_obj, "buff_def"):
                self.buff_def = card_obj.buff_def
        if hasattr(card_obj, "on_play"):
            self.on_play = card_obj.on_play
        if self.type == "morph":
            self.hp = card_obj.hp
            self.atk = card_obj.atk
        self.attributes = card_obj.attributes if hasattr(card_obj, "attributes") else []
        self.require_target = card_obj.require_target if hasattr(card_obj, "require_target") else None
        self.select_target = card_obj.select_target if hasattr(card_obj, "select_target") else None
        self.listeners = card_obj.listeners if hasattr(card_obj, "listeners") else []
        self.owner = None

    def __str__(self):
        return f"{self.name}"
    
    def __repr__(self):
        return f"{self.name}"

    def GetCard(id:str):
        card_class = globals()[id]
        card_obj = card_class()
        return Card(card_obj)
    
    def GetCards(ids:list[str]):
        cards = []
        for id in ids:
            cards.append(Card.GetCard(id))
        return cards.copy()
    
    def assign_owner(self, player):
        self.owner = player

    def get_corresponding_hero(self):
        from .hero import Hero
        for hero in self.owner.heroes:
            if Hero.GetHero(self.hero).name == hero.name:
                return hero