import sys
sys.path.insert(0, "E:/more_random_project")
from torch.utils.tensorboard import SummaryWriter
from datetime import datetime
import time
import os

from rl_dqn.replay_buffer import ReplayBuffer
from env.env import RandomOpponentGameEnv, DQNOpponentGameEnv
from rl_dqn.agent import DoubleDQNAgent

def train(env, agent, episodes=10000):

    log_dir = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_dir = os.path.join("logs/dqn", log_dir)
    writer = SummaryWriter(log_dir)

    # env.load_model("./logs/dqn/2026-03-13_13-36-48/dqn_model_3.pt")
    agent.load_model("./logs/dqn/2026-03-13_15-09-05/dqn_model_2.pt")
    
    replay_buffer = ReplayBuffer(100000)

    epsilon = 0.4
    epsilon_decay = 0.99
    epsilon_min = 0.05

    target_update_freq = 1000
    total_steps = 0

    chkpt = 1
    win = 0
    lose = 0

    for episode in range(episodes):

        obs = env.reset()
        done = False
        episode_reward = 0

        while not done:

            action_mask = env.get_action_masks(player=env.player1)

            action = agent.select_action(obs, action_mask, epsilon)

            next_obs, reward, done, _ = env.step(action)

            next_mask = env.get_action_masks(player=env.player1)

            replay_buffer.push(
                obs, action, reward,
                next_obs, done,
                action_mask, next_mask
            )

            obs = next_obs
            episode_reward += reward
            total_steps += 1

            if total_steps % target_update_freq == 0:
                agent.update_target()

        loss = agent.update(replay_buffer, batch_size=2048)
        epsilon = max(epsilon * epsilon_decay, epsilon_min)

        print(f"Episode {episode} | Reward {episode_reward} | epsilon {epsilon:.3f}")
        writer.add_scalar("Reward", episode_reward, episode)
        if loss is not None:
            writer.add_scalar("Loss", loss, episode)
        if episode_reward > 100:
            win += 1
        else:
            lose += 1
        print(f"win count {win} | lose count {lose}")
        
        if episode > chkpt * 2500:
            chkpt += 1
            agent.save_model(os.path.join(log_dir, f"dqn_model_{chkpt}.pt"))
            # env.load_model(os.path.join(log_dir, f"dqn_model_{chkpt}.pt"))
            win = 0
            lose = 0
            # epsilon = 0.4
    
    agent.save_model(os.path.join(log_dir, "dqn_model.pt"))

train(RandomOpponentGameEnv(), DoubleDQNAgent(obs_dim=243, action_dim=39, device='cuda'), episodes=30000)
