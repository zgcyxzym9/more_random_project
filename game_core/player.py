from game_core import cards

from .action import *
from .utils import CardList
from .card import Card
from .hero import Hero
from .entity import Entity
from .enums import *
import os
import random as r


# Player: generic, can directly use for training
class Player():
    def __init__(self, deck:list[str], heroes:list[str]):
        from .game import Game
        from .agent import Agent
        self.game: Game = None
        self.entity_type = "player"
        self.opponent: Player = None
        self.agent: Agent = None
        self.is_first_player: bool = False
        self.heroes: list[Hero] = Hero.GetHeroes(heroes)
        self.starting_deck = deck
        self.state = PlayerState.WAITING
        self.hp: int = 30
        self.current_max_hp: int = 30
        self.defense: int = 0
        self.deck: CardList = None
        self.hand: CardList = None
        self.used_card: CardList = None
        self.attack_zone: Hero = None
        self.attack_available: bool = False
        self.fire_cnt: int = 0
        self.instant_used: bool = True
        self.upgrade_remaining: int = 0
        self.candidate_targets = []
        self.pending_card: Card = None
        self.selected_targets = None
        self.listeners = []
        self.initial_pick_reject_left = 3

    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        r.shuffle(self.heroes)
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.state = PlayerState.INITIAL_PICK
    
    def draw(self):
        if self.deck.is_empty():
            self.hp = 0
            self.state = PlayerState.LOST
            return
        drawn_card = self.deck.pop(0)
        # If you have more than 12 cards, you still draw the card but immediately discard it
        if len(self.hand.cards) >= 12:
            self.used_card.append(drawn_card)
            return
        self.hand.append(drawn_card)
    
    def reject_initial_card(self, id):
        rejected_card = self.hand.pop(id-1)
        self.deck.append(rejected_card)
    
    def assign_agent(self):
        from agent import Agent, IOAgent
        self.agent = IOAgent(self.game, self)
    
    def advance_hero(self, hero:Hero):
        if self.attack_zone is not None:
            self.attack_zone.state = "pending"
        self.attack_zone = hero
        hero.state = "attacking"
        hero.atk += hero.inspiration_atk
        hero.inspiration_atk = 0
        hero.defense += hero.inspiration_def
        hero.inspiration_def = 0
    
    def retract_hero(self):
        if self.attack_zone is not None:
            self.attack_zone.state = "pending"
            self.attack_zone = None
    
    def check_death(self):
        if self.hp <=0:
            self.state = PlayerState.LOST
    
    def clear_round_effects(self):
        for hero in self.heroes:
            hero.round_buff_atk = 0
    
    def move_card_to_used(self, card:Card):
        self.hand.remove(card)
        self.used_card.append(card)
    
    def receive_damage(self, damage:int):
        effective_damage = damage - self.defense
        if effective_damage < 0:
            self.defense -= damage
        else:
            self.hp -= effective_damage
            self.defense = 0
    
    def GiveCardToHand(self, cards:list[str]):
        for card in cards:
            card_obj = Card.GetCard(card)
            card_obj.assign_owner(self)
            if len(self.hand.cards) >= 12:
                self.used_card.append(card_obj)
                return
            self.hand.append(card_obj)
    
    def GiveCardToDeck(self, cards:list[str]):
        for card in cards:
            card_obj = Card.GetCard(card)
            card_obj.assign_owner(self)
            self.deck.append(card_obj)
    
    def can_end_turn(self):
        return self.game.current_player is self and self.upgrade_remaining == 0
    
    def get_legal_actions(self):
        match self.state:
            case PlayerState.INITIAL_PICK:
                actions = [RejectInitialPick(card) for card in self.hand]
                actions.append(EndTurn())
                return actions
            
            case PlayerState.PLAYING:
                actions = []
                if self.upgrade_remaining > 0:
                    for hero in self.heroes:
                        is_min_level = True
                        for hero_tmp in self.heroes:
                            if hero_tmp.level < hero.level:
                                is_min_level = False
                        if hero.level < 3 and is_min_level:
                            actions.append(UpgradeHero(hero))
                    return actions
                actions.append(EndTurn())
                for card in self.hand:
                    if card.require_target is not None and [] in [req(card) for req in card.require_target]:
                        continue
                    if card.get_corresponding_hero().state == "dead" and CardAttributes.CAN_PLAY_WHEN_DEAD not in card.attributes:
                        continue
                    if card.level_req > card.get_corresponding_hero().level:
                        continue
                    if self.fire_cnt > 0:
                        actions.append(PlayCard(card, None))
                    elif CardAttributes.INSTANT in card.attributes and self.instant_used == False:
                        actions.append(PlayCard(card, None))
                    elif CardAttributes.NO_FIRE_CONSUMPTION in card.attributes:
                        actions.append(PlayCard(card, None))
                for hero in self.heroes:
                    if hero.is_alive and hero.level > 0 and self.attack_available and self.fire_cnt > 0:
                        actions.append(HeroAttack(hero))
                return actions
            
            case PlayerState.SELECTING_TARGET:
                actions = [SelectTarget(target) for target in self.candidate_targets]
                return actions

            case _:
                print(f"getting legal actions with an undefined state {self.state}, check code!")
                return []


"""
InferencePlayer: for full game inference, DO NOT USE FOR TRAINING OR 
PLAYING WITH THE SIMULATOR
"""
class InferencePlayer(Player):
    def __init__(self, deck:list[str], heroes:list[str]):
        super().__init__(deck, heroes)
        root_dict = "E:/more_random_project"
        with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
            self.card_names = [line.strip() for line in file if line.strip()]
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            self.hero_names = [line.strip() for line in file if line.strip()]

    # This version of start_game will not shuffle the hero list
    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.state = PlayerState.INITIAL_PICK

    """
    The implementation of this draw function will generate a card from 
    nowhere and pop a random card from the deck, and therefore should only 
    be used in circumstances where you will determine drawn cards manually.
    """
    def draw(self):
        from rl.utils import match_by_caps
        while True:
            _ = input(f"Please enter the name of the card you just drawn: ")
            card_name = match_by_caps(self.card_names, _)
            if card_name is not None:
                if len(self.hand.cards) >= 12:
                    print("Your hand is full, the drawn card will be discarded.")
                    self.used_card.append(Card.GetCard(card_name).assign_owner(self))
                else:
                    self.GiveCardToHand([card_name])
                break
        self.deck.pop()

"""
InferenceOpponent: for full game inference, DO NOT USE FOR TRAINING OR 
PLAYING WITH THE SIMULATOR
"""
class InferenceOpponent(Player):
    def __init__(self, deck:list[str], heroes:list[str]):
        super().__init__(deck, heroes)
        root_dict = "E:/more_random_project"
        with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
            self.card_names = [line.strip() for line in file if line.strip()]
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            self.hero_names = [line.strip() for line in file if line.strip()]

    # This version of start_game will not shuffle the hero list
    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
        if not self.is_first_player:
            self.defense = 5
        for i in range(5):
            self.draw()
        self.state = PlayerState.INITIAL_PICK