from .enums import PlayerState

def select_target(player, target_list, card):
    player.candidate_targets = target_list
    player.state = PlayerState.SELECTING_TARGET
    player.pending_card = card

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