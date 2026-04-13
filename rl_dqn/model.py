import torch
import torch.nn as nn
import torch.nn.functional as F

class QNetwork(nn.Module):
    def __init__(self, obs_dim, action_dim):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(obs_dim, 1024),
            nn.ReLU(),
            nn.Linear(1024, 768),
            nn.ReLU(),
            nn.Linear(768, 512),
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


class QNetworkLN(nn.Module):
    """
    和 QNetwork 结构完全相同，但每个隐藏层后加了 LayerNorm。
    LayerNorm 在每个样本内部做归一化，不依赖 batch 统计量，
    适合 RL 场景（BatchNorm 因样本非独立同分布容易不稳定）。
    """
    def __init__(self, obs_dim, action_dim):
        super().__init__()
 
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 1024),
            nn.LayerNorm(1024),
            nn.ReLU(),
            nn.Linear(1024, 768),
            nn.LayerNorm(768),
            nn.ReLU(),
            nn.Linear(768, 512),
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Linear(512, 512),
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Linear(512, action_dim)
        )
 
    def forward(self, obs):
        return self.net(obs)
