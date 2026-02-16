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
        from .player import Player
        for effect in self.effects:
            if isinstance(owner, Player):
                if isinstance(effect(event, owner), Action):
                    owner.game.step(owner, action=effect(event, owner))
                else:
                    effect(event, owner)
            else:
                if isinstance(effect(event, owner), Action):
                    owner.owner.game.step(owner.owner, action=effect(event, owner))
                else:
                    effect(event, owner)
            # effect.apply(event, owner)