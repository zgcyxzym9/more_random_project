import torch
import sys
import os
sys.path.insert(0, "E:/more_random_project")

from game_core.game import Game
from game_core.player import InferencePlayer, InferenceOpponent
from rl.actor_critic import ActorCritic
from game_core.agent import IOAgent
from game_core.card import Card
from game_core.enums import CardAttributes
from env.env import RandomOpponentGameEnv
from rl.utils import match_by_caps

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
root_dict = "E:/more_random_project"
model = ActorCritic(243, 39).to(device=device)
model.load_state_dict(torch.load("./logs/2026-02-20_00-13-35/ppo_actor_critic_2.pt"))

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

player1 = InferencePlayer(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng", "ShengKai"], player_heroes)
player2 = InferenceOpponent(["WuShiZhiQuan", "WuShiZhiQuan", "WuShiZhiDi", "WuShiZhiDi", "WuShiZhiLi", "WuShiZhiLi", "WuShiZhiRen", "WuShiZhiRen", "TianXieGuiChiRanShao", "TianXieGuiChiRanShao", "TianXieGuiHuangGuWu", "TianXieGuiHuangGuWu", "TianXieGuiQingYuanJi", "TianXieGuiQingYuanJi", "TianXieGuiLvPaiDa", "TianXieGuiLvPaiDa", "XinZhan", "XinZhan", "XinJiGuiChu", "XinJiGuiChu", "EJiZhan", "EJiZhan", "XinJianLuanWu", "XinJianLuanWu", "TaoZhiXinXi", "TaoZhiXinXi", "HuaXinFeng", "HuaXinFeng", "FengShi", "FengShi", "TaoYuChunFeng", "TaoYuChunFeng", "ShengKai"], opponent_heroes)
game = Game([player1, player2])
ioagent1 = IOAgent(game, player1)
# We use a env to get obs and action masks, should use Env instead of RandomOpponentGameEnv in the future
env = RandomOpponentGameEnv()
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
        action_id = model.act_inference(obs, action_mask)
        action = env.decode_action(player1, action_id)
        input(f"\nModel's action: {action}\nPress enter to continue\n")
        game.step(player1, action)
    else:
        legal_actions = player2.get_legal_actions()
        legal_actions = [action for action in legal_actions if action.type != "play card"]
        print("Here are all the possible actions of the opponent:")
        for i in range(len(legal_actions)):
            print(f"[{i+1}] {legal_actions[i]}")
        print(f"[{len(legal_actions) + 1}] play a card")
        _ = int(input(f"\n Please enter the opponent's move: ")) - 1
        if _ < len(legal_actions):
            game.step(player2, legal_actions[_])
        else:
            while True:
                _ = input(f"Please enter the card played by the opponent: ")
                card_name = match_by_caps(card_names, _)
                if card_name is not None:
                    card_obj = Card.GetCard(card_name)
                    break
            if card_obj.id == 17:
                for hero in player2.heroes:
                    if hero.id == 3:
                        qs = hero
                        break
                print(qs.level)
                card_obj.attributes = [CardAttributes.INSTANT] if qs.level == 2 else [CardAttributes.NO_FIRE_CONSUMPTION] if qs.level == 3 else []
            while True:
                for attribute, value in vars(card_obj).items():
                    print(attribute, "=", value)
                _ = int(input(f"Is the above card exactly the card actually played by the opponent? \n[1] Yes \n[2] No\n")) - 1
                if _:
                    attr = input(f"Please enter the mismatching field")
                    value = input(f"Please enter the correct value for {attr}")
                    setattr(card_obj, attr, value)
                else:
                    break
            card_obj.assign_owner(player2)
            player2.hand.cards[0] = card_obj
            from game_core.action import PlayCard
            game.step(player2, PlayCard(card_obj))





































print("That is the end of the game!")
print("If you make it to this message, you probably already have a fully functional and accurate game and model. Congratulations!")
print("also hopefully you've also beaten your cat")