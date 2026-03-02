import random
from collections import deque
import numpy as np
import torch

class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, obs, action, reward, next_obs, done, mask, next_mask):
        self.buffer.append(
            (obs, action, reward, next_obs, done, mask, next_mask)
        )

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)

        obs, action, reward, next_obs, done, mask, next_mask = zip(*batch)

        return (
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in obs]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in action]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in reward]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in next_obs]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in done]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in mask]),
            np.array([x.cpu().numpy() if torch.is_tensor(x) else x for x in next_mask]),
        )


    def __len__(self):
        return len(self.buffer)
