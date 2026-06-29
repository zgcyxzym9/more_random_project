"""
inference_full_game.py  (GUI edition)
--------------------------------------
Original CLI interactions replaced by GUIBridge calls.
The game loop runs in a background thread; Tkinter runs on the main thread.
"""

import torch
import sys
import os
import threading

sys.path.insert(0, "E:/more_random_project")

from game_core.game import Game
from game_core.player import InferencePlayer, InferenceOpponent
from rl_dqn.agent import DoubleDQNAgent
from game_core.agent import IOAgent
from game_core.card import Card
from game_core.enums import CardAttributes
from game_core.action import PlayCard
from env.env import Env
from rl.utils import match_by_caps

# ── GUI imports ──────────────────────────────────────────────────────────────
from rl_dqn.inference_full_game_gui import InferenceGUI, GUIBridge, CaptureBackend, InputMode, build_snapshot_from_game
from rl_dqn.game_frame_capture import DEFAULT_TODESK_TITLE
from rl_dqn.hero_recognizer import HeroRecognizer

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
root_dict = "E:/more_random_project"

# ── Load model ───────────────────────────────────────────────────────────────
model = DoubleDQNAgent(251, 36, device)
model.q_net.load_state_dict(
    torch.load("./logs/dqn/2026-03-17_14-34-54/dqn_model_1.pt"))
model.q_net.eval()

# ── Load name lists ──────────────────────────────────────────────────────────
with open(os.path.join(root_dict, "game_core/cards/card_names.txt"),
          'r', encoding='utf-8') as f:
    card_names = [line.strip() for line in f if line.strip()]
with open(os.path.join(root_dict, "game_core/hero_names.txt"),
          'r', encoding='utf-8') as f:
    hero_names = [line.strip() for line in f if line.strip()]

def extract_uppercase(input_string):
    """
    提取字符串中所有大写字母，并返回由这些大写字母组成的新字符串。
    
    参数:
    input_string (str): 输入的字符串
    
    返回:
    str: 只包含大写字母的新字符串
    """
    # 使用列表推导式遍历字符串，筛选出大写字母
    uppercase_chars = [char for char in input_string if char.isupper()]
    # 将列表连接成字符串
    return ''.join(uppercase_chars)


def detect_opening_heroes(bridge: GUIBridge, timeout: float = 20.0):
    assets_dir = os.path.join(root_dict, "game_core/assets")
    done = threading.Event()
    result_holder = [None]

    def on_result(result):
        result_holder[0] = result
        done.set()

    bridge.log("[hero] Waiting for fixed opening board scene...", "sys")
    recognizer = HeroRecognizer(
        assets_dir,
        window_title_hint=DEFAULT_TODESK_TITLE,
        confirm_frames=1,
        poll_idle=0.05,
        poll_active=0.03,
    )
    try:
        recognizer.start(on_result)
        done.wait(timeout)
    except Exception as exc:
        bridge.log(f"[hero] auto recognition failed: {exc}", "warn")
    finally:
        recognizer.stop()

    result = result_holder[0]
    if result is None:
        bridge.log("[hero] no opening scene detected; using manual input", "warn")
        return None
    if not result.all_confident(0.45):
        low = ", ".join(result.low_confidence_slots(0.45))
        bridge.log(f"[hero] low confidence slots ({low}); using manual input", "warn")
        return None

    bridge.log(f"[hero] player: {', '.join(result.player_heroes)}", "good")
    bridge.log(f"[hero] opponent: {', '.join(result.opponent_heroes)}", "good")
    return result.player_heroes, result.opponent_heroes


# ─────────────────────────────────────────────────────────────────────────────
#  GAME LOOP  (runs in a background thread)
# ─────────────────────────────────────────────────────────────────────────────

def game_loop(bridge: GUIBridge):

    # ── Hero selection ────────────────────────────────────────────────────────
    detected = detect_opening_heroes(bridge)
    if detected:
        auto_answers = list(detected[0]) + list(detected[1])
        auto_answers = [extract_uppercase(i) for i in auto_answers]
        original_ask = bridge.ask

        def ask_with_detected_heroes(prompt: str) -> str:
            if auto_answers and (
                prompt.startswith("Player hero") or prompt.startswith("Opponent hero")
            ):
                return auto_answers.pop(0)
            return original_ask(prompt)

        bridge.ask = ask_with_detected_heroes

    player_heroes = []
    for i in range(4):
        while True:
            raw = bridge.ask(f"Player hero {i+1} / 4:")
            name = match_by_caps(hero_names, raw)
            if name:
                player_heroes.append(name)
                bridge.log(f"  ✓ {name}", "good")
                break
            bridge.log(f"  ✗ '{raw}' not found, try again", "warn")

    opponent_heroes = []
    for i in range(4):
        while True:
            raw = bridge.ask(f"Opponent hero {i+1} / 4:")
            name = match_by_caps(hero_names, raw)
            if name:
                opponent_heroes.append(name)
                bridge.log(f"  ✓ {name}", "good")
                break
            bridge.log(f"  ✗ '{raw}' not found, try again", "warn")

    # ── Build players & game ──────────────────────────────────────────────────
    DECK = ["WuShiZhiQuan","WuShiZhiQuan","WuShiZhiDi","WuShiZhiDi",
            "WuShiZhiLi","WuShiZhiLi","WuShiZhiRen","WuShiZhiRen",
            "TianXieGuiChiRanShao","TianXieGuiChiRanShao","TianXieGuiHuangGuWu",
            "TianXieGuiHuangGuWu","TianXieGuiQingYuanJi","TianXieGuiQingYuanJi",
            "TianXieGuiLvPaiDa","TianXieGuiLvPaiDa","XinZhan","XinZhan",
            "XinJiGuiChu","XinJiGuiChu","EJiZhan","EJiZhan","XinJianLuanWu",
            "XinJianLuanWu","TaoZhiXinXi","TaoZhiXinXi","HuaXinFeng","HuaXinFeng",
            "FengShi","FengShi","TaoYuChunFeng","TaoYuChunFeng"]

    player1 = InferencePlayer(DECK, player_heroes)
    player2 = InferenceOpponent(DECK, opponent_heroes)
    game = Game([player1, player2])
    ioagent1 = IOAgent(game, player1)
    env = Env()
    env.game, env.player1, env.player2 = game, player1, player2

    game.start_game()

    raw = bridge.ask("Are you the first player?\n  1 = No   2 = Yes")
    is_first = raw.strip() == "2"
    if is_first:
        game.player1, game.player2 = player1, player2
        player1.defense, player2.defense = 0, 5
    else:
        game.player1, game.player2 = player2, player1
        player1.defense, player2.defense = 5, 0

    game.player1.is_first_player = True
    game.player2.is_first_player = False
    game.current_player = game.player1
    game.begin_turn()

    # ── Main loop ─────────────────────────────────────────────────────────────
    while not game.check_end_condition():

        # Refresh GUI state
        snap = build_snapshot_from_game(game, player1, player2)
        bridge.update_state(snap)

        # Show observations (same as before, just logged instead of printed)
        state = game.get_observations(player1)
        ioagent1.PhaseOutState(state)           # This may print to stdout — fine
        bridge.log(f"[obs] Turn {snap.turn} — {snap.current_player}'s move", "sys")

        # ── Player turn (model decides) ───────────────────────────────────────
        if game.current_player == player1:
            obs = torch.tensor(env.get_obs(player1),
                               dtype=torch.float32, device=device)
            action_mask = env.get_action_masks(player1)
            action_id   = model.select_action(
                obs.cpu().numpy(), action_mask.cpu().numpy(), epsilon=0.0)
            action = env.decode_action(player1, action_id)

            bridge.show_model_action(str(action))
            bridge.wait_continue("▶ Execute model action?  Press OK")
            game.step(player1, action)
            bridge.log(f"[AI] executed: {action}", "ai")

        # ── Opponent turn (human inputs) ──────────────────────────────────────
        else:
            legal = player2.get_legal_actions()
            non_card = [a for a in legal if a.type != "play card"]

            choice = bridge.show_opponent_actions(non_card)

            if isinstance(choice, tuple) and choice[0] == "play_card":
                # User clicked "Play a card" → loop until valid name
                card_name = choice[1]
                while True:
                    cn = match_by_caps(card_names, card_name)
                    if cn:
                        card_name = cn
                        break
                    card_name = bridge.ask(f"'{card_name}' not found. Try again:")

                # Locate / inject card into opponent's hand (same logic as original)
                card_obj = _resolve_opponent_card(card_name, player2)

                # Verify card attributes via GUI
                card_obj = _verify_card(card_obj, bridge, player2)
                card_obj.assign_owner(player2)
                player2.hand.cards[0] = card_obj
                game.step(player2, PlayCard(card_obj))
                bridge.log(f"[opp] played card: {card_name}", "opp")
            else:
                game.step(player2, choice)
                bridge.log(f"[opp] action: {choice}", "opp")

    # ── Game over ─────────────────────────────────────────────────────────────
    bridge.log("═══ GAME OVER ═══", "warn")
    bridge.wait_continue("Game ended. Press OK to close.")


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_opponent_card(card_name: str, player2) -> "Card":
    """
    Find/inject card into opponent's hand — identical logic to original script.
    """
    card_obj = None
    for card in player2.hand.cards:
        if card.eng_name == card_name:
            return card

    for i, card in enumerate(player2.deck.cards):
        if card.eng_name == card_name:
            player2.hand.cards[0], player2.deck.cards[i] = \
                player2.deck.cards[i], player2.hand.cards[0]
            return player2.hand.cards[0]

    for i, card in enumerate(player2.hand.cards):
        if card.eng_name not in player2.starting_deck:
            card_obj = Card.GetCard(card_name)
            card_obj.assign_owner(player2)
            player2.hand.cards[i] = card_obj
            return card_obj

    for i, card in enumerate(player2.deck.cards):
        if card.eng_name not in player2.starting_deck:
            card_obj = Card.GetCard(card_name)
            card_obj.assign_owner(player2)
            player2.deck.cards[i] = card_obj
            player2.hand.cards[0], player2.deck.cards[i] = \
                player2.deck.cards[i], player2.hand.cards[0]
            return player2.hand.cards[0]

    # Fallback: overwrite first hand card
    card_obj = Card.GetCard(card_name)
    card_obj.assign_owner(player2)
    player2.hand.cards[0] = card_obj
    return card_obj


def _verify_card(card_obj, bridge: GUIBridge, player2) -> "Card":
    """
    Let user correct any mismatching card attributes via the GUI.
    Loops until confirmed.
    """
    while True:
        # Display card fields in the log
        bridge.log("── Card attributes ──", "sys")
        for attr, val in vars(card_obj).items():
            bridge.log(f"  {attr} = {val}", "sys")

        answer = bridge.ask("Correct? (y / field_name to fix)")
        if answer.lower() in ("y", "yes", ""):
            break

        attr = answer.strip()
        if not hasattr(card_obj, attr) and attr != "attributes":
            bridge.log(f"Unknown field '{attr}'", "warn")
            continue

        if attr == "attributes":
            bridge.log("CardAttributes options:", "sys")
            for idx, a in enumerate(CardAttributes):
                bridge.log(f"  {idx+1}. {a.name}", "sys")
            raw = bridge.ask("Enter attribute numbers, comma-separated:")
            try:
                value = [CardAttributes(int(x.strip()))
                         for x in raw.split(",")]
            except ValueError:
                bridge.log("Invalid input", "warn")
                continue
        else:
            raw = bridge.ask(f"New value for '{attr}':")
            if isinstance(getattr(card_obj, attr, None), int):
                try:
                    value = int(raw)
                except ValueError:
                    bridge.log("Expected an integer", "warn")
                    continue
            else:
                value = raw

        setattr(card_obj, attr, value)
        bridge.log(f"  ✓ {attr} = {value}", "good")

    return card_obj


# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def _make_gui_input(bridge: GUIBridge):
    """
    Return a callable that replaces builtins.input() for the game-loop thread.

    Any call to input() from inside the game engine (player.draw(), mulligan,
    etc.) is redirected to the GUI — no changes to game_core required.

    The patch is applied globally before game.start_game() is called, and
    restored after the GUI closes.
    """
    def _gui_input(prompt: str = "") -> str:
        bridge.log(f"[draw prompt] {prompt.strip()}", "warn")
        return bridge.ask(prompt.strip() or "Input required:")
    return _gui_input


if __name__ == "__main__":
    import builtins

    # Build GUI (stays on main thread for Tk stability)
    gui = InferenceGUI(mode=InputMode.MANUAL,
                       capture_backend=CaptureBackend())   # swap real backend here
    bridge = GUIBridge(gui)

    # Patch builtins.input BEFORE the game thread starts so that any call
    # to input() from anywhere in the game engine (including player.draw(),
    # mulligan, etc.) is routed through the GUI bridge.
    _original_input = builtins.input
    builtins.input = _make_gui_input(bridge)

    # Launch game loop in a background thread
    t = threading.Thread(target=game_loop, args=(bridge,), daemon=True)
    t.start()

    # Tk event loop — blocks until window is closed
    gui.run()

    # Restore original input after GUI closes (good practice)
    builtins.input = _original_input
