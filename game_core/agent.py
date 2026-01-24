class Agent:
    def act():
        print("not implemented!")

class IOAgent(Agent):
    def __init__(self, game, player):
        self.game = game
        self.player = player
    
    def act(self):
        state = self.game.get_observations(self.player)
        self.PhaseOutState(state)
        legal_actions = self.player.get_legal_actions()
        for i in range(len(legal_actions)):
            print(f"Action {i+1}: {legal_actions[i]}")
        action_id = int(input("Select action ID: ")) - 1
        return legal_actions[action_id]
    
    def PhaseOutState(self, state):
        match state["game_state"]:
            case "initial pick":
                print(f"Opponent heroes: {state["opponent_heroes"]}")
                print(f"Your heroes: {state["player_heroes"]}")
                print(f"Your hand: {state["player_hand"]}")
            case "playing":
                print(f"Opponent hp: {state["opponent_hp"]}           Opponent hand size: {state["opponent_hand_size"]}           Opponent deck size: {state["opponent_deck_size"]}")
                print("")
                print(f"Opponent heroes: ")
                for hero in state["opponent_heroes"]:
                    if hero.state == "attacking":
                        continue
                    print(f"{hero.name}    level: {hero.level}    atk: {hero.atk}+{hero.round_buff_atk}    hp: {hero.hp}+{hero.defense}    ", end="")
                    if not hero.is_alive:
                        print(f"round until alive: {hero.round_until_alive}")
                    else:
                        print("")
                print("")
                for hero in state["opponent_heroes"]:
                    if hero.state == "attacking":
                        print(f"Attacking hero: {hero.name}    level: {hero.level}    atk: {hero.atk}+{hero.round_buff_atk}   hp: {hero.hp}+{hero.defense}    ", end="")
                        if not hero.is_alive:
                            print(f"round until alive: {hero.round_until_alive}")
                        else:
                            print("")
                print("")
                for hero in state["player_heroes"]:
                    if hero.state == "attacking":
                        print(f"Your attacking hero: {hero.name}    level: {hero.level}    atk: {hero.atk}+{hero.round_buff_atk}    hp: {hero.hp}+{hero.defense}    ", end="")
                        if not hero.is_alive:
                            print(f"round until alive: {hero.round_until_alive}")
                        else:
                            print("")
                print("")
                print(f"Your heroes:")
                for hero in state["player_heroes"]:
                    if hero.state == "attacking":
                        continue
                    print(f"{hero.name}    level: {hero.level}    atk: {hero.atk}+{hero.round_buff_atk}    hp: {hero.hp}+{hero.defense}    ", end="")
                    if not hero.is_alive:
                        print(f"round until alive: {hero.round_until_alive}")
                    else:
                        print("")
                print("")
                print("Your hand:")
                for card in state["player_hand"]:
                    print(card, end="    ")
                print("\n")
                print(f"Your hp: {state["player_hp"]}    Attack available: {state["attack_available"]}    Your fire count: {state["fire_remaining"]}    Your deck size: {state["player_deck_size"]}")
                print("")