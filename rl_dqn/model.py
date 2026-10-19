import torch
import torch.nn as nn
import torch.nn.functional as F

from env.actions import TOTAL_CARD_NUM, ObsIdx

class QNetwork(nn.Module):
    def __init__(self, obs_dim, action_dim):
        super().__init__()

        self.net = nn.Sequential(
            nn.Linear(obs_dim, 768),
            nn.ReLU(),
            nn.Linear(768, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )

    def forward(self, obs):
        """
        obs: (batch, obs_dim)
        return: (batch, action_dim)
        """
        return self.net(obs)


class QNetworkLN(nn.Module):
    """
    和 QNetwork 结构完全相同，但每个隐藏层后加了 LayerNorm。
    LayerNorm 在每个样本内部做归一化，不依赖 batch 统计量，
    适合 RL 场景（BatchNorm 因样本非独立同分布容易不稳定）。
    """
    def __init__(self, obs_dim, action_dim):
        super().__init__()
 
        self.net = nn.Sequential(
            nn.Linear(obs_dim, 768),
            nn.LayerNorm(768),
            nn.ReLU(),
            nn.Linear(768, 512),
            nn.LayerNorm(512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.LayerNorm(256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.LayerNorm(128),
            nn.ReLU(),
            nn.Linear(128, action_dim)
        )
 
    def forward(self, obs):
        return self.net(obs)


# ── 卡牌 embedding 网络（新基线，移植自 experiments/emb_norm_reward）────────
# 卡牌 multi-hot 四段（手牌/起始牌库/我方用过/对方用过）在 obs 中的
# 连续区间 [CARD_LO, CARD_HI)
CARD_LO         = ObsIdx.PLAYER_HAND_START                  # 283
CARD_HI         = ObsIdx.OPP_USED_START + TOTAL_CARD_NUM    # 1811
N_CARD_SECTIONS = 4
CARD_EMBED_DIM  = 32
assert ObsIdx.OPP_USED_START - ObsIdx.PLAYER_HAND_START == 3 * TOTAL_CARD_NUM, \
    "卡牌四段应连续；ObsIdx 布局可能已变，请核对"


class CardEmbQNetwork(nn.Module):
    """卡牌 embedding 头 + 原 trunk。

    - 4 组卡牌 multi-hot（各 382 维，允许 0/1/2 计数）经**共享**线性层
      embed: 382→32（一张表，跨段共享 ⇒ 同一张卡在任何区段映射同一向量，
      跨卡/跨段的泛化由 embedding 几何承担）；
    - 4×32=128 拼接 → Linear(128,64)+ReLU（段间组合）；
    - 与其余 341 维拼接（clamp ±10，与实验验证配方一致）→
      原 trunk [768,512,256,128]→792。
    参数量 ≈ 0.99M（原 plain 2.1M）。
    """

    REST_CLAMP = 10.0

    def __init__(self, obs_dim, action_dim, card_begin, card_end, total_card,
                 embed_dim=CARD_EMBED_DIM):
        super().__init__()
        self.card_begin, self.card_end = card_begin, card_end
        self.n_sections = N_CARD_SECTIONS
        self.total_card = total_card

        self.embed = nn.Linear(total_card, embed_dim, bias=False)      # 4 段共享
        self.sec_mix = nn.Sequential(nn.Linear(N_CARD_SECTIONS * embed_dim, 64), nn.ReLU())
        rest_dim = obs_dim - (card_end - card_begin)
        self.net = nn.Sequential(
            nn.Linear(rest_dim + 64, 768), nn.ReLU(),
            nn.Linear(768, 512), nn.ReLU(),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, 128), nn.ReLU(),
            nn.Linear(128, action_dim),
        )

    def forward(self, obs):
        cards = obs[..., self.card_begin:self.card_end]
        cards = cards.unflatten(-1, (self.n_sections, self.total_card))       # (B,4,382)
        z = self.embed(cards)                                           # (B,4,32)
        z = self.sec_mix(z.flatten(-2))                                # (B,64)
        rest = torch.cat([obs[..., :self.card_begin], obs[..., self.card_end:]], dim=-1)
        rest = rest.clamp(-self.REST_CLAMP, self.REST_CLAMP)
        return self.net(torch.cat([rest, z], dim=-1))
