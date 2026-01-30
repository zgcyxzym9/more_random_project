import torch

class RolloutBuffer:
    def __init__(self, size, obs_dim, device):
        self.device = device
        self.size = size
        self.ptr = 0

        self.obs = torch.zeros((size, obs_dim), device=device)
        self.actions = torch.zeros(size, device=device, dtype=torch.long)
        self.log_probs = torch.zeros(size, device=device)
        self.rewards = torch.zeros(size, device=device)
        self.dones = torch.zeros(size, device=device)
        self.values = torch.zeros(size, device=device)

    def add(self, obs, action, log_prob, reward, done, value):
        self.obs[self.ptr] = obs
        self.actions[self.ptr] = action
        self.log_probs[self.ptr] = log_prob
        self.rewards[self.ptr] = reward
        self.dones[self.ptr] = done
        self.values[self.ptr] = value
        self.ptr += 1

    def compute_returns_and_advantages(self, last_value, gamma=0.99, gae_lambda=0.95):
        advantages = torch.zeros_like(self.rewards)
        returns = torch.zeros_like(self.rewards)

        gae = 0
        for t in reversed(range(self.size)):
            next_value = last_value if t == self.size - 1 else self.values[t + 1]
            delta = self.rewards[t] + gamma * next_value * (1 - self.dones[t]) - self.values[t]
            gae = delta + gamma * gae_lambda * (1 - self.dones[t]) * gae
            advantages[t] = gae
            returns[t] = advantages[t] + self.values[t]

        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        return returns, advantages
