import torch
import sys
import os
sys.path.insert(0, "E:/more_random_project_vibe")

from game_core.game import Game
from game_core.player import InferencePlayer, InferenceOpponent
from rl_dqn.agent import DoubleDQNAgent
from game_core.agent import IOAgent
from game_core.card import Card
from game_core.enums import CardAttributes
from env.env import Env
from env.actions import OBS_DIM
from rl.utils import match_by_caps

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
root_dict = "E:/more_random_project_vibe"
from env.actions import ACTION_DIM
model = DoubleDQNAgent(OBS_DIM, ACTION_DIM, device)
# 加载最新训练好的模型（如无则跳过，纯手动输入）
import glob as _glob
import os as _os
model_path = None
checkpoints = sorted(_glob.glob(_os.path.join(root_dict, "logs/dqn/*/dqn_model.pt")))
if checkpoints:
    model_path = checkpoints[-1]
    print(f"Loading model from: {model_path}")
    model.q_net.load_state_dict(torch.load(model_path, map_location=device))
else:
    print("No trained model found, running in manual mode (model suggestions will be random)")
model.q_net.eval()

with open(os.path.join(root_dict, "game_core/cards/card_names.txt"), 'r', encoding='utf-8') as file:
    card_names = [line.strip() for line in file if line.strip()]
with open(os.path.join(root_dict, "game_core/hero_names.txt"), 'r', encoding='utf-8') as file:
    hero_names = [line.strip() for line in file if line.strip()]

# We will not manually input this part for the sake of debugging
player_heroes = []
for i in range(4):
    while True:
        _ = input(f"Please enter hero No.{i+1} of the player: ")
        hero_name = match_by_caps(hero_names, _)
        if hero_name is not None:
            player_heroes.append(hero_name)
            break
opponent_heroes = []
for i in range(4):
    while True:
        _ = input(f"Please enter hero No.{i+1} of the opponent: ")
        hero_name = match_by_caps(hero_names, _)
        if hero_name is not None:
            opponent_heroes.append(hero_name)
            break
"""
player_heroes = ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"]
opponent_heroes = ["ZhiRenWuShi", "TianXieGuiTuanHuo", "QuanShen", "TaoHuaYao"]
"""

# 牌组在运行前硬编码在此处。请根据你的实际牌组修改。
# 格式：每种卡牌名出现对应数量（通常每种 2 张，共 32 张）
player_deck = ["WuShiZhiQuan","WuShiZhiQuan","WuShiZhiDi","WuShiZhiDi",
               "WuShiZhiLi","WuShiZhiLi","WuShiZhiRen","WuShiZhiRen",
               "TianXieGuiChiRanShao","TianXieGuiChiRanShao","TianXieGuiHuangGuWu",
               "TianXieGuiHuangGuWu","TianXieGuiQingYuanJi","TianXieGuiQingYuanJi",
               "TianXieGuiLvPaiDa","TianXieGuiLvPaiDa","XinZhan","XinZhan",
               "XinJiGuiChu","XinJiGuiChu","EJiZhan","EJiZhan","XinJianLuanWu",
               "XinJianLuanWu","TaoZhiXinXi","TaoZhiXinXi","HuaXinFeng","HuaXinFeng",
               "FengShi","FengShi","TaoYuChunFeng","TaoYuChunFeng"]

player1 = InferencePlayer(player_deck, player_heroes)
player2 = InferenceOpponent(opponent_heroes)
game = Game([player1, player2])
ioagent1 = IOAgent(game, player1)
env = Env()
env.game = game
env.player1 = player1
env.player2 = player2

game.start_game()
is_first_player = int(input(f"Are you the first player? \n[1]: No \n[2]: Yes \n")) - 1
if is_first_player:
    game.player1, game.player2 = player1, player2
    player1.defense = 0
    player2.defense = 5
else:
    game.player1, game.player2 = player2, player1
    player1.defense = 5
    player2.defense = 0
game.player1.is_first_player = True
game.player2.is_first_player = False
game.current_player = game.player1

game.begin_turn()

while not game.check_end_condition():
    """
    The following code is intended to remove any inconsistencies between the 
    simulation and the game, should any error occurs due to either partially
    observations or simulation inaccuracies.
    However, for now, this will be implemented later due to the intense 
    timeline.
    """
    state = game.get_observations(player1)
    ioagent1.PhaseOutState(state)
    """
    _ = int(input(f"Is the current state correct?\n[1] Yes, proceed\n[2] No, let's correct it\n")) - 1
    if _:
        _ = input(f"Please select where is incorrect\n")
        continue
    """


    if game.current_player == player1:
        obs = torch.tensor(env.get_obs(player1), dtype=torch.float32, device=device)
        action_mask = env.get_action_masks(player1)
        action_id = model.select_action(obs.cpu().numpy(), action_mask.cpu().numpy(), epsilon=0.0)
        action = env.decode_action(player1, action_id)
        input(f"\nModel's action: {action}\nPress enter to continue\n")
        game.step(player1, action)
    else:
        legal_actions = player2.get_legal_actions()
        legal_actions = [action for action in legal_actions if action.type != "play card"]
        print("Here are all the possible actions of the opponent:")
        for i in range(len(legal_actions)):
            action = legal_actions[i]
            if action.type == "select target" and hasattr(action, 'target'):
                tag = "[我方]" if action.target.owner == player1 else "[敌方]"
                print(f"[{i+1}] {action} {tag}")
            else:
                print(f"[{i+1}] {action}")
        print(f"[{len(legal_actions) + 1}] play a card")
        try:
            _ = int(input(f"\n Please enter the opponent's move: ")) - 1
        except ValueError:
            print("Invalid input. Please enter a number.")
            continue
        if _ < len(legal_actions):
            game.step(player2, legal_actions[_])
        else:
            while True:
                _ = input(f"Please enter the card played by the opponent: ")
                card_name = match_by_caps(card_names, _)
                # If the card is in opponent's hand, it will remain as is; If the card is in opponent's
                # deck, we will swap it with the first card in opponent's hand; Otherwise we will check
                # if there's a card in opponent's hand or deck that's not in the starting deck and
                # replace that card, then move it to the hand if the card is in the deck; Otherwise
                # we'll swap out a random card in opponent's hand.
                if card_name is not None:
                    card_obj = None
                    for card in player2.hand.cards:
                        if card.eng_name == card_name:
                            card_obj = card
                            break
                    if card_obj is None:
                        for i in range(len(player2.deck.cards)):
                            if player2.deck.cards[i].eng_name == card_name:
                                player2.hand.cards[0], player2.deck.cards[i] = player2.deck.cards[i], player2.hand.cards[0]
                                card_obj = player2.hand.cards[0]
                                break
                    if card_obj is None:
                        for i in range(len(player2.hand.cards)):
                            if player2.hand.cards[i].eng_name not in player2.starting_deck:
                                card_obj = Card.GetCard(card_name)
                                card_obj.assign_owner(player2)
                                player2.hand.cards[i] = card_obj
                                break
                    if card_obj is None:
                        for i in range(len(player2.deck.cards)):
                            if player2.deck.cards[i].eng_name not in player2.starting_deck:
                                card_obj = Card.GetCard(card_name)
                                card_obj.assign_owner(player2)
                                player2.deck.cards[i] = card_obj
                                player2.hand.cards[0], player2.deck.cards[i] = player2.deck.cards[i], player2.hand.cards[0]
                                break
                    if card_obj is None:
                        card_obj = Card.GetCard(card_name)
                        card_obj.assign_owner(player2)
                        player2.hand.cards[0] = card_obj
                    break
            
            while True:
                for attribute, value in vars(card_obj).items():
                    print(attribute, "=", value)
                _ = int(input(f"Is the above card exactly the card actually played by the opponent? \n[1] Yes \n[2] No\n")) - 1
                if _:
                    attr = input(f"Please enter the mismatching field")
                    match attr:
                        case "attributes":
                            print("Here are all the possible attributes:")
                            idx = 0
                            for a in CardAttributes:
                                print(f"[{idx + 1}] {a.name}")
                                idx += 1
                            value = input(f"Please enter the correct value for {attr} (separate multiple attributes with commas)")
                            value = [CardAttributes(int(a.strip())) for a in value.split(",")]
                        case _:
                            try:
                                if type(getattr(card_obj, attr)) == int:
                                    value = int(input(f"Please enter the correct value for {attr}"))
                                else:
                                    value = input(f"Please enter the correct value for {attr}")
                            except AttributeError:
                                value = input(f"Please enter the correct value for {attr}")
                                try:
                                    value = int(value)
                                except ValueError:
                                    pass
                    setattr(card_obj, attr, value)
                else:
                    break
            card_obj.assign_owner(player2)
            player2.hand.cards[0] = card_obj
            from game_core.action import PlayCard
            game.step(player2, PlayCard(card_obj))