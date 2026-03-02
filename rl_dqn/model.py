import torch
import torch.nn as nn
import torch.nn.functional as F

class QNetwork(nn.Module):
    def __init__(self, obs_dim, action_dim):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(obs_dim, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.Linear(512, action_dim)
        )

    def forward(self, obs):
        """
        obs: (batch, obs_dim)
        return: (batch, action_dim)
        """
        return self.net(obs)
