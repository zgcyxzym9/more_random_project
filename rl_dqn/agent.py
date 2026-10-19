import torch
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
import random
import copy

from .model import (QNetwork, QNetworkLN, CardEmbQNetwork,
                    CARD_LO, CARD_HI, TOTAL_CARD_NUM)


class DoubleDQNAgent:
    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        device: str,
        gamma: float = 0.99,
        lr: float = 1e-4,
        use_layer_norm: bool = False,
        model_type: str | None = None,
    ):
        self.device = device
        self.gamma = gamma
        self.action_dim = action_dim

        # model_type 未显式指定时：latent_cards 为新基线默认；
        # 旧参数 use_layer_norm=True 仍生效
        if model_type is None:
            model_type = "layer_norm" if use_layer_norm else "latent_cards"

        if model_type == "plain":
            self.q_net = QNetwork(obs_dim, action_dim).to(device)
        elif model_type == "layer_norm":
            self.q_net = QNetworkLN(obs_dim, action_dim).to(device)
        elif model_type == "latent_cards":
            self.q_net = CardEmbQNetwork(obs_dim, action_dim, CARD_LO, CARD_HI,
                                         TOTAL_CARD_NUM).to(device)
        else:
            raise ValueError(f"未知网络结构: {model_type}")

        self.target_net = copy.deepcopy(self.q_net)
        self.target_net.eval()

        self.optimizer = optim.Adam(self.q_net.parameters(), lr=lr, weight_decay=1e-4)

    # ------------------------------------------------------------------
    # ε-greedy 动作选择
    # ------------------------------------------------------------------
    def select_action(self, obs, action_mask: torch.Tensor, epsilon: float = 0.0):
        """
        obs        : numpy array 或 GPU tensor，形状 (obs_dim,)
        action_mask: bool tensor，True 表示非法，形状 (action_dim,)
                     已经在 GPU 上（由环境直接返回）
        """
        if random.random() < epsilon:
            # 只在合法动作中随机采样，全程在 GPU 上完成
            legal_actions = torch.where(~action_mask)[0]
            if len(legal_actions) == 0:
                # 无合法动作（异常局面）时兜底到结束回合，避免 randint(0) 崩溃
                return 0
            return legal_actions[torch.randint(len(legal_actions), (1,))].item()

        # obs 转换：只有 numpy 才需要搬一次，tensor 直接用
        if not isinstance(obs, torch.Tensor):
            obs_tensor = torch.from_numpy(
                np.asarray(obs, dtype=np.float32)
            ).to(self.device).unsqueeze(0)
        else:
            obs_tensor = obs.unsqueeze(0) if obs.dim() == 1 else obs

        with torch.no_grad():
            q_values = self.q_net(obs_tensor).squeeze(0)
            q_values[action_mask] = -1e9          # mask 非法动作
            action = q_values.argmax().item()

        return action

    # ------------------------------------------------------------------
    # 网络更新
    # ------------------------------------------------------------------
    def update(self, replay_buffer, batch_size: int):
        if len(replay_buffer) < batch_size:
            return None

        # sample 直接拿到 GPU tensor，无需任何转换 ✓
        obs, action, reward, next_obs, done, mask, next_mask = \
            replay_buffer.sample(batch_size)

        # 当前 Q(s, a)
        q_values = self.q_net(obs)
        q_value  = q_values.gather(1, action.unsqueeze(1)).squeeze(1)

        # Double DQN target
        with torch.no_grad():
            next_q_online = self.q_net(next_obs)
            next_q_online[next_mask] = -1e9          # mask 非法动作
            next_actions = next_q_online.argmax(1)

            next_q_target = self.target_net(next_obs)
            next_q = next_q_target.gather(
                1, next_actions.unsqueeze(1)
            ).squeeze(1)

            target = reward + self.gamma * next_q * (1.0 - done)

        loss = F.smooth_l1_loss(q_value, target)

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_net.parameters(), 10.0)
        self.optimizer.step()

        return loss.item()

    # ------------------------------------------------------------------
    # 辅助方法
    # ------------------------------------------------------------------
    def update_target(self):
        self.target_net.load_state_dict(self.q_net.state_dict())

    def save_model(self, path: str):
        torch.save(self.q_net.state_dict(), path)

    def load_model(self, path: str):
        self.q_net.load_state_dict(
            torch.load(path, map_location=self.device)
        )
        self.update_target()