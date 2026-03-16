import sys
sys.path.insert(0, "E:/more_random_project")
import torch
from rl_dqn.agent import DoubleDQNAgent
from env.env import RandomOpponentGameEnv, DQNOpponentGameEnv

def eval(env, model_path="./logs/dqn/2026-03-13_15-09-05/dqn_model_2.pt"):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    obs_dim = 240
    act_dim = 36

    model = DoubleDQNAgent(obs_dim, act_dim, device)
    model.q_net.load_state_dict(torch.load(model_path))
    model.q_net.eval()

    total = 500
    won = 0

    first_won = 0
    second_won = 0

    for i in range(total):
        obs = torch.tensor(env.reset(), dtype=torch.float32, device=device)

        done = False
        while not done:
            with torch.no_grad():
                action_mask = env.get_action_masks(player=env.player1)
                action = model.select_action(obs.cpu().numpy(), action_mask.cpu().numpy(), epsilon=0.0)

            obs, _, done, _ = env.step(action)
            obs = torch.tensor(obs, dtype=torch.float32, device=device)
        if env.player1.state != 5 and env.player2.state == 5:
            won += 1
            if env.player1.is_first_player:
                first_won += 1
            else:
                second_won += 1
        print(f"{won} / {i + 1}")
    print(f"{first_won} {second_won}")

if __name__ == "__main__":
    env = RandomOpponentGameEnv()
    eval(env)