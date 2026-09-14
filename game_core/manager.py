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
    def __init__(self, event_type, condition, effects):
        self.event_type = event_type
        self.condition = condition      # event -> bool
        self.effects = effects          # list[Effect]

    def matches(self, event, owner):
        return (
            event.type == self.event_type
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