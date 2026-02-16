import sys
sys.path.insert(0, "E:\more_random_project")
import torch
from actor_critic import ActorCritic
from env.env import RandomOpponentGameEnv

def eval(env, model_path="./logs/2026-02-16_12-59-30/ppo_actor_critic.pt"):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    obs_dim = 243
    # end_turn + upgrade + attack + play_card_by_slot + select_target + reject_initial_pick
    act_dim = 1 + 4 + 4 + 15 + 10 + 5 # 39

    model = ActorCritic(obs_dim, act_dim).to(device)
    model.load_state_dict(torch.load(model_path))
    model.eval()

    total = 100
    won = 0

    for i in range(total):
        obs = torch.tensor(env.reset(), dtype=torch.float32, device=device)

        done = False
        while not done:
            with torch.no_grad():
                action_mask = env.get_action_masks(player=env.player1)
                action = model.act_inference(obs, action_mask)

            obs, _, done, _ = env.step(action.item())
            obs = torch.tensor(obs, dtype=torch.float32, device=device)
        if env.player1.state != 5 and env.player2.state == 5:
            won += 1
        print(f"{env.player1.hp} {env.player2.hp}")
        print(f"{len(env.player1.deck.cards), len(env.player2.deck.cards)}")
        print(f"{won} / {i + 1}")

eval(RandomOpponentGameEnv())