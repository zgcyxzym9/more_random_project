"""
inference_full_game.py  (GUI edition)
--------------------------------------
Original CLI interactions replaced by GUIBridge calls.
The game loop runs in a background thread; Tkinter runs on the main thread.

临时接入 deck_strength 实验训练的 deck1 最终模型（finetune_vs_deck3）：
卡组为 game_loop 内的 DECK 列表（deck1，配套式神 山童/凤凰火/妖刀姬/白狼），
模型路径在下方 torch.load 处手动修改。运行（仓库根目录）：
    .venv/Scripts/python.exe -m rl_dqn.inference_full_game_gui_base
"""

import torch
import sys
import os
import random
import threading
from typing import Optional

sys.path.insert(0, "E:/more_random_project_vibe")

from game_core.game import Game
from game_core.player import InferencePlayer, InferenceOpponent
from rl_dqn.agent import DoubleDQNAgent
from game_core.agent import IOAgent
from game_core.card import Card
from game_core.enums import CardAttributes
from game_core.action import EndTurn, PlayCard
from env.env import Env
from env.actions import OBS_DIM
from rl.utils import match_by_caps

# ── GUI imports ──────────────────────────────────────────────────────────────
from rl_dqn.inference_full_game_gui import (
    InferenceGUI, GUIBridge, CaptureBackend, InputMode,
    OpponentSyncMode, build_snapshot_from_game,
)
from rl_dqn.game_frame_capture import DEFAULT_TODESK_TITLE
from rl_dqn.hero_recognizer import HeroRecognizer
from rl_dqn.opening_recognizer import OpeningSceneRecognizer
from rl_dqn.game_recorder import GameRecorder, new_seed

# ── Battle-log sync imports ────────────────────────────────────────────────────
from rl_dqn.battle_log_models import BattleLogEntry, SyncStep, SyncResult
from rl_dqn.battle_log_parser import BattleLogParser
from rl_dqn.battle_log_synchronizer import StateSyncEngine

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
root_dict = "E:/more_random_project_vibe"

# ── Load model ───────────────────────────────────────────────────────────────
from env.actions import ACTION_DIM as _ACT_DIM
model = DoubleDQNAgent(OBS_DIM, _ACT_DIM, device)
# deck1 最终版（finetune_vs_deck3 微调轮产物）——临时接入，换模型时改这里的路径
model.q_net.load_state_dict(
    torch.load(os.path.join(root_dict,
              "experiments/deck_strength/results/deck1/finetune_vs_deck3/dqn_model.pt"),
              map_location=device))
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


def match_full(names, raw):
    """
    全文匹配：先精确比较，再忽略大小写；无匹配返回 None。

    仅用于式神识别结果的匹配——大写字母比对（match_by_caps）在
    山童 ShanTong / 山兔 ShanTu 这类大写字母重名时无法区分；
    手动输入仍由 match_by_caps 兜底。
    """
    raw = (raw or "").strip()
    if not raw:
        return None
    for n in names:
        if n == raw:
            return n
    for n in names:
        if n.lower() == raw.lower():
            return n
    return None


def detect_opening_heroes(bridge: GUIBridge, timeout: float = 60.0):
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

def game_loop(bridge: GUIBridge, capture_backend: Optional[CaptureBackend] = None):

    # ── 对局记录器：全程状态+操作落盘 runs/*.jsonl（越早创建越好，
    #    以捕获开局识别/手牌输入等全部交互）────────────────────────────────────
    recorder = GameRecorder()
    recorder.hook_bridge(bridge)
    bridge.log(f"[rec] 对局记录: {recorder.path}", "sys")

    # ── Pre-initialise OCR before anything else ────────────────────────────────
    # This must happen BEFORE hero/opening detection so that OCR is ready by
    # the time the game starts — initialisation is slow and would otherwise
    # block mid-game.
    if capture_backend is not None:
        bridge.log("[ocr] Initialising OCR engine (this may take a moment)...", "sys")
        ok = capture_backend.pre_init()
        if ok:
            bridge.log("[ocr] OCR engine ready.", "good")
        else:
            bridge.log("[ocr] OCR initialisation FAILED — sync will be unavailable.", "warn")

    # ── Hero selection ────────────────────────────────────────────────────────
    detected = detect_opening_heroes(bridge)
    if detected:
        auto_answers = list(detected[0]) + list(detected[1])
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
            name = match_full(hero_names, raw) or match_by_caps(hero_names, raw)
            if name:
                player_heroes.append(name)
                bridge.log(f"  ✓ {name}", "good")
                break
            bridge.log(f"  ✗ '{raw}' not found, try again", "warn")

    opponent_heroes = []
    for i in range(4):
        while True:
            raw = bridge.ask(f"Opponent hero {i+1} / 4:")
            name = match_full(hero_names, raw) or match_by_caps(hero_names, raw)
            if name:
                opponent_heroes.append(name)
                bridge.log(f"  ✓ {name}", "good")
                break
            bridge.log(f"  ✗ '{raw}' not found, try again", "warn")

    # ── Auto-detect opening sequence (first/second + initial hand) ──────────
    bridge.log("[opening] Waiting for first/second player indicator...", "sys")
    opening_recognizer = OpeningSceneRecognizer(
        window_title_hint=DEFAULT_TODESK_TITLE,
    )
    turn_result = opening_recognizer.detect_turn_order(timeout=30.0)
    if turn_result:
        bridge.log(
            f"[opening] Turn order: {'先手 (first)' if turn_result.is_first else '后手 (second)'} "
            f"(text='{turn_result.raw_text}')", "good")
        is_first_auto = turn_result.is_first
    else:
        bridge.log("[opening] Turn order detection failed — will ask manually", "warn")
        is_first_auto = None

    # Detect initial hand cards
    hand_result = None
    bridge.log("[opening] Waiting for initial hand cards...", "sys")
    hand_result = opening_recognizer.detect_initial_hand(timeout=30.0)
    if hand_result:
        names = hand_result.card_eng_names()
        bridge.log(f"[opening] Initial hand: {', '.join(names)}", "good")
        for c in hand_result.cards:
            bridge.log(f"  Card {c.position_index+1}: {c.cn_name} ({c.eng_name}) conf={c.confidence:.2f}", "sys")
    else:
        bridge.log("[opening] Initial hand detection failed", "warn")

    opening_recognizer.close()

    # ── Build players & game ──────────────────────────────────────────────────
    # deck1（山童/凤凰火/妖刀姬/白狼）——deck_strength 实验的训练卡组，
    # 须与上方加载的模型配套；换卡组时同步换模型路径
    DECK = ["GuaiLi","GuaiLi","NuHou","NuHou","BenZhuo","BenZhuo",
            "SiJi","BengShan","FengMing","FengMing","YinRan","YinRan",
            "FenYu","FengHuo","FengHuo","YanWu",
            "BuXiangZhiRen","BuXiangZhiRen","ZhanYi","ZhanYi",
            "YiShan","YiShan","YaoDaoWanHua","YaoDaoWanHua",
            "QiGong","QiGong","WenShe","WenShe",
            "Li","Li","Hui","JueXingBaiLang"]

    player1 = InferencePlayer(DECK, player_heroes)
    player2 = InferenceOpponent(opponent_heroes)
    # 统一种子：game.rng 与全局 random（CardList.shuffle 用全局模块）需同种子，
    # 记录文件中的 setup.seed 可完整复现本局数字对局
    seed = new_seed()
    random.seed(seed)
    game = Game([player1, player2], seed=seed)
    recorder.bind(game, player1, player2)
    recorder.record_setup(seed=seed, deck=DECK,
                          player_heroes=player_heroes,
                          opponent_heroes=opponent_heroes)
    recorder.attach()
    ioagent1 = IOAgent(game, player1)
    env = Env()
    env.game, env.player1, env.player2 = game, player1, player2

    # 使用 OCR 识别到的初始手牌时，让 player.start_game() 静默发牌，
    # 跳过 5 次手动输入（识别失败时保持原手动输入行为）
    if hand_result is not None and hand_result.cards:
        player1.auto_initial_draw = True
        bridge.log("[opening] Detected hand cards found — skipping manual draw input", "sys")

    game.start_game()

    # Use auto-detected turn order, fall back to manual prompt
    if is_first_auto is not None:
        is_first = is_first_auto
    else:
        raw = bridge.ask("Are you the first player?\n  1 = No   2 = Yes")
        is_first = raw.strip() == "2"
    if is_first:
        game.player1, game.player2 = player1, player2
        player1.defense, player2.defense = 0, 5
    else:
        game.player1, game.player2 = player2, player1
        player1.defense, player2.defense = 5, 0

    # ── Override initial hand with auto-detected cards ──────────────────────
    if hand_result is not None and hand_result.cards:
        detected_names = hand_result.card_eng_names()
        bridge.log("[opening] Overriding digital hand with detected cards...", "sys")
        for i, eng_name in enumerate(detected_names):
            if i >= len(player1.hand.cards):
                break
            # Try to find card in hand first, then deck, then create
            card_obj = None
            for c in player1.hand.cards:
                if c.eng_name == eng_name:
                    card_obj = c
                    break
            if card_obj is None:
                for c in list(player1.deck.cards):
                    if c.eng_name == eng_name:
                        card_obj = c
                        player1.deck.cards.remove(c)
                        break
            if card_obj is None:
                card_obj = Card.GetCard(eng_name)
                card_obj.assign_owner(player1)
            player1.hand.cards[i] = card_obj
            bridge.log(f"  Hand[{i}]: {eng_name}", "good")
        # 手牌覆写属带外修改，单独落账（附当前状态快照）
        recorder.note("hand_override", with_state=True, cards=detected_names)

    game.player1.is_first_player = True
    game.player2.is_first_player = False
    game.current_player = game.player1
    recorder.note("game_start", with_state=True, is_first=is_first,
                  defenses=[player1.defense, player2.defense])
    game.begin_turn()

    # ── Initialise battle-log sync engine ──────────────────────────────────────
    player_heroes_cn = [
        getattr(h, "name", str(h)) for h in player1.heroes
    ]
    opponent_heroes_cn = [
        getattr(h, "name", str(h)) for h in player2.heroes
    ]

    log_parser = BattleLogParser(
        player_heroes_cn=player_heroes_cn,
        opponent_heroes_cn=opponent_heroes_cn,
    )

    sync_engine = StateSyncEngine(game, player1, player2)
    sync_mode = OpponentSyncMode.MANUAL

    # Wire up capture backend with parser
    if capture_backend is not None:
        capture_backend._parser = log_parser
        capture_backend.reset()  # reset continuity for new game

    # Handle sync toggle from GUI (via queue)
    # The GUI's LogSyncPanel toggle pushes events to the GUI queue;
    # we poll the capture state via the bridge during the game loop.
    # For now, we track `sync_mode` as a mutable container so the
    # toggle callback can update it.
    sync_mode_holder = {"mode": OpponentSyncMode.MANUAL}

    def _on_sync_toggle(mode: OpponentSyncMode):
        sync_mode_holder["mode"] = mode
        if mode == OpponentSyncMode.AUTO and capture_backend is not None:
            capture_backend.start(1.0)
            bridge.log("[sync] AUTO mode enabled — battle-log capture started", "good")
            bridge.set_sync_status("capturing")
        else:
            if capture_backend is not None:
                capture_backend.stop()
            bridge.log("[sync] MANUAL mode — battle-log capture stopped", "sys")
            bridge.set_sync_status("idle")

    # Register toggle callback with the GUI's sync panel.
    # Save the original GUI-side handler so both fire (GUI status + game state).
    _original_panel_toggle = bridge.gui._sync_panel._on_toggle
    def _panel_toggle_chain(mode: OpponentSyncMode):
        _on_sync_toggle(mode)
        if _original_panel_toggle:
            _original_panel_toggle(mode)
    bridge.gui._sync_panel._on_toggle = _panel_toggle_chain

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
            # 当前状态 + 即将执行动作的 Q 值（在线网络），供 GUI 显示行更新
            with torch.inference_mode():
                q_value = float(model.q_net(obs.unsqueeze(0))[0, action_id])
            action = env.decode_action(player1, action_id)

            if action is None:
                # 牌已离手等导致解码失败时回退结束回合，避免 game.step(None) 崩溃
                action = EndTurn()
                bridge.log(f"[AI] action_id {action_id} decode failed → EndTurn", "warn")

            bridge.show_model_action(str(action))
            bridge.show_q_value(f"Q(state, action_id={action_id}) = {q_value:.4f}")
            recorder.note("model_decision", action_id=action_id,
                          q_value=round(q_value, 4), action=str(action))

            # ── 同步响应 ─────────────────────────────────────────────────────
            # 真实对局中对方可能对我方操作打出响应牌。引擎在 step 内广播事件时
            # 由 _auto_response 扫描 player2 手牌自动打出响应，因此必须先把真实
            # 触发的响应牌注入对方模拟手牌，再执行操作。
            #   Execute Action 按钮   → 选项1：无响应，直接执行
            #   Handle Response 按钮  → 选项2：输入响应牌名，注入后执行
            choice = bridge.ask_execute_or_response()
            recorder.note("response_choice", choice=choice,
                          action_id=action_id)
            resp_card_name = ""
            if choice == "response":
                while True:
                    raw = bridge.ask_allow_empty(
                        "Response card name (empty Enter = give up response & execute):"
                    ).strip()
                    if not raw:
                        break
                    cn = match_by_caps(card_names, raw)
                    if cn:
                        resp_card_name = cn
                        break
                    bridge.log(f"✗ '{raw}' not found, try again", "warn")

            if resp_card_name:
                resp_card = _resolve_opponent_card(resp_card_name, player2)
                recorder.note("opponent_response_inject", card=resp_card_name)
                bridge.log(f"[resp] response card injected into opponent hand: {resp_card_name}", "opp")
                can_play, why = game.can_play_card(player2, resp_card)
                if not can_play:
                    bridge.log(
                        f"[resp] WARNING: response card can't be played in simulation ({why}) "
                        "— state may desync", "warn")

            game.step(player1, action)
            bridge.log(f"[AI] executed: {action}", "ai")

        # ── Opponent turn ────────────────────────────────────────────────────
        else:
            if sync_mode_holder["mode"] == OpponentSyncMode.AUTO:
                ok = _auto_sync_opponent_turn(
                    game, player2, bridge, sync_engine,
                    card_names, hero_names,
                )
                if not ok:
                    # Auto-sync failed (no entries, log panel not detected, etc.)
                    # Fall back to manual mode for this turn so the game can
                    # continue instead of looping forever.
                    bridge.log("[sync] AUTO failed — falling back to manual input", "warn")
                    bridge.set_sync_status("idle")
                    legal = player2.get_legal_actions()
                    non_card = [a for a in legal if a.type != "play card action"]
                    choice = bridge.show_opponent_actions(non_card)
                    if isinstance(choice, tuple) and choice[0] == "play_card":
                        card_name = choice[1]
                        while True:
                            cn = match_by_caps(card_names, card_name)
                            if cn:
                                card_name = cn
                                break
                            card_name = bridge.ask(f"'{card_name}' not found. Try again:")
                        card_obj = _resolve_opponent_card(card_name, player2)
                        # 暂时跳过 _verify_card 逐卡确认（需要时恢复此行）：
                        # card_obj = _verify_card(card_obj, bridge, player2)
                        recorder.note("opponent_card_inject", card=card_name)
                        card_obj.assign_owner(player2)
                        player2.hand.cards[0] = card_obj
                        game.step(player2, PlayCard(card_obj))
                    else:
                        game.step(player2, choice)
                    bridge.log(f"[opp] action (manual fallback): {choice}", "opp")
            else:
                # ── MANUAL mode (original behaviour) ──────────────────────
                legal = player2.get_legal_actions()
                non_card = [a for a in legal if a.type != "play card action"]

                choice = bridge.show_opponent_actions(non_card)

                if isinstance(choice, tuple) and choice[0] == "play_card":
                    card_name = choice[1]
                    while True:
                        cn = match_by_caps(card_names, card_name)
                        if cn:
                            card_name = cn
                            break
                        card_name = bridge.ask(f"'{card_name}' not found. Try again:")

                    card_obj = _resolve_opponent_card(card_name, player2)
                    # 暂时跳过 _verify_card 逐卡确认（需要时恢复此行）：
                    # card_obj = _verify_card(card_obj, bridge, player2)
                    recorder.note("opponent_card_inject", card=card_name)
                    card_obj.assign_owner(player2)
                    player2.hand.cards[0] = card_obj
                    game.step(player2, PlayCard(card_obj))
                    bridge.log(f"[opp] played card: {card_name}", "opp")
                else:
                    game.step(player2, choice)
                    bridge.log(f"[opp] action: {choice}", "opp")

    # ── Game over ─────────────────────────────────────────────────────────────
    recorder.close()   # 写入终局快照并关闭记录文件（每条已实时 flush，中途崩溃也不丢记录）
    bridge.log("═══ GAME OVER ═══", "warn")
    bridge.wait_continue("Game ended. Press OK to close.")


# ─────────────────────────────────────────────────────────────────────────────
#  AUTO-SYNC OPPONENT TURN
# ─────────────────────────────────────────────────────────────────────────────

def _auto_sync_opponent_turn(
    game: "Game",
    player2: "Player",
    bridge: "GUIBridge",
    sync_engine: "StateSyncEngine",
    card_names: list[str],
    hero_names: list[str],
    poll_timeout: float = 2.0,
) -> bool:
    """
    AUTO mode opponent turn: poll battle-log OCR entries and drive game.step().

    Returns True if at least one action was executed or the turn ended naturally.
    Returns False if no entries were found (timeout / log panel not detected).

    Flow
    ----
    1. Poll CaptureBackend for new entries (with timeout)
    2. Process entries through StateSyncEngine → SyncResult
    3. Execute SyncSteps in order:
       - "action"       → game.step(player2, action)
       - "manual_input" → bridge.ask(prompt)
       - "verify"       → skip (done later)
    4. After all steps → verify_after_actions()
    5. If turn_ended → return True
    6. If timeout and no entries → return False
    """
    bridge.set_sync_status("syncing")

    # ── CONSOLE DEBUG: always print to terminal ──
    gui = bridge.gui
    loop = gui.capture._loop
    loop_alive = loop._thread.is_alive() if (loop and loop._thread) else False
    loop_running = loop._running if loop else False
    stats = gui.capture.get_stats()
    metrics = gui.capture.get_detection_metrics()

    print(f"\n{'='*60}")
    print(f"[sync] AUTO opponent turn started")
    print(f"[sync] Capture loop: exists={loop is not None}, running={loop_running}, thread_alive={loop_alive}")
    print(f"[sync] Pipeline: attempts={stats.get('capture_attempts',0)}, "
          f"log_open={stats.get('log_open_count',0)}, "
          f"ocr_texts={stats.get('ocr_texts_total',0)}, "
          f"parsed={stats.get('parsed_entries_total',0)}, "
          f"emitted={stats.get('new_entries_total',0)}")
    print(f"[sync] Detection: is_open={metrics.get('is_open')}, "
          f"dark={metrics.get('dark_ratio', '?'):.3f}, "
          f"panel={metrics.get('panel_ratio', '?'):.3f}"
          f"{'  [PANEL NOT DETECTED]' if not metrics.get('is_open') else ''}")
    if stats.get("last_error"):
        print(f"[sync] Last error: {stats['last_error']}")
    print(f"{'='*60}\n")

    # Also log to GUI
    bridge.log("[sync] AUTO opponent turn started", "sys")
    bridge.log(
        f"[sync] loop_alive={loop_alive} running={loop_running} "
        f"attempts={stats.get('capture_attempts',0)} "
        f"log_open={stats.get('log_open_count',0)} "
        f"ocr={stats.get('ocr_texts_total',0)} "
        f"parsed={stats.get('parsed_entries_total',0)}", "sys")

    import time
    turn_done = False
    empty_polls = 0
    max_empty_polls = 5  # After 5 empty polls (~10s), fall back to manual

    while not turn_done and game.current_player == player2:
        # Check if we should fall back to manual
        if empty_polls >= max_empty_polls:
            bridge.log("[sync] No new entries for too long — check game state", "warn")
            bridge.add_sync_warning(
                f"No log entries after {empty_polls} polls. "
                "Game may have desynced or log panel is closed.", "warn")
            print(f"[sync] TIMEOUT after {empty_polls} empty polls — falling back to manual")
            bridge.set_sync_status("idle")
            return False

        # Poll for new entries via the bridge's gui capture backend
        new_entries = gui.capture.poll_entries(timeout=poll_timeout)

        if not new_entries:
            empty_polls += 1
            if empty_polls == 1:
                metrics = gui.capture.get_detection_metrics()
                print(f"[sync] Poll #{empty_polls} timeout — "
                      f"is_open={metrics.get('is_open')}, "
                      f"dark={metrics.get('dark_ratio', '?'):.3f}, "
                      f"panel={metrics.get('panel_ratio', '?'):.3f}")
                bridge.log(
                    f"[sync] Poll timeout — log panel: "
                    f"is_open={metrics.get('is_open')}, "
                    f"dark={metrics.get('dark_ratio', '?'):.3f} "
                    f"panel={metrics.get('panel_ratio', '?'):.3f}", "sys")
            else:
                print(f"[sync] Poll #{empty_polls} timeout (no new entries)")
            # Check if turn already ended (game state changed)
            if game.current_player != player2:
                turn_done = True
                bridge.log("[sync] Turn ended (game state changed)", "sys")
            continue

        empty_polls = 0  # reset on activity
        bridge.log(f"[sync] Processing {len(new_entries)} new log entries", "sys")

        # Process entries
        result = sync_engine.process_entries(new_entries, bridge)

        # Execute steps in order
        for step in result.steps:
            if step.kind == "action":
                if step.action is not None:
                    game.step(player2, step.action)
                    bridge.log(f"[sync] executed: {step.action}", "sys")
                else:
                    bridge.log(f"[sync] skipped null action for: {step.entry.raw_text}", "warn")

            elif step.kind == "manual_input":
                # Need user input — pause and ask
                answer = bridge.ask(step.prompt or "Manual input required:")
                bridge.log(f"[sync] manual input: {answer}", "sys")
                # The callback in the step may need to process the answer
                if step.input_callback:
                    step.input_callback(answer)

            elif step.kind == "verify":
                # Will be verified after all actions
                pass

        # Verify auxiliary entries after all actions executed
        warnings = sync_engine.verify_after_actions(result)
        for w in warnings:
            bridge.log(f"[sync] WARNING: {w}", "warn")
            bridge.add_sync_warning(w, "warn")

        # Check turn end
        if result.turn_ended:
            turn_done = True
            bridge.log(f"[sync] Turn boundary detected (log turn {result.log_turn_ended})", "sys")

        # Also check game state
        if game.current_player != player2:
            turn_done = True
            bridge.log("[sync] Turn ended (game state changed)", "sys")

    # Cleanup
    bridge.set_sync_status("idle")
    bridge.log("[sync] AUTO opponent turn finished", "sys")
    return True


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

    # Build capture backend (shared between GUI and game loop)
    capture = CaptureBackend()

    # Build GUI (stays on main thread for Tk stability)
    gui = InferenceGUI(mode=InputMode.MANUAL,
                       capture_backend=capture)
    bridge = GUIBridge(gui)

    # Patch builtins.input BEFORE the game thread starts so that any call
    # to input() from anywhere in the game engine (including player.draw(),
    # mulligan, etc.) is routed through the GUI bridge.
    _original_input = builtins.input
    builtins.input = _make_gui_input(bridge)

    # Launch game loop in a background thread
    t = threading.Thread(target=game_loop, args=(bridge, capture), daemon=True)
    t.start()

    # Tk event loop — blocks until window is closed
    gui.run()

    # Restore original input after GUI closes (good practice)
    builtins.input = _original_input
