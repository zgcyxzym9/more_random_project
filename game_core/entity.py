from .counters import CounterManager


class Entity:
    def __init__(self, game=None, type: str = None, listeners=None):
        self.game = game
        self.entity_type = type
        self.listeners = listeners if listeners is not None else []
        self.counters = CounterManager(self)

        # ── 可选生命周期钩子（Card/Hero 定义中的 lambda 元组，框架自动调用）──
        self.on_before_damage = ()   # (source, damage_value) → None 或修改后的事件
        self.on_after_damage = ()    # (source, damage_dealt) → None
        self.on_before_death = ()    # → 返回 True 阻止死亡（不死保护）
        self.on_countdown = ()       # 倒计时归零时触发
        self.on_move = ()            # (from_zone, to_zone) → None
        self.on_stun = ()            # 被眩晕时触发
        self.on_unstun = ()          # 眩晕解除时触发
