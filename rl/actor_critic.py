import torch
import torch.nn as nn
import torch.distributions as dist


class ActorCritic(nn.Module):
    def __init__(self, obs_dim, act_dim, hidden_dim=128):
        super().__init__()

        # Actor
        self.actor = nn.Sequential(
            nn.Linear(obs_dim, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, act_dim)
        )

        # Critic
        self.critic = nn.Sequential(
            nn.Linear(obs_dim, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 1)
        )

    def forward(self, obs):
        raise NotImplementedError

    def get_action_and_value(self, obs, action=None, action_mask=None):
        """
        用于训练：
        - 采样动作
        - 计算 log_prob
        - 计算 value
        """
        logits = self.actor(obs)
        if action_mask is not None:
            logits = logits.masked_fill(action_mask, float('-inf'))
        dist_ = dist.Categorical(logits=logits)

        if action is None:
            action = dist_.sample()

        log_prob = dist_.log_prob(action)
        entropy = dist_.entropy()
        value = self.critic(obs).squeeze(-1)

        return action, log_prob, entropy, value

    def act_inference(self, obs, action_mask=None):
        """
        用于推理（不采样、不算 log_prob）
        """
        logits = self.actor(obs)
        if action_mask is not None:
            logits = logits.masked_fill(action_mask, float('-inf'))
        action = torch.argmax(logits, dim=-1)
        return action
