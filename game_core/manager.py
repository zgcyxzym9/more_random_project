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
        for effect in self.effects:
            if type(owner).__name__ == "Player":
                owner.game.step(action=effect)
            else:
                owner.owner.game.step(action=effect)
            # effect.apply(event, owner)