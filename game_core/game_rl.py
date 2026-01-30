from player import Player
from action import *
import random as r
from hero import Hero
from card import Card
from enums import *
from event import Event

class Game:
    def __init__(self, players:list[Player]):
        self.player1:Player = players[0]
        self.player2:Player = players[1]
        self.turn_count = 0
        self.current_player:Player = None
        self.state:str = None
        self.action_queue:list = []


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
        self.broadcast("begin turn", next_player=self.current_player)
        self.turn_count += 1
        self.current_player.state = "playing"
        self.current_player.opponent.state = "waiting"
        self.current_player.attack_available = True
        self.current_player.fire_cnt = 2
        self.current_player.instant_used = False
        self.current_player.picked_upgrade = False
        self.player1.clear_round_effects()
        self.player2.clear_round_effects()
        for hero in self.player1.heroes:
            if hero.state == "dead":
                hero.round_until_alive -= 1
                if hero.round_until_alive <= 0:
                    hero.revive()

        self.current_player.draw()

    
    def check_end_condition(self):
        if self.player1.state == "lost" or self.player2.state == "lost":
            return True
        return False
    

    def broadcast(self, event_type, **kwargs):
        event = Event(event_type, **kwargs)
        for entity in self.iter_entities():
            for listener in entity.listeners:
                if listener.matches(event, entity):
                    listener.trigger(event, entity)

    
    def iter_entities(self):
        yield from self.players
        for player in self.players:
            yield from player.hand
            yield from player.secrets
            yield from player.board
            yield from player.graveyard


    def step(self, player:Player, action:Action):
        self.broadcast(action.type, action)
        if hasattr(action, "revert") and action.revert == True:
            return
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
                if hasattr(action.hero, "on_upgrade"):
                    for event in action.hero.on_upgrade:
                        if type(event(action.hero)).__name__ == "Action":
                            self.step(player, event(action.hero))
                        else:
                            event(action.hero)
                self.current_player.picked_upgrade = True
            
            case "play card":
                if not self.current_player == player:
                    print("trying to play a card when it's not his turn, will ignore")
                    return
                if not action.card.owner == player:
                    print("trying to play a card doesn't owned")
                    return
                if hasattr(action.card, "attributes"):
                    if CardAttributes.INSTANT in action.card.attributes:
                        player.fire_cnt += 1
                if player.fire_cnt <= 0:
                    print("trying to play a card when there's no fire remaining")
                    return
                player.fire_cnt -= 1
                self.play_card(player, action.card, action.target)
            
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
                    self.step(player, EntitiesAttack(action.hero, player.opponent.attack_zone))
                else:
                    self.step(player, EntitiesAttack(action.hero, player.opponent))
                player.fire_cnt -= 1
                player.attack_available = False
            
            case "hero attack by card":
                if not self.current_player == player:
                    print("trying to attack by card when it's not his turn")
                    return
                if not action.hero.is_alive:
                    print("trying to attack with a dead hero by card")
                    return
                player.advance_hero(action.hero)
                if hasattr("buff_atk", action.card):
                    hero.atk += action.card.buff_atk
                if player.opponent.attack_zone is not None:
                    self.attack(action.hero, player.opponent.attack_zone)
                else:
                    self.attack(action.hero, player.opponent)
                if hasattr("buff_atk", action.card):
                    hero.atk -= action.card.buff_atk
            
            case "call selector":
                action.func(action.player, action.target_list, action.card)
            
            case "select target":
                player.selected_targets = [action.target]

            case "give buff":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    if action.attr == "hp":
                        setattr(e, "hp", getattr(e, "hp") + action.value)
                        setattr(e, "current_max_hp", getattr(e, "current_max_hp") + action.value)
                    elif action.attr == "atk":
                        setattr(e, "atk", getattr(e, "atk") + action.value)
            
            case "heal":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    e.hp += action.value
                    if e.hp > e.current_max_hp:
                        e.hp = e.current_max_hp
            
            case "deal damage":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    if type(e).__name__ == "Hero":
                        for h in e.owner.heroes:
                            if h == e:
                                continue
                            if hasattr(h, "on_firendly_hero_take_damage"):
                                for event in h.on_friendly_hero_take_damage:
                                    if event(h) == "negate damage":
                                        return
                                    if type(event(h)).__name__ == "Action":
                                        self.step(player, event(h))
                                    else:
                                        event(h)
                    e.receive_damage(action.value)
                    e.check_death()
                
            case "draw selected card from deck":
                if action.card not in action.player.deck:
                    print("trying to draw a card not in deck")
                    return
                action.player.deck.remove(action.card)
                action.player.hand.append(action.card)


    def play_card(self, player:Player, card:Card, target):
        match card.type:
            case "attack":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        if type(event(card)).__name__ == "Action":
                            self.step(player, event(card))
                        else:
                            event(card)
                for hero in player.heroes:
                    if hero.name == card.hero:
                        attacking_hero = hero
                if hasattr(card, "buff_def"):
                    attacking_hero.defense += card.buff_def
                self.step(player, HeroAttackByCard(attacking_hero, card))
                if hasattr(card, "after_play"):
                    for event in card.after_play:
                        if type(event(card)).__name__ == "Action":
                            self.step(player, event(card))
                        else:
                            event(card)

            case "spell":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        if type(event(card)).__name__ == "Action":
                            self.step(player, event(card))
                        else:
                            event(card)
            
            case "morph":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        if type(event(card)).__name__ == "Action":
                            self.step(player, event(card))
                        else:
                            event(card)
                card.get_corresponding_hero().current_max_hp = card.hp
                card.get_corresponding_hero().atk = card.atk
                card.get_corresponding_hero().hp = card.hp

        player.move_card_to_used(card)
        player.fire_cnt -= 1


    def attack(self, entity1, entity2):
        atk1 = 0
        if hasattr(entity1, "atk"):
            atk1 += entity1.atk
        if hasattr(entity1, "round_buff_atk"):
            atk1 += entity1.round_buff_atk
        atk2 = 0
        if hasattr(entity2, "atk"):
            atk2 += entity2.atk
        if hasattr(entity2, "round_buff_atk"):
            atk2 += entity2.round_buff_atk
        self.step(DealDamage(atk1, entity1, entity2))
        self.step(DealDamage(atk2, entity2, entity1))


    def start_game(self):
        self.player1.opponent = self.player2
        self.player2.opponent = self.player1
        self.player1.game = self
        self.player2.game = self

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
        player_deck_size = len(player.deck)
        opponent_deck_size = len(player.opponent.deck)
        player_hand = [card.name for card in player.hand.cards]
        opponent_hand_size = len(player.opponent.hand)
        player_starting_deck = player.starting_deck
        fire_remaining = player.fire_cnt
        attack_available = player.attack_available
        is_first_player = player.is_first_player
        selected_targets = player.selected_targets
        return {
            "player_state": player_state,
            "game_state": game_state,
            "turn_count": turn_count,
            "player_hp": player_hp,
            "opponent_hp": opponent_hp,
            "player_heroes": player_heroes,
            "opponent_heroes": opponent_heroes,
            "player_deck_size": player_deck_size,
            "opponent_deck_size": opponent_deck_size,
            "player_hand": player_hand,
            "opponent_hand_size": opponent_hand_size,
            "player_starting_deck": player_starting_deck,
            "fire_remaining": fire_remaining,
            "attack_available": attack_available,
            "is_first_player": is_first_player,
            "selected_targets": player.selected_targets,
        }