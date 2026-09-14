"""通用计数器系统。

支持持久化（死亡不重置）、阈值回调、以及按回合/按局重置。
供 Hero / Player / Game 使用，替代原来零散的 hero.counter dict。
"""
from typing import Callable, Optional


class CounterDef:
    """计数器定义（静态配置）。"""
    __slots__ = ("name", "initial", "persistent", "max_val", "min_val",
                 "on_threshold", "reset_per_turn")

    def __init__(
        self,
        name: str,
        initial: int = 0,
        persistent: bool = False,        # True = 死亡/气绝时不重置
        max_val: Optional[int] = None,   # 上限
        min_val: int = 0,                # 下限
        on_threshold: Optional[dict] = None,  # {threshold_value: callback(self, counter_name, old, new)}
        reset_per_turn: bool = False,    # True = 每回合重置为 initial
    ):
        self.name = name
        self.initial = initial
        self.persistent = persistent
        self.max_val = max_val
        self.min_val = min_val
        self.on_threshold = on_threshold or {}
        self.reset_per_turn = reset_per_turn


class CounterManager:
    """管理一个实体上的所有计数器。

    用法：
        mgr = CounterManager(owner=self)
        mgr.define(CounterDef("lives", initial=0, persistent=True,
                               on_threshold={5: self._on_permanent_death}))
        mgr.inc("lives", 1)   # 触发阈值回调
        mgr.get("lives")       # 查询
    """

    def __init__(self, owner):
        self._owner = owner                  # Hero / Player / Game
        self._defs: dict[str, CounterDef] = {}
        self._values: dict[str, int] = {}

    def define(self, cd: CounterDef):
        """注册一个计数器。"""
        self._defs[cd.name] = cd
        self._values[cd.name] = cd.initial

    def ensure(self, name: str, **kwargs):
        """若计数器不存在则定义，否则忽略。"""
        if name not in self._defs:
            self.define(CounterDef(name=name, **kwargs))

    def get(self, name: str, default: int = 0) -> int:
        return self._values.get(name, default)

    def set(self, name: str, value: int):
        cd = self._defs.get(name)
        old = self._values.get(name, 0)
        new = min(value, cd.max_val) if cd and cd.max_val is not None else value
        if cd and cd.min_val is not None:
            new = max(new, cd.min_val)
        self._values[name] = new

        # 阈值回调
        if cd and cd.on_threshold:
            for threshold, callback in cd.on_threshold.items():
                if old < threshold <= new:
                    callback(self._owner, name, old, new)
                elif new < threshold <= old:
                    callback(self._owner, name, old, new)

    def inc(self, name: str, delta: int = 1):
        self.set(name, self.get(name) + delta)

    def dec(self, name: str, delta: int = 1):
        self.set(name, self.get(name) - delta)

    def reset(self, name: str):
        """重置单个计数器为初始值。"""
        cd = self._defs.get(name)
        if cd:
            self.set(name, cd.initial)

    def reset_all(self):
        """重置所有计数器为初始值（死亡/复活时调用）。"""
        for name, cd in self._defs.items():
            if not cd.persistent:
                self._values[name] = cd.initial

    def reset_per_turn(self):
        """每回合开始时的重置。"""
        for name, cd in self._defs.items():
            if cd.reset_per_turn:
                self._values[name] = cd.initial

    # ── 字典兼容接口 ──────────────────────────────────────────────────────

    def __getitem__(self, name: str) -> int:
        return self.get(name)

    def __setitem__(self, name: str, value: int):
        self.set(name, value)

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def update(self, mapping: dict):
        for k, v in mapping.items():
            self.set(k, v)

    def items(self):
        return self._values.items()
