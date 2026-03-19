from .player import Player
from .action import *
import random as r
from .hero import Hero
from .card import Card
from .enums import *
from .event import Event

class Game:
    def __init__(self, players:list[Player]):
        self.player1:Player = players[0]
        self.player2:Player = players[1]
        self.turn_count = 0
        self.current_player:Player = None
        self.state:str = None
        self.action_queue:list = []
        self.pending_card: Card = None


    def pick_first_player(self):
        x = r.random()
        if x < 0.5:
            return self.player1, self.player2
        else:
            return self.player2, self.player1
        

    def begin_turn(self):
        self.broadcast("begin turn", next_player=self.current_player)
        self.current_player.state = PlayerState.PLAYING if self.current_player.initial_pick_reject_left == 0 else PlayerState.INITIAL_PICK
        self.current_player.opponent.state = PlayerState.WAITING
        if self.player1.state != PlayerState.INITIAL_PICK and self.player2.state != PlayerState.INITIAL_PICK:
            self.turn_count += 1
        if self.turn_count == 1:
            self.player1.upgrade_remaining, self.player2.upgrade_remaining = 1, 1
            self.step(self.current_player, UpgradeHero(self.current_player.heroes[0]))
            self.current_player = self.current_player.opponent
            self.step(self.current_player, UpgradeHero(self.current_player.heroes[0]))
            self.current_player = self.current_player.opponent
        self.current_player.attack_available = True
        self.current_player.fire_cnt = 2 if self.turn_count > 1 else 1
        self.current_player.instant_used = False
        self.current_player.upgrade_remaining = 1
        self.current_player.retract_hero()
        if self.current_player.is_first_player and self.turn_count == 13:
            self.current_player.upgrade_remaining += 1
        if not self.current_player.is_first_player and self.turn_count == 6:
            self.current_player.upgrade_remaining += 1
        avail_upgrades = 0
        for hero in self.current_player.heroes:
            avail_upgrades += 3 - hero.level
        self.current_player.upgrade_remaining = min(self.current_player.upgrade_remaining, avail_upgrades)
        if self.turn_count == 2:
            self.current_player.defense = 0
        self.player1.clear_round_effects()
        self.player2.clear_round_effects()
        for hero in self.current_player.heroes:
            if hero.state == "dead":
                hero.round_until_alive -= 1
                if hero.round_until_alive <= 0:
                    hero.revive()

        if self.current_player.state != PlayerState.INITIAL_PICK:
            self.current_player.draw()

    
    def check_end_condition(self):
        if self.player1.state == PlayerState.LOST or self.player2.state == PlayerState.LOST:
            return True
        return False
    

    def broadcast(self, event_type, **kwargs):
        event = Event(event_type, **kwargs)
        for entity in self.iter_entities():
            for listener in entity.listeners:
                if listener.matches(event, entity):
                    listener.trigger(event, entity)

    
    def iter_entities(self):
        yield self.player1
        yield self.player2
        yield from self.player1.hand
        yield from self.player2.hand
        yield from self.player1.heroes
        yield from self.player2.heroes


    def step(self, player:Player, action:Action):
        if action is None:
            return
        self.broadcast(action.type, action=action)
        if hasattr(action, "revert") and action.revert == True:
            return
        match action.type:
            case "reject initial pick":
                if player.state != PlayerState.INITIAL_PICK:
                    print("trying to reject initial pick while playing, will ignore")
                    return
                if type(action.card) is not Card:
                    print("target to reject is not a card")
                    return
                player.hand.remove(action.card)
                player.deck.append(action.card)
                player.draw()
                player.initial_pick_reject_left -= 1
                if player.initial_pick_reject_left == 0:
                    self.step(player, EndTurn())
            
            case "end turn":
                if player.state == PlayerState.INITIAL_PICK:
                    player.state = PlayerState.WAITING
                    player.initial_pick_reject_left = 0
                    self.current_player = self.current_player.opponent
                    self.begin_turn()
                    return
                if not self.current_player == player:
                    print("trying to end a turn when it's not his turn, will ignore")
                    return
                self.current_player = self.current_player.opponent
                self.begin_turn()
            
            case "upgrade hero":
                if not self.current_player == player:
                    print("trying to upgrade a hero when it's not his turn, will ignore")
                    return
                if self.current_player.upgrade_remaining <= 0:
                    print("trying to upgrade multiple heroes, will ignore")
                    return
                if action.hero.level >= 3:
                    print("trying to upgrade a hero already at level 3, will ignore")
                    return
                if type(action.hero) != Hero:
                    print("target to upgrade is not a hero")
                    return
                if action.hero.owner is not player:
                    print(f"hero to upgrade does not belong to player, hero belongs to {action.hero.owner} but player is {player}")
                    return
                for hero in player.heroes:
                    if hero.level < action.hero.level:
                        print("trying to upgrade a hero whose current level is not lowest")
                        return
                action.hero.Upgrade()
                if hasattr(action.hero, "on_upgrade"):
                    for event in action.hero.on_upgrade:
                        if isinstance(event(action.hero), Action):
                            self.step(player, event(action.hero))
                self.current_player.upgrade_remaining -= 1
            
            case "play card":
                if not self.current_player == player:
                    print("trying to play a card when it's not his turn, will ignore")
                    return
                if not action.card.owner == player:
                    print("trying to play a card doesn't owned")
                    return
                if CardAttributes.NO_FIRE_CONSUMPTION in action.card.attributes:
                    player.fire_cnt += 1
                elif CardAttributes.INSTANT in action.card.attributes and player.instant_used == False:
                    player.fire_cnt += 1
                    player.instant_used = True
                if player.fire_cnt <= 0:
                    print("trying to play a card when there's no fire remaining")
                    return
                if action.card.level_req > action.card.get_corresponding_hero().level:
                    print("trying to play a card when corresponding hero level is not enough")
                    return
                if action.card.get_corresponding_hero().state == "dead" and CardAttributes.CAN_PLAY_WHEN_DEAD not in action.card.attributes:
                    print("trying to play a card whose corresponding hero is dead without the ability to play when dead")
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
                    self.attack(action.hero, player.opponent.attack_zone)
                else:
                    self.attack(action.hero, player.opponent)
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
                if player.opponent.attack_zone is not None:
                    self.attack(action.hero, player.opponent.attack_zone)
                else:
                    self.attack(action.hero, player.opponent)
            
            case "call selector":
                action.func(action.player, action.target_list, action.card)
            
            case "select target":
                player.selected_targets = [action.target]
                player.state = PlayerState.PLAYING
                player.candidate_targets = []
                player.pending_card = None
                self.play_card(player, self.pending_card,)
                self.pending_card = None
                player.selected_targets = None

            case "give buff":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    if action.attr == "hp":
                        setattr(e, "hp", getattr(e, "hp") + action.value)
                        setattr(e, "current_max_hp", getattr(e, "current_max_hp") + action.value)
                    elif action.attr == "atk":
                        setattr(e, "atk", getattr(e, "atk") + action.value)
                    elif action.attr == "round_buff_atk":
                        setattr(e, "round_buff_atk", getattr(e, "round_buff_atk") + action.value)
            
            case "heal":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                    e.hp += action.value
                    if e.hp > e.current_max_hp:
                        e.hp = e.current_max_hp
            
            case "deal damage":
                for e in action.target:
                    if e.state == "dead":
                        continue
                    if isinstance(e, Hero):
                        if e.level == 0:
                            continue
                        for h in e.owner.heroes:
                            if h == e:
                                continue
                            if hasattr(h, "on_firendly_hero_take_damage"):
                                for event in h.on_friendly_hero_take_damage:
                                    if event(h) == "negate damage":
                                        return
                                    if isinstance(event(h), Action):
                                        self.step(player, event(h))
                    e.receive_damage(action.value)
                    e.check_death()
                
            case "draw selected card from deck":
                if action.card not in action.player.deck.cards:
                    print("trying to draw a card not in deck")
                    return
                action.player.deck.remove(action.card)
                action.player.hand.append(action.card)
            
            case "revive":
                if action.target.state != "dead":
                    print("trying to revive a non-dead target")
                    return
                action.target.revive()
            
            case _:
                print(f"stepping with the game with undefined action type {action.type}, check code!")


    def play_card(self, player:Player, card:Card, target=None):
        if card.select_target is not None:
            if player.selected_targets is None:
                self.pending_card = card
                for event in card.select_target:
                    event(card)
                player.state = PlayerState.SELECTING_TARGET
                return
                
        match card.type:
            case "attack":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        # it's worth noting that if event(card) is a function, it will
                        # be executed while checking if it's an Action type.
                        if isinstance(event(card), Action):
                            self.step(player, event(card))
                for hero in player.heroes:
                    if hero.type_name == card.hero:
                        attacking_hero = hero
                if hasattr(card, "buff_atk"):
                    attacking_hero.atk += card.buff_atk
                if hasattr(card, "buff_def"):
                    attacking_hero.defense += card.buff_def
                self.step(player, HeroAttackByCard(attacking_hero, card))
                if hasattr(card, "after_play"):
                    for event in card.after_play:
                        if isinstance(event(card), Action):
                            self.step(player, event(card))
                if hasattr(card, "buff_atk"):
                    attacking_hero.atk -= card.buff_atk

            case "spell":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        if isinstance(event(card), Action):
                            self.step(player, event(card))
            
            case "morph":
                if hasattr(card, "on_play"):
                    for event in card.on_play:
                        if isinstance(event(card), Action):
                            self.step(player, event(card))
                card.get_corresponding_hero().current_max_hp = card.hp
                card.get_corresponding_hero().atk = card.atk
                card.get_corresponding_hero().hp = card.hp

        player.move_card_to_used(card)
        player.selected_targets = None


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
        self.step(self.current_player, DealDamage(atk1, entity1, [entity2,]))
        self.step(self.current_player, DealDamage(atk2, entity2, [entity1,]))


    def start_game(self):
        self.player1.opponent = self.player2
        self.player2.opponent = self.player1
        self.player1.game = self
        self.player2.game = self
        self.turn_count = 0

        first, second = self.pick_first_player()
        self.player1 = first
        self.player2 = second
        self.player1.is_first_player = True
        self.player2.is_first_player = False
        self.current_player = first

        self.player1.start_game()
        self.player2.start_game()

        self.state = "playing"

    
    def play(self):
        self.start_game()
        self.begin_turn()

        while True:
            action = self.current_player.agent.act()
            self.step(self.current_player, action)
    

    def get_observations(self, player:Player):
        player_state = player.state
        game_state = self.state
        turn_count = self.turn_count
        player_hp = player.hp
        player_defense = player.defense
        opponent_hp = player.opponent.hp
        opponent_defense = player.opponent.defense
        player_heroes = player.heroes.copy()
        opponent_heroes = player.opponent.heroes.copy()
        player_deck_size = len(player.deck)
        opponent_deck_size = len(player.opponent.deck)
        player_hand = player.hand.cards.copy()
        opponent_hand_size = len(player.opponent.hand)
        player_starting_deck = player.starting_deck
        fire_remaining = player.fire_cnt
        attack_available = player.attack_available
        is_first_player = player.is_first_player
        pending_card = player.pending_card
        player_used_card = player.used_card
        opponent_used_card = player.opponent.used_card
        return {
            "player_state": player_state,
            "game_state": game_state,
            "turn_count": turn_count,
            "player_hp": player_hp,
            "player_defense": player_defense,
            "opponent_hp": opponent_hp,
            "opponent_defense": opponent_defense,
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
            "pending_card": pending_card,
            "player_used_card": player_used_card,
            "opponent_used_card": opponent_used_card
        }
    

    def get_obs_tensor(self, player: Player, device) -> "torch.Tensor":
        """
        用 numpy 数组在 CPU 上完成所有赋值，最后一次 .to(device)。
        避免原来逐元素写 GPU tensor 导致的 240 次 Python→CUDA 同步。
        """
        import torch
        import numpy as np
        opponent = player.opponent
        buf = np.zeros(240, dtype=np.float32)   # 全在 CPU，无 CUDA 开销

        buf[0] = player.state
        buf[2] = self.turn_count
        buf[3] = player.hp
        buf[4] = opponent.hp

        # ── 己方英雄 ──────────────────────────────────────────
        for i, h in enumerate(player.heroes):
            base = 5 + i * 12
            buf[base]      = h.id
            buf[base + 1]  = h.morphed_id
            buf[base + 2]  = h.current_max_hp
            buf[base + 3]  = h.hp
            buf[base + 4]  = h.atk
            buf[base + 5]  = h.round_buff_atk
            buf[base + 6]  = h.defense
            buf[base + 7]  = h.level
            buf[base + 8]  = h.round_until_alive
            buf[base + 9]  = h.inspiration_atk
            buf[base + 10] = h.inspiration_hp
            buf[base + 11] = h.inspiration_def

        # ── 对手英雄 ──────────────────────────────────────────
        for i, h in enumerate(opponent.heroes):
            base = 53 + i * 12
            buf[base]      = h.id
            buf[base + 1]  = h.morphed_id
            buf[base + 2]  = h.current_max_hp
            buf[base + 3]  = h.hp
            buf[base + 4]  = h.atk
            buf[base + 5]  = h.round_buff_atk
            buf[base + 6]  = h.defense
            buf[base + 7]  = h.level
            buf[base + 8]  = h.round_until_alive
            buf[base + 9]  = h.inspiration_atk
            buf[base + 10] = h.inspiration_hp
            buf[base + 11] = h.inspiration_def

        buf[101] = len(player.deck)
        buf[102] = len(opponent.deck)

        # ── 手牌（最多 12 张）────────────────────────────────
        for i, c in enumerate(player.hand.cards):
            if i >= 12: break
            buf[103 + i] = c.id

        buf[115] = len(opponent.hand)

        # ── 起始牌组（最多 32 张）────────────────────────────
        for i, name in enumerate(player.starting_deck):
            if i >= 32: break
            buf[116 + i] = Card.GetCard(name).id

        buf[148] = player.fire_cnt
        buf[149] = 1.0 if player.attack_available else 0.0
        buf[150] = 1.0 if player.is_first_player   else 0.0
        buf[151] = player.pending_card.id if player.pending_card is not None else 0.0

        # ── 己方已用牌（最多 32 张）──────────────────────────
        for i, c in enumerate(player.used_card):
            if i >= 32: break
            buf[152 + i] = c.id

        # ── 对手已用牌（最多 32 张）──────────────────────────
        for i, c in enumerate(opponent.used_card):
            if i >= 32: break
            buf[184 + i] = c.id

        # ── 正在攻击的己方英雄 ────────────────────────────────
        for h in player.heroes:
            if h.state == "attacking":
                buf[216] = h.id;           buf[217] = h.morphed_id
                buf[218] = h.current_max_hp; buf[219] = h.hp
                buf[220] = h.atk;          buf[221] = h.round_buff_atk
                buf[222] = h.defense;      buf[223] = h.level
                buf[224] = h.round_until_alive
                buf[225] = h.inspiration_atk
                buf[226] = h.inspiration_hp
                buf[227] = h.inspiration_def
                break

        # ── 正在攻击的对手英雄 ────────────────────────────────
        for h in opponent.heroes:
            if h.state == "attacking":
                buf[228] = h.id;           buf[229] = h.morphed_id
                buf[230] = h.current_max_hp; buf[231] = h.hp
                buf[232] = h.atk;          buf[233] = h.round_buff_atk
                buf[234] = h.defense;      buf[235] = h.level
                buf[236] = h.round_until_alive
                buf[237] = h.inspiration_atk
                buf[238] = h.inspiration_hp
                buf[239] = h.inspiration_def
                break

        # ── 一次性传到 device ────────────────────────────────
        return torch.from_numpy(buf).to(device)