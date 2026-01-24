def select_target(player, target_list, card):
    player.candidate_targets = target_list
    player.state = "selecting target"
    player.pending_card = card
    action = player.agent.act()
    player.game.step(player, action)
    player.state = "playing"
    player.candidate_targets = []
    player.pending_card = None