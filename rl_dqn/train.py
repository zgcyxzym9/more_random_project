import sys
sys.path.insert(0, "E:/more_random_project")

from torch.utils.tensorboard import SummaryWriter
from datetime import datetime
import os

from rl_dqn.replay_buffer import ReplayBuffer
from env.env import RandomOpponentGameEnv, DQNOpponentGameEnv
from rl_dqn.agent import DoubleDQNAgent


OBS_DIM    = 240
ACTION_DIM = 36
DEVICE     = "cuda"


def train(env, agent, episodes=10000):

    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = os.path.join("logs/dqn", log_dir)
    writer  = SummaryWriter(log_dir)

    # agent.load_model("./logs/dqn/2026-03-13_14-06-15/dqn_model_2.pt")

    # ReplayBuffer 现在需要知道 obs_dim / action_dim / device
    # 所有数据从一开始就住在 GPU 上
    replay_buffer = ReplayBuffer(
        capacity=100000,
        obs_dim=OBS_DIM,
        action_dim=ACTION_DIM,
        device=DEVICE,
    )

    epsilon       = 1.0
    epsilon_decay = 0.9995
    epsilon_min   = 0.05

    target_update_freq = 5000
    total_steps = 0
    update_freq=4

    chkpt = 1
    win = 0
    lose = 0

    for episode in range(episodes):

        obs = env.reset()
        done = False
        episode_reward = 0
        episode_loss = 0.0
        update_count = 0

        while not done:

            action_mask = env.get_action_masks(player=env.player1)

            action = agent.select_action(obs, action_mask, epsilon)

            next_obs, reward, done, _ = env.step(action)

            next_mask = env.get_action_masks(player=env.player1)

            # push 接受任意格式，内部统一转 GPU tensor
            replay_buffer.push(
                obs, action, reward,
                next_obs, done,
                action_mask, next_mask,
            )

            obs = next_obs
            episode_reward += reward
            total_steps += 1

            if total_steps % target_update_freq == 0:
                agent.update_target()

            # 每 update_freq 步做一次梯度更新
            if total_steps % update_freq == 0:
                loss = agent.update(replay_buffer, batch_size=2048)
                if loss is not None:
                    episode_loss += loss
                    update_count += 1

        epsilon = max(epsilon * epsilon_decay, epsilon_min)
        avg_loss = episode_loss / update_count if update_count > 0 else None

        print(f"Episode {episode} | Reward {episode_reward:.2f} | epsilon {epsilon:.3f}")
        writer.add_scalar("Reward", episode_reward, episode)
        if avg_loss is not None:
            writer.add_scalar("Loss", avg_loss, episode)

        if env.player1.hp > 0:
            win += 1
        else:
            lose += 1
        print(f"win count {win} | lose count {lose}")

        if episode > chkpt * 2500:
            chkpt += 1
            agent.save_model(os.path.join(log_dir, f"dqn_model_{chkpt}.pt"))
            env.load_model(os.path.join(log_dir, f"dqn_model_{chkpt}.pt"))
            win = 0
            lose = 0
    
    agent.save_model(os.path.join(log_dir, "dqn_model.pt"))


train(
    DQNOpponentGameEnv(),
    DoubleDQNAgent(obs_dim=OBS_DIM, action_dim=ACTION_DIM, device=DEVICE),
    episodes=30000,
)