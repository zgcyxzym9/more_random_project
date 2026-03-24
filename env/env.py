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

_DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


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


    def get_obs(self, player) -> torch.Tensor:
        state = self.game.get_observations(player)
        obs = torch.zeros(240, dtype=torch.float32, device=_DEVICE)
 
        obs[0] = player.state   #player_state need to use enum
        obs[1] = 0  # game_state, currently just a placeholder since game_state has no usage now
        obs[2] = state["turn_count"]
        obs[3] = state["player_hp"]
        obs[4] = state["opponent_hp"]
 
        for i in range(4):
            h = state["player_heroes"][i]
            base = 5 + i * 12
            obs[base]     = h.id
            obs[base + 1] = h.morphed_id
            obs[base + 2] = h.current_max_hp
            obs[base + 3] = h.hp
            obs[base + 4] = h.atk
            obs[base + 5] = h.round_buff_atk
            obs[base + 6] = h.defense
            obs[base + 7] = h.level
            obs[base + 8] = h.round_until_alive
            obs[base + 9] = h.inspiration_atk
            obs[base + 10] = h.inspiration_hp
            obs[base + 11] = h.inspiration_def
 
        for i in range(4):
            h = state["opponent_heroes"][i]
            base = 53 + i * 12
            obs[base]     = h.id
            obs[base + 1] = h.morphed_id
            obs[base + 2] = h.current_max_hp
            obs[base + 3] = h.hp
            obs[base + 4] = h.atk
            obs[base + 5] = h.round_buff_atk
            obs[base + 6] = h.defense
            obs[base + 7] = h.level
            obs[base + 8] = h.round_until_alive
            obs[base + 9] = h.inspiration_atk
            obs[base + 10] = h.inspiration_hp
            obs[base + 11] = h.inspiration_def
 
        obs[101] = state["player_deck_size"]
        obs[102] = state["opponent_deck_size"]
 
        hand = state["player_hand"]
        for i in range(min(len(hand), HAND_LIMIT)):
            obs[103 + i] = hand[i].id
 
        obs[115] = state["opponent_hand_size"]
 
        deck = state["player_starting_deck"]
        for i in range(min(len(deck), 32)):
            obs[116 + i] = Card.GetCard(deck[i]).id
 
        obs[148] = state["fire_remaining"]
        obs[149] = 1 if state["attack_available"] else 0
        obs[150] = 1 if state["is_first_player"] else 0
        obs[151] = state["pending_card"].id if state["pending_card"] is not None else 0
 
        for i, c in enumerate(state["player_used_card"]):
            if i >= 32: break
            obs[152 + i] = c.id
 
        for i, c in enumerate(state["opponent_used_card"]):
            if i >= 32: break
            obs[184 + i] = c.id
 
        # attacking heroes（一次遍历同时处理双方）
        for hero in state["player_heroes"]:
            if hero.state == "attacking":
                base = 216
                obs[base]     = hero.id
                obs[base + 1] = hero.morphed_id
                obs[base + 2] = hero.current_max_hp
                obs[base + 3] = hero.hp
                obs[base + 4] = hero.atk
                obs[base + 5] = hero.round_buff_atk
                obs[base + 6] = hero.defense
                obs[base + 7] = hero.level
                obs[base + 8] = hero.round_until_alive
                obs[base + 9] = hero.inspiration_atk
                obs[base + 10] = hero.inspiration_hp
                obs[base + 11] = hero.inspiration_def
                break
 
        for hero in state["opponent_heroes"]:
            if hero.state == "attacking":
                base = 228
                obs[base]     = hero.id
                obs[base + 1] = hero.morphed_id
                obs[base + 2] = hero.current_max_hp
                obs[base + 3] = hero.hp
                obs[base + 4] = hero.atk
                obs[base + 5] = hero.round_buff_atk
                obs[base + 6] = hero.defense
                obs[base + 7] = hero.level
                obs[base + 8] = hero.round_until_alive
                obs[base + 9] = hero.inspiration_atk
                obs[base + 10] = hero.inspiration_hp
                obs[base + 11] = hero.inspiration_def
                break
 
        return obs  # shape: (240,), float32, on GPU
        

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


    def get_action_masks(self, player) -> torch.Tensor:
        mask = torch.ones(36, dtype=torch.bool, device=_DEVICE)
        for a in self.get_legal_actions(player):
            mask[a] = False
        return mask
        

    def decode_action(self, player, action_id):
        if action_id == 0:
            return EndTurn()
        if UPGRADE_HERO_START <= action_id < HERO_ATTACK_START:
            return UpgradeHero(player.heroes[action_id - UPGRADE_HERO_START])
        if HERO_ATTACK_START <= action_id < PLAY_CARD_START:
            return HeroAttack(player.heroes[action_id - HERO_ATTACK_START])
        if PLAY_CARD_START <= action_id < SELECT_TARGET_START:
            return PlayCard(player.hand[action_id - PLAY_CARD_START], None)
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
            return RejectInitialPick(player.hand[action_id - REJECT_INITIAL_PICK_START])


    def get_reward(self, obs_before: torch.Tensor, obs_after: torch.Tensor) -> float:
        o = ObsIdx
        reward = 0.0
 
        # 胜负
        if obs_after[o.PLAYER_STATE] == 5:
            reward -= 50
        if obs_after[o.OPPONENT_HP] <= 0 or obs_after[o.OPPONENT_DECK] <= 0:
            reward += 50
 
        # 血量变化
        reward += float(obs_after[o.PLAYER_HP]  - obs_before[o.PLAYER_HP])  * 3
        reward += float(obs_before[o.OPPONENT_HP] - obs_after[o.OPPONENT_HP]) * 8
 
        # 鬼火消耗
        reward += float(obs_before[o.FIRE_REMAINING] - obs_after[o.FIRE_REMAINING]) * 2
 
        # 攻击阶段对手英雄 hp+def 变化
        if obs_before[o.PLAYER_STATE] == 2:
            for hp_idx, def_idx in zip(o.OPP_HERO_HP, o.OPP_HERO_DEF):
                reward += 4.0 * float(
                    (obs_before[hp_idx]  - obs_after[hp_idx]) +
                    (obs_before[def_idx] - obs_after[def_idx])
                )
 
        # 手牌超限惩罚
        hand_after = obs_after[o.PLAYER_HAND_START : o.PLAYER_HAND_START + HAND_LIMIT]
        hand_size  = int(hand_after.count_nonzero())
        if hand_size > HAND_LIMIT:
            reward -= 10 * (hand_size - HAND_LIMIT)
 
        # 回合切换但没用鬼火的惩罚
        turn_changed   = obs_after[o.TURN_COUNT] != obs_before[o.TURN_COUNT]
        not_init_state = obs_before[o.PLAYER_STATE] != 1
        fire_was_full  = obs_before[o.FIRE_REMAINING] == 2
        if not_init_state and turn_changed and fire_was_full:
            reward -= 8
 
        return reward


class RandomOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = ActorCritic(240, 36).to(device="cuda")
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
        self.opponent = "random" if x < 0.03 else "trained"
        # self.opponent = "random"
    

    def load_model(self, model_path):
        self.model.load_state_dict(torch.load(model_path))


class DQNOpponentGameEnv(Env):
    def __init__(self):
        super().__init__()
        self.model = DoubleDQNAgent(240, 36, "cuda")
        self.model.load_model("./logs/dqn/2026-03-17_14-34-54/dqn_model_1.pt")
    

    def step(self, action):
        obs_before = self.game.get_obs_tensor(self.player1, "cpu")
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
                    obs = self.game.get_obs_tensor(self.player2, _DEVICE)
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        
        done = self.game.check_end_condition()
        obs_after = self.game.get_obs_tensor(self.player1, "cpu")
        reward = self.get_reward(obs_before, obs_after)
        return obs_after.to(device=_DEVICE), reward, done, {}


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
                    obs = self.game.get_obs_tensor(self.player2, _DEVICE)
                    action = self.model.select_action(obs, action_mask)
                    self.game.step(self.player2, self.decode_action(self.player2, action))
        return self.get_obs(self.player1)
    

    def get_opponent_agent(self):
        import random as r
        x = r.random()
        self.opponent = "random" if x < 0.02 else "trained"
        # self.opponent = "random"
    

    def load_model(self, model_path):
        self.model.load_model(model_path)