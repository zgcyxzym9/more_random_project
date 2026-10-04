"""整局对局的驱动 + 对手候选池（即「对手卡组分布 q」的采样器）。

对局双方由同一个固定 DQN 贪心驱动（epsilon=0），这样胜负只反映**卡组强度**差异，
不掺入策略差异。驱动循环照抄 rl_dqn/selfplay_eval.py::play_game。

动作空间必须用 env/actions.py 这版（build_action_mask / decode_action 无 game 参数），
它与 game.get_obs_tensor 的 multi-hot 下标严格对齐；experiments/deck_strength/spaces.py
里的同名函数是 282 维卡牌空间的旧拷贝，不能用。

关于随机性：Env._build_deck / Player.start_game 用的是模块级 `random`，所以随机性
统一由全局 `random` 控制（rl_dqn/selfplay_eval.py:84 也是这么做的）。调用方在每局
开始前 `random.seed(...)` 即可复现整套卡组构筑与对局。
"""

import random

import numpy as np
import torch

from env.actions import ACTION_DIM, OBS_DIM, build_action_mask, decode_action
from env.env import Env
from game_core.enums import PlayerState
from game_core.game import Game
from game_core.player import Player
from rl_dqn.agent import DoubleDQNAgent

MAX_STEPS = 3000     # 单局步数上限（正常对局远小于此，见 selfplay_eval.py）
MAX_ILLEGAL = 20     # mask 判合法但 decode 为 None 的容忍次数


class DeckEnv(Env):
    """只借用 Env 的随机器组/随机卡组构筑逻辑（_precompute_deck_tables + _build_deck）。"""

    def random_deck(self):
        """均匀抽一套合法卡组，返回 (heroes, deck)。"""
        heroes = list(random.choice(self.valid_lineups))
        return heroes, self._build_deck(heroes)


def load_dqn(path, device):
    """加载一个冻结的 DQN（贪心推理用）。"""
    agent = DoubleDQNAgent(OBS_DIM, ACTION_DIM, device)
    agent.load_model(path)
    agent.q_net.eval()
    return agent


def play_game(agent, deck_a, deck_b, seed, device):
    """跑一局 deck_a vs deck_b，双方都由 agent 贪心驱动。

    返回 (a_won, steps, finished)：
      a_won    —— deck_a 一方是否获胜
      finished —— 是否真的分出了胜负。平局 / 超时（含非法动作超限）时为 False，
                  调用方应丢弃该样本，避免把「没打完」当成「输了」。
    """
    heroes_a, cards_a = deck_a
    heroes_b, cards_b = deck_b
    player_a = Player(cards_a, heroes_a)
    player_b = Player(cards_b, heroes_b)
    game = Game([player_a, player_b], seed=seed)
    game.start_game()

    steps = 0
    illegal = 0
    while not game.check_end_condition():
        if steps >= MAX_STEPS:
            break
        cur = game.current_player
        mask = build_action_mask(cur, device)
        obs = game.get_obs_tensor(cur, device)
        action = agent.select_action(obs, mask, epsilon=0.0)
        decoded = decode_action(cur, action)
        steps += 1
        if decoded is None:
            # 与环境 step 一致的兜底：不推进游戏。理论上 mask 保证不会走到这里。
            illegal += 1
            if illegal > MAX_ILLEGAL:
                break
            continue
        game.step(cur, decoded)

    a_won = player_b.state == PlayerState.LOST
    b_won = player_a.state == PlayerState.LOST
    return a_won, steps, a_won != b_won


def softmax_weights(preds: np.ndarray, temperature: float) -> np.ndarray:
    """对手分布的权重：softmax(预测胜率 / T)。数值稳定（减最大值再取指数）。"""
    logits = preds / temperature
    logits = logits - logits.max()
    weights = np.exp(logits)
    return weights / weights.sum()


class OpponentPool:
    """需求2里的对手卡组分布 q。

    q 不是一个能存下来的分布，而是「现场生成 K 套随机卡组 -> 用当前模型批量打分 ->
    按 softmax(pred/T) 抽一套」这个采样过程。候选卡组每 POOL_REFRESH 局重生成一次，
    权重每局都用最新模型重算（K 次前向，训练里可忽略）。
    """

    def __init__(self, env: DeckEnv, k: int = 64):
        self.env = env
        self.k = k
        self.decks = [env.random_deck() for _ in range(k)]

    def refresh(self):
        """重新生成 K 套候选对手卡组。"""
        self.decks = [self.env.random_deck() for _ in range(self.k)]

    def weights(self, predictor, temperature: float) -> np.ndarray:
        """当前模型下 K 套候选的 softmax 权重。"""
        return softmax_weights(predictor.predict_batch(self.decks), temperature)

    def sample(self, predictor, temperature: float, weights=None):
        """抽一套对手卡组；weights 可复用外部刚算过的那一份，避免重复前向。"""
        if weights is None:
            weights = self.weights(predictor, temperature)
        idx = random.choices(range(self.k), weights=weights, k=1)[0]
        return self.decks[idx]
