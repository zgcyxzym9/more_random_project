import torch
from .actor_critic import ActorCritic

def inference(env, model_path="ppo_actor_critic.pt"):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    obs_dim = env.observation_space.shape[0]
    act_dim = env.action_space.n

    model = ActorCritic(obs_dim, act_dim).to(device)
    model.load_state_dict(torch.load(model_path))
    model.eval()

    obs = torch.tensor(env.reset(), dtype=torch.float32, device=device)

    done = False
    while not done:
        with torch.no_grad():
            action = model.act_inference(obs)

        obs, _, done, _ = env.step(action.item())
        obs = torch.tensor(obs, dtype=torch.float32, device=device)
        env.render()