"""deck_winrate_predictor 的对外接口。

env.reset 只需要 predict()；predict_batch / sample_deck 供训练与工具使用。
"""

import random

import numpy as np
import torch

from .encoding import INPUT_DIM, encode_deck, encode_decks
from .model import DeckWinrateNet
from .selfplay import DeckEnv, softmax_weights


class DeckWinratePredictor:
    def __init__(self, device: str = "cuda", model_path: str = None):
        self.device = device
        self.model = DeckWinrateNet(INPUT_DIM).to(device)
        if model_path is not None:
            self.load(model_path)
        self.model.eval()
        self._env = None     # sample_deck 用；惰性创建（构造要读 cards.json 等）

    # ── 预测 ──────────────────────────────────────────────────────────

    @torch.no_grad()
    def predict(self, heroes, deck) -> float:
        """单套卡组的期望胜率（0~1）。heroes 为 4 个式神类名，deck 为 32 个卡牌 eng_name。"""
        x = torch.from_numpy(encode_deck(heroes, deck)).to(self.device)
        return float(self.model(x.unsqueeze(0)).item())

    @torch.no_grad()
    def predict_batch(self, decks) -> np.ndarray:
        """批量预测。decks 为 [(heroes, deck), ...]，返回 (N,) float32 numpy。"""
        if not decks:
            return np.zeros(0, dtype=np.float32)
        x = torch.from_numpy(encode_decks(decks)).to(self.device)
        return self.model(x).cpu().numpy()

    # ── 按胜率采样卡组 ────────────────────────────────────────────────

    def sample_deck(self, k: int = 64, temperature: float = 0.2):
        """生成 k 套随机卡组，按 softmax(预测胜率 / T) 加权抽一套，返回 (heroes, deck)。

        这正是需求2里「对手卡组分布 q 由本模块采样得到」的那套采样过程；k 越大越接近
        真实 q，但每调用一次就多 k 次卡组构筑。训练时请复用 selfplay.OpponentPool，
        它把候选缓存起来、只重算权重。
        """
        env = self._get_env()
        decks = [env.random_deck() for _ in range(k)]
        weights = softmax_weights(self.predict_batch(decks), temperature)
        return decks[random.choices(range(k), weights=weights, k=1)[0]]

    # ── checkpoint ───────────────────────────────────────────────────

    def save(self, path: str):
        torch.save(self.model.state_dict(), path)

    def load(self, path: str):
        self.model.load_state_dict(torch.load(path, map_location=self.device))

    @classmethod
    def from_checkpoint(cls, path: str, device: str = "cuda"):
        return cls(device=device, model_path=path)

    # ── 内部 ─────────────────────────────────────────────────────────

    def _get_env(self):
        if self._env is None:
            self._env = DeckEnv()
        return self._env
