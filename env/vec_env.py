# vec_env.py
import numpy as np
import torch

class VecEnv:
    def __init__(self, env_fns):
        self.envs = [fn() for fn in env_fns]
        self.num_envs = len(self.envs)

    def reset(self):
        obs = [env.reset() for env in self.envs]
        action_masks = [env.get_action_masks(player=env.player1) for env in self.envs]
        return np.stack(obs), action_masks

    def step(self, actions):
        obs, rewards, dones, infos, action_masks = [], [], [], [], []

        for env, action in zip(self.envs, actions):
            if env.game.check_end_condition():
                o = env.reset()
                r = 0.0
                d = True
            else:
                o, r, d, info = env.step(action)
            m = env.get_action_masks(player=env.player1)

            obs.append(o)
            rewards.append(r)
            dones.append(d)
            infos.append(info)
            action_masks.append(m)

        return (
            np.stack(obs),
            torch.tensor(rewards, dtype=np.float32),
            np.array(dones, dtype=np.bool_),
            infos,
            action_masks,
        )
