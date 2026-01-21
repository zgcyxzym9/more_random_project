from player import Player
from action import Action
import random as r
from hero import Hero
from card import Card

class Game:
    def __init__(self, players:list[Player]):
        self.player1:Player = players[0]
        self.player2:Player = players[1]
        self.turn_count = 0
        self.current_player:Player = None
        self.state:str = None


    def pick_first_player(self):
        x = r.random()
        if x < 0.5:
            return self.player1, self.player2
        else:
            return self.player2, self.player1
        

    def initial_pick(self):
        self.player1.state = "initial pick"
        self.player2.state = "initial pick"
        for i in range(5):
            self.player1.draw()
        
        for i in range(3):
            action = self.player1.agent.act()
            self.step(self.player1, action)
        
        for i in range(5):
            self.player2.draw()
        
        for i in range(3):
            action = self.player2.agent.act()
            self.step(self.player2, action)

        self.state = "playing"
        self.current_player = self.player1
    

    def begin_turn(self):
        self.turn_count += 1
        self.current_player.state = "playing"
        self.current_player.opponent.state = "waiting"
        self.current_player.attack_available = True
        self.current_player.fire_cnt = 2
        self.current_player.instant_used = False
        self.current_player.picked_upgrade = False

        self.current_player.draw()

    
    def check_end_condition(self):
        if self.player1.state == "lost" or self.player2.state == "lost":
            return True
        return False
    

    def step(self, player:Player, action:Action):
        match action.type:
            case "reject initial pick":
                if self.state != "initial pick":
                    print("trying to reject initial pick while playing, will ignore")
                    return
                if type(action.card) is not Card:
                    print("target to reject is not a card")
                    return
                player.hand.remove(action.card)
                player.deck.append(action.card)
                player.hand.append(player.deck.pop(0))
            
            case "end turn":
                if not self.current_player == player:
                    print("trying to end a turn when it's not his turn, will ignore")
                    return
                self.current_player = self.current_player.opponent
                self.begin_turn()
            
            case "upgrade hero":
                if not self.current_player == player:
                    print("trying to upgrade a hero when it's not his turn, will ignore")
                    return
                if self.current_player.picked_upgrade:
                    print("trying to upgrade multiple heroes, will ignore")
                    return
                if action.hero.level >= 3:
                    print("trying to upgrade a hero already at level 3, will ignore")
                    return
                if type(action.hero) != Hero:
                    print("target to upgrade is not a hero")
                    return
                if action.hero not in player.heroes:
                    print("hero to upgrade does not belong to player")
                    return
                for hero in player.heroes:
                    if hero.level < action.hero.level:
                        print("trying to upgrade a hero whose current level is not lowest")
                        return
                action.hero.Upgrade()
                self.current_player.picked_upgrade = True
            
            case "play card":
                if not self.current_player == player:
                    print("trying to play a card when it's not his turn, will ignore")
                    return
                if not action.card.owner == player:
                    print("trying to play a card doesn't owned")
                    return
            
            case "hero attack":
                if not self.current_player == player:
                    print("trying to attack when it's not his turn")
                    return
                if not action.hero.is_alive:
                    print("trying to attack with a dead hero")
                    return
                if player.attack_available == False:
                    print("trying to attack when attack is not available")
                    return
                if player.fire_cnt <= 0:
                    print("trying to attack when there's no fire left")
                    return
                if not action.hero.owner == player:
                    print("trying to let a non-friendly hero attack")
                    return
                player.advance_hero(action.hero)
                if player.opponent.attack_zone is not None:
                    self.attack(action.hero, player.opponent.attack_zone)
                else:
                    self.attack(action.hero, player.opponent)
                player.fire_cnt -= 1
                player.attack_available = False



    def attack(self, entity1, entity2):
        entity2.hp -= entity1.atk if hasattr(entity1, "atk") else 0
        entity1.hp -= entity2.atk if hasattr(entity2, "atk") else 0
        entity1.check_death()
        entity2.check_death()


    def start_game(self):
        self.player1.opponent = self.player2
        self.player2.opponent = self.player1

        first, second = self.pick_first_player()
        self.player1 = first
        self.player2 = second
        self.player1.is_first_player = True
        self.player2.is_first_player = False

        self.player1.start_game()
        self.player2.start_game()

        self.state = "initial pick"

    
    def play(self):
        self.start_game()
        self.pick_first_player()
        self.initial_pick()
        self.begin_turn()

        while True:
            print("game:", self.current_player)
            action = self.current_player.agent.act()
            self.step(self.current_player, action)
    

    def get_observations(self, player:Player):
        player_state = player.state
        game_state = self.state
        turn_count = self.turn_count
        player_hp = player.hp
        opponent_hp = player.opponent.hp
        player_heroes = player.heroes
        opponent_heroes = player.opponent.heroes
        player_deck_volume = len(player.deck)
        opponent_deck_volume = len(player.opponent.deck)
        player_hand = [card.name for card in player.hand.cards]
        opponent_hand_size = len(player.opponent.hand)
        player_starting_deck = player.starting_deck
        fire_remaining = player.fire_cnt
        attack_available = player.attack_available
        is_first_player = player.is_first_player
        return {
            "player_state": player_state,
            "game_state": game_state,
            "turn_count": turn_count,
            "player_hp": player_hp,
            "opponent_hp": opponent_hp,
            "player_heroes": player_heroes,
            "opponent_heroes": opponent_heroes,
            "player_deck_volume": player_deck_volume,
            "opponent_deck_volume": opponent_deck_volume,
            "player_hand": player_hand,
            "opponent_hand_size": opponent_hand_size,
            "player_starting_deck": player_starting_deck,
            "fire_remaining": fire_remaining,
            "attack_available": attack_available,
            "is_first_player": is_first_player,
        }