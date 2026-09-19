class CardEnhance:
    """增强（wiki 关键字-增强）声明：cond(s) 满足时，卡牌获得 attributes 中的
    属性（如瞬发），并获得 on_play 追加效果。

    引擎结算（Game.can_play_card / Game._apply_enhance）：
    - 判定时以「满足条件增强后的复制体」重新判定（瞬发等可打出性属性生效，
      0 鬼火可通过判定），原卡不被修改；
    - 确定打出后、play_card 结算开头把增强实装到卡上（属性参与鬼火结算、
      效果回调续在 on_play 尾部随类型正常结算）。
    """

    def __init__(self, cond, attributes=(), on_play=()):
        self.cond = cond              # (card) -> bool
        self.attributes = tuple(attributes)
        self.on_play = tuple(on_play)  # (card) -> Event | None，续在原效果之后


class Listener:
    """事件监听器（两阶段广播）。

    phase 只能取 "before"（生效前）或 "after"（生效后）二者之一——每个监听器
    只匹配其中一个阶段，同一事件不会让同一监听器触发两次。未显式指定时默认
    "before"，与历史单阶段行为兼容（绝大多数广播点在生效前）。

    例外历史约定："play card" 的常规监听器习惯上读的是结算完成后的战场状态，
    全部旧监听器已显式迁移为 phase="after"（对应完成广播位置），不能依赖默认值。

    after 阶段语义：广播点位于事件/动作完整生效之后（revert、校验失败、挂起
    等提前返回的路径不会广播 after）；对 wrapper 事件的修改与 revert 在 after
    阶段不再被评估。
    """

    def __init__(self, event_type, condition, effects, phase="before"):
        if phase not in ("before", "after"):
            raise ValueError(f"invalid listener phase: {phase!r}")
        self.event_type = event_type
        self.condition = condition      # event -> bool
        self.effects = effects          # list[Effect]
        self.phase = phase              # "before" | "after"，二选一

    def matches(self, event, owner):
        return (
            event.type == self.event_type
            and getattr(event, "phase", "before") == self.phase
            and self.condition(event, owner)
        )

    def trigger(self, event, owner):
        from .action import Action
        from .event import Event
        from .player import Player
        for effect in self.effects:
            if isinstance(owner, Player):
                result = effect(event, owner)
                if isinstance(result, Action):
                    owner.game.step(owner, action=result)
                elif isinstance(result, Event):
                    owner.game.handle_event(result)
            else:
                result = effect(event, owner)
                if isinstance(result, Action):
                    owner.owner.game.step(owner.owner, action=result)
                elif isinstance(result, Event):
                    owner.owner.game.handle_event(result)