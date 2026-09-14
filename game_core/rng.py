"""集中化随机数生成器。

支持种子控制和推理模式覆写，使游戏随机效果可复现、可在真实对局中手动同步。
"""
import random as _random

_NOT_SET = object()


class GameRNG:
    """集中化随机数生成器。

    训练模式：使用标准 random.Random(seed) 保证可复现性。
    推理模式：通过 push_override() 预先注入随机结果。
    """

    def __init__(self, seed: int = None):
        self._rng = _random.Random(seed)
        self._override_stack: list = []

    # ── 覆写接口 ──────────────────────────────────────────────────────────

    def push_override(self, result):
        """推理模式：预先告知 RNG 下一次随机调用的结果。"""
        self._override_stack.append(result)

    def clear_overrides(self):
        """清空所有未消费的覆写结果。"""
        self._override_stack.clear()

    @property
    def has_override(self) -> bool:
        return len(self._override_stack) > 0

    def _next_override(self):
        if self._override_stack:
            return self._override_stack.pop(0)
        return _NOT_SET

    # ── 标准随机接口 ──────────────────────────────────────────────────────

    def choice(self, seq, context: str = ""):
        """从序列中随机选一个元素。"""
        override = self._next_override()
        if override is not _NOT_SET:
            return override
        if not seq:
            raise IndexError("GameRNG.choice() called with empty sequence")
        return self._rng.choice(list(seq))

    def shuffle(self, seq):
        """原地随机打乱序列。"""
        override = self._next_override()
        if override is not _NOT_SET:
            seq.clear()
            seq.extend(override)
            return
        self._rng.shuffle(seq)

    def random(self):
        """返回 [0.0, 1.0) 的随机浮点数。"""
        override = self._next_override()
        if override is not _NOT_SET:
            return float(override)
        return self._rng.random()

    def sample(self, seq, k: int):
        """从序列中随机选 k 个不重复元素。"""
        override = self._next_override()
        if override is not _NOT_SET:
            return list(override)
        return self._rng.sample(list(seq), k)

    def randint(self, a: int, b: int):
        """返回 [a, b] 范围内的随机整数（运势骰子等）。"""
        override = self._next_override()
        if override is not _NOT_SET:
            return int(override)
        return self._rng.randint(a, b)

    # ── 种子管理 ──────────────────────────────────────────────────────────

    def seed(self, s: int = None):
        self._rng.seed(s)

    def getstate(self):
        return self._rng.getstate()

    def setstate(self, state):
        self._rng.setstate(state)
