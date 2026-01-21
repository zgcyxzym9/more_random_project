from cards import *
import copy

class Card:
    def __init__(self, card_obj):
        self.id = card_obj.id
        self.type = card_obj.type
        self.level_req = card_obj.level_req
        self.name = card_obj.name
        if self.type == "attack":
            if hasattr(card_obj, "buff_atk"):
                self.buff_atk = card_obj.buff_atk
        self.attributes = card_obj.attributes if hasattr(card_obj, "attributes") else None
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
    
    def AssignOwner(self, player):
        self.owner = player

