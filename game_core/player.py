from action import *
from utils import CardList
from card import Card
from hero import Hero

class Player:
    def __init__(self, deck:list[str], heroes:list[str]):
        from game import Game
        from agent import Agent
        self.game: Game = None
        self.opponent: Player = None
        self.agent: Agent = None
        self.is_first_player: bool = False
        self.heroes: list[Hero] = Hero.GetHeroes(heroes)
        self.starting_deck = deck
        self.state: str = None
        self.hp: int = 30
        self.defense: int = 0
        self.deck: CardList = None
        self.hand: CardList = None
        self.used_card: CardList = None
        self.attack_zone: Hero = None
        self.attack_available: bool = False
        self.fire_cnt: int = 0
        self.instant_used: bool = True
        self.picked_upgrade: bool = True
        self.candidate_targets = []
        self.pending_card: Card = None
        self.selected_targets = []

    def start_game(self):
        self.deck = CardList(Card.GetCards(self.starting_deck))
        for card in self.deck:
            card.assign_owner(self)
        self.deck.shuffle()
        for hero in self.heroes:
            hero.assign_owner(self)
        self.hand = CardList([])
        self.used_card = CardList([])
    
    def draw(self):
        if self.deck.is_empty():
            # should automatically concede here
            print("deck is empty!")
            return
        drawn_card = self.deck.pop(0)
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
    
    def check_death(self):
        if self.hp <=0:
            self.state = "lost"
    
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
    
    def get_legal_actions(self):
        match self.state:
            case "initial pick":
                actions = [RejectInitialPick(card) for card in self.hand]
                actions.append(EndTurn())
                return actions
            
            case "playing":
                actions = []
                actions.append(EndTurn())
                if not self.picked_upgrade:
                    for hero in self.heroes:
                        is_min_level = True
                        for hero_tmp in self.heroes:
                            if hero_tmp.level < hero.level:
                                is_min_level = False
                        if hero.level < 3 and is_min_level:
                            actions.append(UpgradeHero(hero))
                    return actions
                for card in self.hand:
                    if self.fire_cnt > 0:
                        # for simplicity, we will not consider targets for now
                        # WIP here!!!!!!!!!!!!!!!!!!!!!!
                        actions.append(PlayCard(card, None))
                for hero in self.heroes:
                    if hero.is_alive and self.attack_available and self.fire_cnt > 0:
                        actions.append(HeroAttack(hero))
                return actions
            
            case "selecting target":
                actions = [SelectTarget(target) for target in self.candidate_targets]
                return actions

            case _:
                print(f"getting legal actions with an undefined state {self.state}, check code!")
                return []