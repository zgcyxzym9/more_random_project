import sys
sys.path.insert(0, "E:/more_random_project")

from game_core.game import Game
from game_core.player import Player
from game_core.card import Card
from rl.actor_critic import ActorCritic
from rl_dqn.agent import DoubleDQNAgent
from .actions import *
from game_core.action import *
import torch
import os
import random as r


class Env:
    def __init__(self):
        root_dict = "E:/more_random_project"
        with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
            card_names = [line.strip() for line in file if line.strip()]
        with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
            hero_names = [line.strip() for line in file if line.strip()]


    def step(self, action):
        raise NotImplementedError
        

    def reset(self):
        raise NotImplementedError


    def get_obs(self, player):
        state = self.game.get_observations(player)  #state: dict
        obs = [0] * 243
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
        for i in range(len(state["player_used_card"])):
            obs[155 + i] = state["player_used_card"][i].id
        for i in range(len(state["opponent_used_card"])):
            obs[187 + i] = state["opponent_used_card"][i].id
        for hero in state["player_heroes"]:
            if hero.state == "attacking":
                obs[219] = hero.id
                obs[220] = hero.morphed_id
                obs[221] = hero.current_max_hp
                obs[222] = hero.hp
                obs[223] = hero.atk
                obs[224] = hero.round_buff_atk
                obs[225] = hero.defense
                obs[226] = hero.level
                obs[227] = hero.round_until_alive
                obs[228] = hero.inspiration_atk
                obs[229] = hero.inspiration_hp
                obs[230] = hero.inspiration_def
        for hero in state["opponent_heroes"]:
            if hero.state == "attacking":
                obs[231] = hero.id
                obs[232] = hero.morphed_id
                obs[233] = hero.current_max_hp
                obs[234] = hero.hp
                obs[235] = hero.atk
                obs[236] = hero.round_buff_atk
                obs[237] = hero.defense
                obs[238] = hero.level
                obs[239] = hero.round_until_alive
                obs[240] = hero.inspiration_atk
                obs[241] = hero.inspiration_hp
                obs[242] = hero.inspiration_def
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
        if new_state["player_state"] == 5: reward -= 50
        if new_state["opponent_hp"] <= 0 or new_state["opponent_deck_size"] <= 0: reward += 50
        reward += (new_state["player_hp"] - original_state["player_hp"]) * 3
        reward += (original_state["opponent_hp"] - new_state["opponent_hp"]) * 8
        reward += (original_state["fire_remaining"] - new_state["fire_remaining"]) * 2
        if self.player1.state == 2:
            for i in range(4):
                reward += 4 * (original_state["opponent_heroes"][i].hp - new_state["opponent_heroes"][i].hp + original_state["opponent_heroes"][i].defense - new_state["opponent_heroes"][i].defense)
        if len(new_state["player_hand"]) > 15:
            reward -= 10 * (len(new_state["player_hand"]) - 15)
        if original_state["player_state"] != 1 and original_state["turn_count"] != new_state["turn_count"]:
            if original_state["fire_remaining"] == 2:
                reward -= 8
        return reward


class RandomOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = ActorCritic(243, 39).to(device="cuda")
        self.model.load_state_dict(torch.load("./logs/2026-02-20_00-13-35/ppo_actor_critic_2.pt"))


    def step(self, action):
        original_state = self.game.get_observations(self.player1)
        self.game.step(self.player1, self.decode_action(self.player1, action))
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                import random as r
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.act_inference(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        
        done = self.game.check_end_condition()
        new_state = self.game.get_observations(self.player1)
        reward = self.get_reward(original_state, new_state)
        obs = self.get_obs(self.player1)
        return obs, reward, done, {}
        

    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        self.get_opponent_agent()
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                import random as r
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.act_inference(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.get_obs(self.player1)
    

    def get_opponent_agent(self):
        import random as r
        x = r.random()
        self.opponent = "random" if x < 0.1 else "trained"
        # self.opponent = "random"
    

    def load_model(self, model_path):
        self.model.load_state_dict(torch.load(model_path))


class DQNOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = DoubleDQNAgent(243, 39).to(device="cuda")
        self.model.load_state_dict(torch.load("./logs/dqn/2026-03-03_09-47-49/dqn_model.pt"))
    

    def step(self, action):
        original_state = self.game.get_observations(self.player1)
        self.game.step(self.player1, self.decode_action(self.player1, action))
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                import random as r
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        
        done = self.game.check_end_condition()
        new_state = self.game.get_observations(self.player1)
        reward = self.get_reward(original_state, new_state)
        obs = self.get_obs(self.player1)
        return obs, reward, done, {}


    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng"], ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"])
        self.game = Game([self.player1, self.player2])
        self.game.start_game()
        self.get_opponent_agent()
        if self.opponent == "random":
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                import random as r
                legal_actions = self.get_legal_actions(self.player2)
                self.game.step(self.player2, self.decode_action(self.player2, r.choice(legal_actions)))
        else:
            while self.game.current_player is not self.player1 and not self.game.check_end_condition():
                with torch.inference_mode():
                    action_mask = self.get_action_masks(self.player2)
                    obs = torch.tensor(self.get_obs(self.player2), dtype=torch.float32, device="cuda")
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.get_obs(self.player1)
    

    def get_opponent_agent(self):
        import random as r
        x = r.random()
        self.opponent = "random" if x < 0.1 else "trained"
        # self.opponent = "random"
    

    def load_model(self, model_path):
        self.model.load_model(torch.load(model_path))