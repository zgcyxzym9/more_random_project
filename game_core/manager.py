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