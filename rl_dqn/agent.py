import torch.optim as optim
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from .model import QNetwork
import random

class DoubleDQNAgent:
    def __init__(
        self,
        obs_dim,
        action_dim,
        device,
        gamma=0.99,
        lr=1e-4
    ):
        self.device = device
        self.gamma = gamma
        self.action_dim = action_dim

        self.q_net = QNetwork(obs_dim, action_dim).to(device)
        self.target_net = QNetwork(obs_dim, action_dim).to(device)

        self.target_net.load_state_dict(self.q_net.state_dict())
        self.target_net.eval()

        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr)

    # ε-greedy
    def select_action(self, obs, action_mask, epsilon=0):
        """
        obs: (obs_dim,)
        action_mask: (action_dim,)  
        """

        if random.random() < epsilon:
            legal_actions = torch.where(action_mask == False)[0]
            return random.choice(legal_actions)

        if not isinstance(obs, torch.Tensor):
            obs_tensor = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        else:
            obs_tensor = obs

        with torch.no_grad():
            q_values = self.q_net(obs_tensor).squeeze(0)

            q_values[action_mask == True] = -1e9

            action = torch.argmax(q_values).item()

        return action

    def update(self, replay_buffer, batch_size):

        if len(replay_buffer) < batch_size:
            return None

        obs, action, reward, next_obs, done, mask, next_mask = replay_buffer.sample(batch_size)

        obs = torch.FloatTensor(obs).to(self.device)
        next_obs = torch.FloatTensor(next_obs).to(self.device)
        action = torch.LongTensor(action).to(self.device)
        reward = torch.FloatTensor(reward).to(self.device)
        done = torch.FloatTensor(done).to(self.device)
        next_mask = torch.FloatTensor(next_mask).to(self.device)

        # 当前 Q(s,a)
        q_values = self.q_net(obs)
        q_value = q_values.gather(1, action.unsqueeze(1)).squeeze(1)

        # Double DQN target
        with torch.no_grad():

            # online 选动作
            next_q_online = self.q_net(next_obs)

            # mask 非法动作
            next_q_online[next_mask == True] = -1e9

            next_actions = next_q_online.argmax(1)

            # target 估值
            next_q_target = self.target_net(next_obs)
            next_q = next_q_target.gather(
                1, next_actions.unsqueeze(1)
            ).squeeze(1)

            target = reward + self.gamma * next_q * (1 - done)

        # Huber loss 比 MSE 稳定
        loss = F.smooth_l1_loss(q_value, target)

        self.optimizer.zero_grad()
        loss.backward()

        # 防止爆炸
        torch.nn.utils.clip_grad_norm_(self.q_net.parameters(), 10.0)

        self.optimizer.step()

        return loss.item()

    def update_target(self):
        self.target_net.load_state_dict(self.q_net.state_dict())

    def save_model(self, path):
        torch.save(self.q_net.state_dict(), path)
    
    def load_model(self, path):
        self.q_net.load_state_dict(torch.load(path, map_location=self.device))
        self.update_target()
