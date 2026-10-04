"""卡组 → 373 维向量的编码（全仓库唯一一处卡组词表定义）。

词表：
  · 式神 39 维：game_core/hero_names.txt 的行序，index = 行号
  · 卡牌 334 维：cards.json 正式卡 id 1..334，index = id - 1（取值 0/1/2 = 带几张）

卡组记作 (heroes, deck)：heroes 是 4 个式神类名，deck 是 32 个卡牌 eng_name。
两段都是 multi-hot，与顺序无关——引擎在 Player.start_game 里本来就会 shuffle(heroes)，
卡组顺序也不影响对局，所以不需要「按槽位」的 one-hot。

词表外的名字一律抛异常，不静默丢弃：静默丢一张卡会让编码悄悄偏离真实卡组，
而这种偏差在训练里只表现为「预测不准」，极难定位。
"""

import os
from typing import Sequence

import numpy as np

from env.actions import MAX_CARD_ID
from game_core.card import Card

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_hero_index() -> dict:
    with open(os.path.join(_ROOT, "game_core", "hero_names.txt"), "r", encoding="utf-8") as f:
        names = [line.strip() for line in f if line.strip()]
    return {name: i for i, name in enumerate(names)}


#: 式神名 -> multi-hot 下标（hero_names.txt 行序；将来实装新式神只会追加，不重编号）
HERO_INDEX = _load_hero_index()
HERO_DIM = len(HERO_INDEX)          # 39
CARD_DIM = MAX_CARD_ID              # 334（token 卡 id > MAX_CARD_ID，不会出现在卡组里）
INPUT_DIM = HERO_DIM + CARD_DIM     # 373


def card_index(eng_name: str) -> int:
    """卡牌 eng_name -> 卡牌段的 0-based 下标。词表外/超出正式卡 id 的一律报错。"""
    cid = Card.get_id_by_name(eng_name)
    if cid == 0:
        raise KeyError(f"卡牌不在 cards.json 中: {eng_name}")
    if not 1 <= cid <= CARD_DIM:
        raise ValueError(f"卡牌 id 超出正式卡范围（token 不应进卡组）: {eng_name} -> {cid}")
    return HERO_DIM + cid - 1


def encode_deck(heroes: Sequence[str], deck: Sequence[str]) -> np.ndarray:
    """(heroes, deck) -> (INPUT_DIM,) float32。式神段置 1，卡牌段按张数累加。"""
    vec = np.zeros(INPUT_DIM, dtype=np.float32)
    for hero in heroes:
        idx = HERO_INDEX.get(hero)
        if idx is None:
            raise KeyError(f"式神不在 hero_names.txt 中: {hero}")
        vec[idx] = 1.0
    for name in deck:
        vec[card_index(name)] += 1.0
    return vec


def encode_decks(decks: Sequence) -> np.ndarray:
    """批量编码 [(heroes, deck), ...] -> (N, INPUT_DIM) float32。"""
    if not decks:
        return np.zeros((0, INPUT_DIM), dtype=np.float32)
    return np.stack([encode_deck(heroes, deck) for heroes, deck in decks])
