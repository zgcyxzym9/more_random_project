from .enums import PlayerState

def select_target(player, target_list, card):
    player.candidate_targets = target_list
    player.state = PlayerState.SELECTING_TARGET
    player.pending_card = card

def select_random_target(player, target_list):
    if type(player).__name__ == "Player":
        import random as r
        return r.choice(target_list)
    elif type(player).__name__ == "InferencePlayer":
        for i in range(len(target_list)):
            print(f"[{i+1}] {target_list[i]}")
        target_id = int(input("Which target was chosen randomly?\n")) - 1
        return target_list[target_id]

def IsDamaged(target_list):
    sel = []
    for target in target_list:
        if target.hp < target.current_max_hp and target.hp > 0:
            sel.append(target)
    return sel

def IsDead(target_list):
    sel = []
    for target in target_list:
        if not target.is_alive:
            sel.append(target)
    return sel