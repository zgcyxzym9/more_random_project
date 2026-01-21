from card import Card
import random as r
from action import *

class CardList(list[Card]):
    def __init__(self, cards:list[Card]):
        self.cards = cards
    
    def __getitem__(self, index):
        return self.cards[index]

    def __len__(self):
        return len(self.cards)

    def __iter__(self):
        return iter(self.cards)

    def append(self, card):
        self.cards.append(card)
    
    def pop(self, index=-1):
        return self.cards.pop(index)
    
    def remove(self, value):
        return self.cards.remove(value)

    def shuffle(self):
        r.shuffle(self.cards)

    def is_empty(self):
        return len(self.cards) == 0