import sys
sys.path.insert(0, "E:\more_random_project")

from game_core.game import Game
from game_core.player import Player
from game_core.card import Card
from .actions import *
from game_core.action import *
import torch

class RandomOpponentGameEnv:
    def step(self, action):
        original_state = self.game.get_observations(self.player1)
        self.game.step(self.player1, self.decode_action(self.player1, action))
        while self.game.current_player is not self.player1 and not self.game.check_end_condition():
            import random as r
            legal_actions = self.get_legal_actions(self.player2)
            self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        
        done = self.game.check_end_condition()
        new_state = self.game.get_observations(self.player1)
        reward = self.get_reward(original_state, new_state)
        obs = self.get_obs(self.player1)
        return obs, reward, done, {}
        

    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "HuaXinFeng", "HuaXinFeng", "TaoZhiYaoYao", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng", "ShengKai"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "HuaXinFeng", "HuaXinFeng", "TaoZhiYaoYao", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng", "ShengKai"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        while self.game.current_player is not self.player1 and not self.game.check_end_condition():
            import random as r
            legal_actions = self.get_legal_actions(self.player2)
            self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        return self.get_obs(self.player1)

    def get_obs(self, player):
        state = self.game.get_observations(player)  #state: dict
        obs = [0] * 155
        obs[0] = player.state #player_state need to use enum
        obs[1] = 0 # game_state, currently just a placeholder since game_state has no usage now
        obs[2] = state["turn_count"]
        obs[3] = state["player_hp"]
        obs[4] = state["opponent_hp"]
        for i in range(4):
            obs[5 + i * 12] = state["player_heroes"][i].id
            obs[6 + i * 12] = state["player_heroes"][i].morphed_id
            obs[7 + i * 12] = state["player_heroes"][i].current_max_hp
            obs[8 + i * 12] = state["player_heroes"][i].hp
            obs[9 + i * 12] = state["player_heroes"][i].atk
            obs[10 + i * 12] = state["player_heroes"][i].round_buff_atk
            obs[11 + i * 12] = state["player_heroes"][i].defense
            obs[12 + i * 12] = state["player_heroes"][i].level
            obs[13 + i * 12] = state["player_heroes"][i].round_until_alive
            obs[14 + i * 12] = state["player_heroes"][i].inspiration_atk
            obs[15 + i * 12] = state["player_heroes"][i].inspiration_hp
            obs[16 + i * 12] = state["player_heroes"][i].inspiration_def
        for i in range(4):
            obs[53 + i * 12] = state["opponent_heroes"][i].id
            obs[54 + i * 12] = state["opponent_heroes"][i].morphed_id
            obs[55 + i * 12] = state["opponent_heroes"][i].current_max_hp
            obs[56 + i * 12] = state["opponent_heroes"][i].hp
            obs[57 + i * 12] = state["opponent_heroes"][i].atk
            obs[58 + i * 12] = state["opponent_heroes"][i].round_buff_atk
            obs[59 + i * 12] = state["opponent_heroes"][i].defense
            obs[60 + i * 12] = state["opponent_heroes"][i].level
            obs[61 + i * 12] = state["opponent_heroes"][i].round_until_alive
            obs[62 + i * 12] = state["opponent_heroes"][i].inspiration_atk
            obs[63 + i * 12] = state["opponent_heroes"][i].inspiration_hp
            obs[64 + i * 12] = state["opponent_heroes"][i].inspiration_def
        obs[101] = state["player_deck_size"]
        obs[102] = state["opponent_deck_size"]
        # We currently limit the size of hand to 15 cards, can adjust accordingly
        for i in range(len(state["player_hand"])):
            obs[103 + i] = state["player_hand"][i].id
            if i >= 14:
                break
        obs[118] = state["opponent_hand_size"]
        # Hand size should be 32
        for i in range(len(state["player_starting_deck"])):
            obs[119 + i] = Card.GetCard(state["player_starting_deck"][i]).id
        obs[151] = state["fire_remaining"]
        obs[152] = 1 if state["attack_available"] == True else 0
        obs[153] = 1 if state["is_first_player"] == True else 0
        obs[154] = state["pending_card"].id if state["pending_card"] is not None else 0
        return obs
        

    def get_legal_actions(self, player):
        legal_actions_game = player.get_legal_actions()
        legal = []
        for action in legal_actions_game:
            match action.type:
                case "end turn":
                    legal.append(0)
                case "upgrade hero":
                    legal.append(UPGRADE_HERO_START + player.heroes.index(action.hero))
                case "hero attack":
                    legal.append(HERO_ATTACK_START + player.heroes.index(action.hero))
                case "play card":
                    # this limitation is in place because we only have 15 action dim reserved
                    # for play card currently
                    if player.hand.index(action.card) < 15:
                        legal.append(PLAY_CARD_START + player.hand.index(action.card))
                case "select target":
                    if action.target == player.opponent:
                        legal.append(SELECT_TARGET_START + 0)
                    if action.target in player.opponent.heroes:
                        legal.append(SELECT_TARGET_START + 1 + player.opponent.heroes.index(action.target))
                    if action.target in player.heroes:
                        legal.append(SELECT_TARGET_START + 5 + player.heroes.index(action.target))
                    if action.target == player:
                        legal.append(SELECT_TARGET_START + 9)
                case "reject initial pick":
                    legal.append(REJECT_INITIAL_PICK_START + player.hand.index(action.card))
        return legal


    def get_action_masks(self, player):
        legal = self.get_legal_actions(player)
        action_mask = [True] * 39
        for a in legal:
            action_mask[a] = False
        return torch.tensor(action_mask).to(device=torch.device("cuda" if torch.cuda.is_available() else "cpu"))
        

    
    def decode_action(self, player, action_id):
        if action_id == 0:
            return EndTurn()
        if UPGRADE_HERO_START <= action_id < HERO_ATTACK_START:
            hero = player.heroes[action_id - UPGRADE_HERO_START]
            return UpgradeHero(hero)
        if HERO_ATTACK_START <= action_id < PLAY_CARD_START:
            hero = player.heroes[action_id - HERO_ATTACK_START]
            return HeroAttack(hero)
        if PLAY_CARD_START <= action_id < SELECT_TARGET_START:
            card = player.hand[action_id - PLAY_CARD_START]
            return PlayCard(card, None)
        if SELECT_TARGET_START <= action_id < REJECT_INITIAL_PICK_START:
            index = action_id - SELECT_TARGET_START
            if index == 0:
                target = player.opponent
            elif 1 <= index <= 4:
                target = player.opponent.heroes[index - 1]
            elif 5 <= index <= 8:
                target = player.heroes[index - 5]
            elif index == 9:
                target = player
            return SelectTarget(target)
        if REJECT_INITIAL_PICK_START <= action_id < REJECT_INITIAL_PICK_START + len(player.hand):
            card = player.hand[action_id - REJECT_INITIAL_PICK_START]
            return RejectInitialPick(card)


    def get_reward(self, original_state, new_state):
        reward = 0
        if new_state["player_state"] == "lost": reward -= 500
        if new_state["opponent_hp"] <= 0 or new_state["opponent_deck_size"] <= 0: reward += 500
        reward += (new_state["player_hp"] - original_state["player_hp"]) * 2
        reward += (original_state["opponent_hp"] - new_state["opponent_hp"]) * 2
        reward += (original_state["fire_remaining"] - new_state["fire_remaining"]) * 1
        return reward