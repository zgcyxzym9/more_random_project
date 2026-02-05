import torch

class PPO:
    def __init__(
        self,
        model,
        lr=3e-4,
        clip_ratio=0.2,
        value_coef=0.5,
        entropy_coef=0.01,
    ):
        self.model = model
        self.optimizer = torch.optim.Adam(model.parameters(), lr=lr)

        self.clip_ratio = clip_ratio
        self.value_coef = value_coef
        self.entropy_coef = entropy_coef

    def update(self, buffer, returns, advantages, epochs=4, batch_size=512):
        mean_policy_loss = 0
        mean_value_loss = 0
        for _ in range(epochs):
            indices = torch.randperm(buffer.size)

            for start in range(0, buffer.size, batch_size):
                end = start + batch_size
                batch_idx = indices[start:end]

                obs = buffer.obs[batch_idx]
                actions = buffer.actions[batch_idx]
                old_log_probs = buffer.log_probs[batch_idx]
                returns_b = returns[batch_idx]
                adv_b = advantages[batch_idx]

                _, log_probs, entropy, values = self.model.get_action_and_value(obs, actions)

                ratio = torch.exp(log_probs - old_log_probs)
                surr1 = ratio * adv_b
                surr2 = torch.clamp(ratio, 1 - self.clip_ratio, 1 + self.clip_ratio) * adv_b
                policy_loss = -torch.min(surr1, surr2).mean()

                value_loss = (returns_b - values).pow(2).mean()
                entropy_loss = entropy.mean()

                loss = (
                    policy_loss
                    + self.value_coef * value_loss
                    - self.entropy_coef * entropy_loss
                )

                mean_policy_loss += policy_loss.item()
                mean_value_loss += value_loss.item()

                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()

        mean_policy_loss /= epochs * buffer.size / batch_size
        mean_value_loss /= epochs * buffer.size / batch_size
        return mean_value_loss, mean_policy_loss
