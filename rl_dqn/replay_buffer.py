import torch


class ReplayBuffer:
    """
    Pre-allocated GPU-resident replay buffer.
    所有数据直接以 torch.Tensor 形式存储在指定 device（通常是 CUDA）上，
    避免每次 sample 时的 numpy ↔ tensor 转换和 CPU → GPU 搬运。
    """

    def __init__(self, capacity: int, obs_dim: int, action_dim: int, device: str = "cuda"):
        self.capacity = capacity
        self.device = device
        self.ptr = 0       # 下一个写入位置
        self.size = 0      # 当前有效数据量

        # 预分配所有存储空间，一次性占用显存
        self.obs      = torch.zeros((capacity, obs_dim),    dtype=torch.float32, device=device)
        self.next_obs = torch.zeros((capacity, obs_dim),    dtype=torch.float32, device=device)
        self.action   = torch.zeros((capacity,),            dtype=torch.long,    device=device)
        self.reward   = torch.zeros((capacity,),            dtype=torch.float32, device=device)
        self.done     = torch.zeros((capacity,),            dtype=torch.float32, device=device)
        self.mask     = torch.zeros((capacity, action_dim), dtype=torch.bool,    device=device)
        self.next_mask= torch.zeros((capacity, action_dim), dtype=torch.bool,    device=device)

    def push(self, obs, action, reward, next_obs, done, mask, next_mask):
        """
        接受任意格式（numpy / CPU tensor / GPU tensor / Python scalar），
        统一写入 GPU buffer。
        """
        self.obs[self.ptr]       = self._to_tensor(obs,       torch.float32)
        self.next_obs[self.ptr]  = self._to_tensor(next_obs,  torch.float32)
        self.action[self.ptr]    = int(action)
        self.reward[self.ptr]    = float(reward)
        self.done[self.ptr]      = float(done)
        self.mask[self.ptr]      = self._to_tensor(mask,      torch.bool)
        self.next_mask[self.ptr] = self._to_tensor(next_mask, torch.bool)

        self.ptr  = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int):
        """
        直接返回 GPU tensor，agent.update() 无需任何额外转换。
        """
        idx = torch.randint(0, self.size, (batch_size,), device=self.device)
        return (
            self.obs[idx],
            self.action[idx],
            self.reward[idx],
            self.next_obs[idx],
            self.done[idx],
            self.mask[idx],
            self.next_mask[idx],
        )

    def _to_tensor(self, x, dtype):
        if isinstance(x, torch.Tensor):
            return x.to(device=self.device, dtype=dtype)
        import numpy as np
        if isinstance(x, np.ndarray):
            return torch.from_numpy(x).to(device=self.device, dtype=dtype)
        return torch.tensor(x, dtype=dtype, device=self.device)

    def __len__(self):
        return self.size