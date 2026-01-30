import sys
sys.path.insert(0, "E:\more_random_project")

from game_core.game import Game
from game_core.player import Player
from game_core.card import Card
from storage import RolloutBuffer
from actor_critic import ActorCritic
from ppo import PPO

class RandomOpponentGameEnv:
    def step(self, action):
        original_state = self.game.get_observations(self.player1)
        self.game.step(self.player1, action)
        while self.game.current_player is not self.player1 and not self.game.check_end_condition():
            import random as r
            legal_actions = self.get_legal_actions(self.player2)
            self.game.step(self.palyer2, r.choice(legal_actions))
        
        done = self.game.check_end_condition()
        new_state = self.game.get_observations(self.player1)
        reward = self.get_reward(original_state, new_state)
        obs = self.get_obs(self.player1)
        return obs, reward, done, {}
        

    def reset(self):
        self.player1 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "WuShiZhiDi", "WuShiZhiDi"], ["ZhiRenWuShi", "TianXieGuiTuanHuo"])
        self.player2 = Player(["WuShiZhiQuan", "WuShiZhiQuan", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi"], ["ZhiRenWuShi", "TianXieGuiTuanHuo"])
        self.game = Game([self.player1, self.player2])
        return self.get_obs(self.player1)

    def get_obs(self, player):
        state = self.game.get_observations(player)  #state: dict
        obs = [0] * 40
        obs[0] = _ #player_state need to use enum
        obs[1] = _ #game_state need to use enum
        obs[2] = state.turn_count
        obs[3] = state.player_hp
        obs[4] = state.opponent_hp
        for i in range(4):
            obs[5 + i * 12] = state.player_heroes[i].id
            obs[6 + i * 12] = state.player_heroes[i].morphed_id
            obs[7 + i * 12] = state.player_heroes[i].current_max_hp
            obs[8 + i * 12] = state.player_heroes[i].hp
            obs[9 + i * 12] = state.player_heroes[i].atk
            obs[10 + i * 12] = state.player_heroes[i].round_buff_atk
            obs[11 + i * 12] = state.player_heroes[i].defense
            obs[12 + i * 12] = state.player_heroes[i].level
            obs[13 + i * 12] = state.player_heroes[i].round_until_alive
            obs[14 + i * 12] = state.player_heroes[i].inspiration_atk
            obs[15 + i * 12] = state.player_heroes[i].inspiration_hp
            obs[16 + i * 12] = state.player_heroes[i].inspiration_def
        for i in range(4):
            obs[53 + i * 12] = state.opponent_heroes[i].id
            obs[54 + i * 12] = state.opponent_heroes[i].morphed_id
            obs[55 + i * 12] = state.opponent_heroes[i].current_max_hp
            obs[56 + i * 12] = state.opponent_heroes[i].hp
            obs[57 + i * 12] = state.opponent_heroes[i].atk
            obs[58 + i * 12] = state.opponent_heroes[i].round_buff_atk
            obs[59 + i * 12] = state.opponent_heroes[i].defense
            obs[60 + i * 12] = state.opponent_heroes[i].level
            obs[61 + i * 12] = state.opponent_heroes[i].round_until_alive
            obs[62 + i * 12] = state.opponent_heroes[i].inspiration_atk
            obs[63 + i * 12] = state.opponent_heroes[i].inspiration_hp
            obs[64 + i * 12] = state.opponent_heroes[i].inspiration_def
        obs[101] = state.player_deck_size
        obs[102] = state.opponent_deck_size
        # We currently limit the size of hand to 15 cards, can adjust accordingly
        for i in range(len(state.player_hand)):
            obs[103 + i] = state.player_hand[i].id
            if i >= 14:
                break
        obs[118] = state.opponent_hand_size
        # Hand size should be 32
        for i in range(len(state.player_starting_deck)):
            obs[119 + i] = Card.GetCard(state.player_starting_deck[i]).id
        obs[151] = state.fire_remaining
        obs[152] = 1 if state.attack_available == True else 0
        obs[153] = 1 if state.is_first_player == True else 0
        obs[154] = state.pending_card.id
        return obs
        

    def get_legal_actions(self, player):
        if player.can_end_turn():
            


    def get_reward(self, original_state, new_state):
        reward = 0
        if new_state.player_state == "lost": reward -= 500
        if new_state.opponent_hp <= 0 or new_state.opponent_deck_size <= 0: reward += 500
        reward += (new_state.player_hp - original_state.player_hp) * 2
        reward += (original_state.opponent_hp - new_state.opponent_hp) * 2
        reward += (new_state.player_fire - original_state.player_fire) * 1
        return reward