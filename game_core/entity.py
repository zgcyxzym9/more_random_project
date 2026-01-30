class Entity:
    def __init__(self, game, type:str = None, listeners=[]):
        self.game = game
        self.entity_type = type
        self.listeners = listeners