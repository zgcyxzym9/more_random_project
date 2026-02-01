import sys
sys.path.insert(0, "E:\more_random_project")
import torch

from game_core.game import Game
from game_core.player import Player
from storage import RolloutBuffer
from actor_critic import ActorCritic
from ppo import PPO
from env.env import RandomOpponentGameEnv

def train(env, total_steps=100_000, rollout_size=2048):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    obs_dim = 155
    # end_turn + upgrade + attack + play_card_by_slot + select_target + reject_initial_pick
    act_dim = 1 + 4 + 4 + 15 + 10 + 5 # 39

    model = ActorCritic(obs_dim, act_dim).to(device)
    ppo = PPO(model)

    obs = torch.tensor(env.reset(), dtype=torch.float32, device=device)

    step = 0
    while step < total_steps:
        buffer = RolloutBuffer(rollout_size, obs_dim, device)

        for _ in range(rollout_size):
            action_mask = env.get_action_masks(player=env.player1)
            with torch.no_grad():
                action, log_prob, _, value = model.get_action_and_value(obs, action_mask=action_mask)

            next_obs, reward, done, _ = env.step(action.item())

            buffer.add(
                obs,
                action,
                log_prob,
                reward,
                done,
                value,
            )

            obs = torch.tensor(next_obs, dtype=torch.float32, device=device)
            step += 1

            if done:
                obs = torch.tensor(env.reset(), dtype=torch.float32, device=device)

        action_mask = env.get_action_masks(player=env.player1)
        with torch.no_grad():
            _, _, _, last_value = model.get_action_and_value(obs, action_mask=action_mask)

        returns, advantages = buffer.compute_returns_and_advantages(last_value)
        ppo.update(buffer, returns, advantages)

        print(f"############ step {step} / {total_steps} ############")

    torch.save(model.state_dict(), "ppo_actor_critic.pt")


train(RandomOpponentGameEnv())