import torch.nn as nn

from .encoding import INPUT_DIM


class DeckWinrateNet(nn.Module):
    """卡组 one-hot（373 维）-> 期望胜率（0~1）。

    结构风格对齐 rl_dqn/model.py::QNetwork；输入是稀疏 multi-hot、没有归一化，
    但输出过 Sigmoid 且有界，不存在 Q 网络那种自举放大问题。
    """

    def __init__(self, input_dim: int = INPUT_DIM):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid(),
        )

    def forward(self, x):
        """
        x: (batch, input_dim)
        return: (batch,)  —— 每套卡组的期望胜率
        """
        return self.net(x).squeeze(-1)
