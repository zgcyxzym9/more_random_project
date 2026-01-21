class Agent:
    def act():
        print("not implemented!")

class IOAgent(Agent):
    def __init__(self, game, player):
        self.game = game
        self.player = player
    
    def act(self):
        state = self.game.get_observations(self.player)
        print("Current observed state:")
        for key, value in state.items():
            print(f"{key}: {value}")
        legal_actions = self.player.get_legal_actions()
        for i in range(len(legal_actions)):
            print(f"Action {i+1}: {legal_actions[i]}")
        action_id = int(input("Select action ID: ")) - 1
        return legal_actions[action_id]