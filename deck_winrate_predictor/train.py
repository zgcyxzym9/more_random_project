"""训练卡组胜率预估模型（在线、逐局、自洽迭代）。

每一局的流程：
  1. d = 从合法全空间均匀随机构筑一套卡组（被评估方，与 q 无关）
  2. o = 从对手候选池里按 q ∝ softmax(预测胜率 / T) 抽一套
  3. 双方都由同一个固定 DQN 贪心对打，得到 d 的胜负
  4. (encode(d), d 是否获胜) 进 buffer，在线 BCE 更新模型

q 由模型自身的预测导出、模型又要在 q 下拟合胜率，目标是移动的——这是刻意的自洽迭代
（模型变准 -> q 更集中 -> 模型再拟合新的 q）。为此 buffer 用 FIFO 只保留最近 BUFFER 局，
让早期「近似均匀 q」下产生的陈旧标签自然淘汰。

用法：
  .venv/Scripts/python.exe deck_winrate_predictor/train.py
日志与权重写到 logs/deck_winrate/<时间戳>/。
"""
import sys

sys.path.insert(0, "E:/more_random_project_vibe")

import os
import random
from collections import deque
from datetime import datetime

import numpy as np
import torch
import torch.nn.functional as F
import torch.optim as optim
from torch.utils.tensorboard import SummaryWriter

from deck_winrate_predictor.encoding import encode_deck
from deck_winrate_predictor.predictor import DeckWinratePredictor
from deck_winrate_predictor.selfplay import (DeckEnv, OpponentPool, load_dqn,
                                             play_game)

DEVICE = "cuda"

#: 对手人格：双方都用这一个固定 DQN 贪心对打
OPPONENT_MODEL = "logs/dqn/2026-10-03_22-25-12/dqn_model_4.pt"

EPISODES = 20000
CHECKPOINT_EVERY = 5000
BATCH = 256
LR = 1e-3
BUFFER = 20000          # FIFO 容量（单位：局）
UPDATE_EVERY = 4        # 每多少局做一次梯度更新
K = 64                  # 对手候选池大小
TEMPERATURE = 0.2       # q ∝ softmax(pred / T)
POOL_REFRESH = 500      # 每多少局重新生成 K 套候选对手
LOG_EVERY = 50
SEED = 20261004


def train(episodes: int = EPISODES):
    random.seed(SEED)

    log_dir = os.path.join("logs/deck_winrate", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
    writer = SummaryWriter(log_dir)
    print(f"[init] log_dir = {log_dir}", flush=True)

    env = DeckEnv()
    opponent = load_dqn(OPPONENT_MODEL, DEVICE)

    predictor = DeckWinratePredictor(device=DEVICE)   # 打分用的模型就是训练中的模型
    model = predictor.model
    model.train()
    optimizer = optim.Adam(model.parameters(), lr=LR)

    pool = OpponentPool(env, k=K)

    buffer_x = deque(maxlen=BUFFER)
    buffer_y = deque(maxlen=BUFFER)

    window_pred = deque(maxlen=200)     # 最近若干局的预测值 / 实际胜负，用于校准观察
    window_win = deque(maxlen=200)
    loss_sum, loss_cnt = 0.0, 0
    draws = 0

    def update():
        idx = random.sample(range(len(buffer_y)), BATCH)
        x = torch.from_numpy(np.stack([buffer_x[i] for i in idx])).to(DEVICE)
        y = torch.tensor([buffer_y[i] for i in idx], dtype=torch.float32, device=DEVICE)
        loss = F.binary_cross_entropy(model(x), y)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 10.0)
        optimizer.step()
        return loss.item()

    for episode in range(1, episodes + 1):
        # 每局一个确定性子流：卡组构筑走模块级 random（见 selfplay.py 的说明）
        random.seed(SEED + episode)
        if (episode - 1) % POOL_REFRESH == 0:
            pool.refresh()

        deck_d = env.random_deck()
        weights = pool.weights(predictor, TEMPERATURE)
        deck_o = pool.sample(predictor, TEMPERATURE, weights=weights)

        d_won, _, finished = play_game(opponent, deck_d, deck_o,
                                       seed=random.randrange(2 ** 31), device=DEVICE)
        if not finished:
            # 平局 / 超时：没有可用的二分类标签，直接丢弃
            draws += 1
            continue

        buffer_x.append(encode_deck(*deck_d))
        buffer_y.append(float(d_won))
        window_pred.append(predictor.predict(*deck_d))
        window_win.append(float(d_won))

        if len(buffer_y) >= BATCH and episode % UPDATE_EVERY == 0:
            loss_sum += update()
            loss_cnt += 1

        if episode % LOG_EVERY == 0:
            if loss_cnt:
                writer.add_scalar("Loss", loss_sum / loss_cnt, episode)
            loss_sum, loss_cnt = 0.0, 0
            writer.add_scalar("pred_mean", float(np.mean(window_pred)), episode)
            writer.add_scalar("actual_winrate", float(np.mean(window_win)), episode)
            entropy = float(-(weights * np.log(weights + 1e-12)).sum())
            writer.add_scalar("q_entropy", entropy, episode)
            writer.add_scalar("q_max", float(weights.max()), episode)
            writer.add_scalar("draws", draws, episode)
            print(f"Episode {episode} | pred {np.mean(window_pred):.3f} "
                  f"| actual {np.mean(window_win):.3f} | q_max {weights.max():.3f} "
                  f"| draws {draws}", flush=True)

        if episode % CHECKPOINT_EVERY == 0:
            predictor.save(os.path.join(log_dir, "winrate_model.pt"))

    predictor.save(os.path.join(log_dir, "winrate_model.pt"))
    writer.close()
    print(f"[done] 权重已保存到 {log_dir}/winrate_model.pt", flush=True)


if __name__ == "__main__":
    train()
