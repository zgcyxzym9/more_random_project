"""
inference_gui.py
----------------
Compact overlay GUI for the DQN inference loop.
Replaces inference_full_game.py's CLI interactions with a small,
always-on-top Tkinter window that sits over the actual game screen.

Battle-log OCR auto-sync is implemented via CaptureBackend + LogSyncPanel.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
from enum import Enum, auto
import sys

# ── Battle-log sync imports ────────────────────────────────────────────────────
sys.path.insert(0, "E:/more_random_project_vibe")
from rl_dqn.battle_log_models import BattleLogEntry, SyncStep, SyncResult


# ─────────────────────────────────────────────
#  DATA STRUCTURES
# ─────────────────────────────────────────────

class InputMode(Enum):
    MANUAL   = auto()   # human types everything
    CAPTURE  = auto()   # screen-capture backend feeds data


class OpponentSyncMode(Enum):
    """How the opponent's turn is handled."""
    MANUAL = auto()     # user manually inputs opponent actions
    AUTO   = auto()     # battle-log OCR auto-sync


@dataclass
class GameSnapshot:
    """Mirrors the state visible in game.get_observations()."""
    turn: int = 0
    current_player: str = "?"
    player_hp: int = 0
    player_defense: int = 0
    player_hand: List[str] = field(default_factory=list)
    player_heroes: List[str] = field(default_factory=list)
    opponent_hp: int = 0
    opponent_defense: int = 0
    opponent_hand_count: int = 0
    opponent_heroes: List[str] = field(default_factory=list)
    last_action: str = ""
    model_suggestion: str = ""
    log_lines: List[str] = field(default_factory=list)

    # ── Sync fields ─────────────────────────────────────────────────────────────
    sync_mode: OpponentSyncMode = OpponentSyncMode.MANUAL
    sync_status: str = ""                         # "idle" | "capturing" | "syncing" | "error"
    parsed_entries: List[BattleLogEntry] = field(default_factory=list)
    sync_warnings: List[str] = field(default_factory=list)


# ─────────────────────────────────────────────
#  CAPTURE BACKEND  (stub — replace later)
# ─────────────────────────────────────────────

class CaptureBackend:
    """
    Battle-log OCR capture backend.

    Wraps LogCaptureLoop for integration with the GUI bridge.
    When started, it runs PaddleOCR on the battle-log panel region
    and pushes new entries to the GUI via callback.

    Usage
    -----
    backend = CaptureBackend(grabber, parser)
    backend.set_callback(on_new_entries)
    backend.start(interval=1.0)
    ...
    backend.stop()
    """

    def __init__(self, grabber=None, parser=None, detector=None):
        self._grabber = grabber
        self._parser = parser
        self._detector = detector
        self._loop = None
        self._running = False
        self._callback: Optional[Callable] = None
        # Thread-safe queue for game-loop polling
        self._entry_queue: queue.Queue = queue.Queue()

    def is_available(self) -> bool:
        """Return True when PaddleOCR is installed and ready."""
        try:
            from rl_dqn.battle_log_capture import LogCaptureLoop
            loop = LogCaptureLoop.__new__(LogCaptureLoop)
            return loop._init_ocr() is not None
        except Exception:
            return False

    def pre_init(self) -> bool:
        """
        Eagerly initialise OCR and the capture loop BEFORE the game starts.

        Call this during setup (before game.start_game()) so OCR is ready
        when the opponent's turn begins — no mid-game loading delay.

        Returns True on success.
        """
        from rl_dqn.battle_log_capture import LogCaptureLoop
        try:
            if self._loop is None:
                self._loop = LogCaptureLoop(
                    grabber=self._grabber,
                    parser=self._parser,
                    detector=self._detector,
                )
            return self._loop._ocr is not None
        except Exception:
            return False

    def set_callback(self, callback: Callable[[list[BattleLogEntry]], None]):
        """Set the callback for new battle-log entries."""
        self._callback = callback

    def start(self, interval: float = 1.0):
        """Start the background OCR capture loop."""
        from rl_dqn.battle_log_capture import LogCaptureLoop
        if self._loop is None:
            self._loop = LogCaptureLoop(
                grabber=self._grabber,
                parser=self._parser,
                detector=self._detector,
            )
        self._running = True
        self._loop.start(callback=self._on_entries, interval=interval)

    def stop(self):
        """Stop the background capture loop."""
        self._running = False
        if self._loop:
            self._loop.stop()
            self._loop = None

    def reset(self):
        """Reset continuity tracking."""
        if self._loop:
            self._loop.reset()

    def get_detection_metrics(self) -> dict:
        """Return log-panel detection metrics for debugging."""
        if self._loop:
            return self._loop.get_detection_metrics()
        return {}

    def get_stats(self) -> dict:
        """Return pipeline stats for debugging."""
        if self._loop:
            return self._loop.get_stats()
        return {}

    def poll_entries(self, timeout: float = 0.5) -> list[BattleLogEntry]:
        """
        Block until new entries arrive, or timeout.
        Used by the game loop during AUTO opponent turns.

        Returns empty list on timeout.
        """
        try:
            return self._entry_queue.get(timeout=timeout)
        except queue.Empty:
            return []

    def _on_entries(self, entries: list[BattleLogEntry]):
        # Empty list = periodic status heartbeat; only notify GUI, not game loop
        if not entries:
            if self._callback:
                self._callback(entries)
            return
        # Push to game-loop queue
        self._entry_queue.put(entries)
        # Also notify GUI callback
        if self._callback:
            self._callback(entries)


# ─────────────────────────────────────────────
#  COLOUR / STYLE CONSTANTS
# ─────────────────────────────────────────────

C = {
    "bg":        "#0d0f14",
    "panel":     "#13161e",
    "border":    "#1f2433",
    "accent":    "#4fc3f7",
    "accent2":   "#ef5350",
    "gold":      "#ffd54f",
    "text":      "#c8cdd8",
    "dim":       "#5a6070",
    "success":   "#66bb6a",
    "warn":      "#ffa726",
    "btn":       "#1a2035",
    "btn_hover": "#253050",
}

FONT_MONO  = ("Consolas", 9)
FONT_LABEL = ("Consolas", 8)
FONT_TITLE = ("Consolas", 10, "bold")
FONT_BIG   = ("Consolas", 11, "bold")


# ─────────────────────────────────────────────
#  WIDGET HELPERS
# ─────────────────────────────────────────────

def _panel(parent, **kwargs) -> tk.Frame:
    kw = dict(bg=C["panel"], highlightbackground=C["border"],
              highlightthickness=1)
    kw.update(kwargs)
    return tk.Frame(parent, **kw)


def _label(parent, text="", color=None, font=FONT_LABEL, **kwargs) -> tk.Label:
    return tk.Label(parent, text=text, fg=color or C["text"],
                    bg=parent["bg"], font=font, **kwargs)


def _btn(parent, text, cmd, color=None) -> tk.Button:
    b = tk.Button(
        parent, text=text, command=cmd,
        bg=C["btn"], fg=color or C["accent"],
        activebackground=C["btn_hover"], activeforeground=color or C["accent"],
        relief="flat", bd=0, font=FONT_LABEL, cursor="hand2",
        padx=6, pady=3
    )
    b.bind("<Enter>", lambda e: b.config(bg=C["btn_hover"]))
    b.bind("<Leave>", lambda e: b.config(bg=C["btn"]))
    return b


# ─────────────────────────────────────────────
#  LOG SYNC PANEL
# ─────────────────────────────────────────────

class LogSyncPanel:
    """
    Compact panel showing battle-log sync status and parsed entries.

    Displays:
      - Sync toggle button (AUTO / MANUAL)
      - Status indicator (idle / capturing / syncing / error)
      - Last N parsed entries with colour coding
    """

    MAX_VISIBLE_ENTRIES = 12

    # Entry type → display colour mapping
    TYPE_COLORS = {
        "game_start":       C["gold"],
        "turn_start":       C["gold"],
        "play_card":        C["warn"],
        "play_card_target": C["warn"],
        "attack":           C["accent2"],
        "upgrade":          C["accent"],
        "draw":             C["success"],
        "shuffle":          C["dim"],
        "damage_simple":    C["accent2"],
        "damage_counter":   C["accent2"],
        "stat_change":      C["accent"],
        "attack_bonus":     C["gold"],
        "revive":           C["success"],
        "death":            C["dim"],
        "buff":             C["accent"],
    }

    def __init__(self, parent: tk.Frame,
                 on_toggle: Optional[Callable[[OpponentSyncMode], None]] = None):
        self.parent = parent
        self._on_toggle = on_toggle
        self._mode = OpponentSyncMode.MANUAL
        self._status = "idle"
        self._entries: list[BattleLogEntry] = []
        self._build()

    def _build(self):
        f = _panel(self.parent)
        f.pack(fill="x", padx=6, pady=(0, 4))

        # ── Header row ──
        hdr = tk.Frame(f, bg=f["bg"])
        hdr.pack(fill="x", padx=6, pady=(4, 0))

        self._title_lbl = _label(hdr, "◈ BATTLE LOG SYNC", color=C["gold"],
                                 font=FONT_TITLE)
        self._title_lbl.pack(side="left")

        self._status_lbl = _label(hdr, "● idle", color=C["dim"], font=FONT_LABEL)
        self._status_lbl.pack(side="right", padx=4)

        self._toggle_btn = _btn(hdr, "AUTO", self._on_toggle_click,
                                color=C["dim"])
        self._toggle_btn.pack(side="right", padx=2)

        # ── Sync mode label ──
        self._mode_lbl = _label(f, "[MANUAL]  Opponent actions must be entered manually",
                                color=C["dim"], font=FONT_LABEL)
        self._mode_lbl.pack(anchor="w", padx=6, pady=(0, 2))

        # ── Entries display (scrollable) ──
        entries_frame = tk.Frame(f, bg=f["bg"])
        entries_frame.pack(fill="x", padx=6, pady=(0, 4))

        self._entries_text = tk.Text(
            entries_frame, height=6, bg=C["panel"], fg=C["text"],
            font=FONT_MONO, bd=0, highlightthickness=0,
            state="disabled", wrap="word",
        )
        self._entries_text.pack(fill="x")

        # Colour tags
        for tag_name, color in self.TYPE_COLORS.items():
            self._entries_text.tag_config(tag_name, foreground=color)
        self._entries_text.tag_config("sync_info", foreground=C["dim"])
        self._entries_text.tag_config("sync_warn", foreground=C["warn"])
        self._entries_text.tag_config("sync_error", foreground=C["accent2"])

    # ── Public API ─────────────────────────────────────────────────────────

    def set_mode(self, mode: OpponentSyncMode):
        self._mode = mode
        if mode == OpponentSyncMode.AUTO:
            self._toggle_btn.config(text="MANUAL", fg=C["success"])
            self._mode_lbl.config(
                text="[AUTO]  Battle-log OCR sync active",
                fg=C["success"])
        else:
            self._toggle_btn.config(text="AUTO", fg=C["dim"])
            self._mode_lbl.config(
                text="[MANUAL]  Opponent actions must be entered manually",
                fg=C["dim"])

    def set_status(self, status: str, color: Optional[str] = None):
        self._status = status
        colors = {
            "idle": C["dim"],
            "capturing": C["accent"],
            "syncing": C["gold"],
            "error": C["accent2"],
        }
        c = color or colors.get(status, C["dim"])
        self._status_lbl.config(text=f"● {status}", fg=c)

    def add_entries(self, entries: list[BattleLogEntry]):
        self._entries.extend(entries)
        # Trim
        if len(self._entries) > self.MAX_VISIBLE_ENTRIES * 2:
            self._entries = self._entries[-self.MAX_VISIBLE_ENTRIES:]
        self._refresh_display()

    def add_warning(self, msg: str, severity: str = "warn"):
        tag = f"sync_{severity}"
        self._entries_text.config(state="normal")
        self._entries_text.insert("end", f"  ⚠ {msg}\n", tag)
        self._entries_text.see("end")
        self._entries_text.config(state="disabled")

    def clear(self):
        self._entries.clear()
        self._entries_text.config(state="normal")
        self._entries_text.delete("1.0", "end")
        self._entries_text.config(state="disabled")

    # ── Internal ───────────────────────────────────────────────────────────

    def _on_toggle_click(self):
        if self._mode == OpponentSyncMode.MANUAL:
            new_mode = OpponentSyncMode.AUTO
        else:
            new_mode = OpponentSyncMode.MANUAL
        self.set_mode(new_mode)
        if self._on_toggle:
            self._on_toggle(new_mode)

    def _refresh_display(self):
        self._entries_text.config(state="normal")
        self._entries_text.delete("1.0", "end")

        visible = self._entries[-self.MAX_VISIBLE_ENTRIES:]
        for entry in visible:
            tag = self.TYPE_COLORS.get(entry.entry_type, "")
            prefix = "▶" if entry.is_operational else "  "
            turn_str = f"T{entry.log_turn}" if entry.log_turn else "--"
            self._entries_text.insert("end",
                                      f"{prefix} [{turn_str}] {entry.raw_text}\n", tag)

        self._entries_text.see("end")
        self._entries_text.config(state="disabled")


# ─────────────────────────────────────────────
#  MAIN GUI
# ─────────────────────────────────────────────

class InferenceGUI:
    """
    Compact overlay window (~420 × 680 px).

    Public interface used by the game loop
    ───────────────────────────────────────
    gui.update_snapshot(snap: GameSnapshot)   – refresh all panels
    gui.set_model_action(text: str)           – display AI suggestion
    gui.set_q_value(text: str)                – display Q(state, action) line
    gui.append_log(text: str)                 – add a line to the log
    gui.ask_opponent_action(legal, on_done)   – open opponent input sheet
    gui.ask_input(prompt, on_done)            – simple one-line prompt
    gui.wait_for_continue()                   – blocking pause (confirm step)
    """

    WIDTH  = 420
    HEIGHT = 960

    def __init__(self, mode: InputMode = InputMode.MANUAL,
                 capture_backend: Optional[CaptureBackend] = None):
        self.mode    = mode
        self.capture = capture_backend or CaptureBackend()
        self._q: queue.Queue = queue.Queue()        # thread→UI events
        self._response: queue.Queue = queue.Queue() # UI→thread answers

        # Track the active scrollable canvas so the root-level mousewheel
        # handler can route scroll events to it regardless of which child
        # widget the cursor is over.
        self._active_scroll_canvas: Optional[tk.Canvas] = None

        self._build_window()
        self._build_ui()

        # Set up capture callback
        self.capture.set_callback(self._on_log_entries)

        if mode == InputMode.CAPTURE and self.capture.is_available():
            self.capture.start(1.0)
            self._sync_panel.set_mode(OpponentSyncMode.AUTO)

        # Root-level mousewheel: route to the active scrollable canvas
        # so scrolling works even when the cursor is over child buttons.
        self._root.bind("<MouseWheel>", self._on_root_mousewheel)

        # Poll the cross-thread event queue every 50 ms
        self._root.after(50, self._poll_queue)

    # ── WINDOW ────────────────────────────────

    def _build_window(self):
        self._root = tk.Tk()
        self._root.title("DQN Inference")
        self._root.geometry(f"{self.WIDTH}x{self.HEIGHT}+20+20")
        self._root.resizable(False, False)
        self._root.configure(bg=C["bg"])
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.96)
        # Drag bindings are attached to the title bar widget in _build_ui(),
        # NOT to the root window — this prevents conflicts with scrollbars.
        self._drag_x = self._drag_y = 0

    def _drag_start(self, e):
        # Record position relative to the screen so motion works correctly
        self._drag_x = self._root.winfo_pointerx() - self._root.winfo_rootx()
        self._drag_y = self._root.winfo_pointery() - self._root.winfo_rooty()

    def _drag_motion(self, e):
        x = self._root.winfo_pointerx() - self._drag_x
        y = self._root.winfo_pointery() - self._drag_y
        self._root.geometry(f"+{x}+{y}")

    # ── UI CONSTRUCTION ───────────────────────

    def _build_ui(self):
        root = self._root

        # ── Title bar — drag bindings go here only ─
        bar = tk.Frame(root, bg=C["border"], height=26)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        bar.bind("<ButtonPress-1>", self._drag_start)
        bar.bind("<B1-Motion>",     self._drag_motion)
        title_lbl = _label(bar, "  ◈ DQN INFERENCE", color=C["accent"],
               font=FONT_TITLE)
        title_lbl.pack(side="left", pady=4)
        title_lbl.bind("<ButtonPress-1>", self._drag_start)
        title_lbl.bind("<B1-Motion>",     self._drag_motion)
        self._mode_lbl = _label(bar, f"[{self.mode.name}]",
                                color=C["dim"], font=FONT_LABEL)
        self._mode_lbl.pack(side="left", padx=4)
        tk.Button(bar, text="✕", bg=C["border"], fg=C["dim"],
                  relief="flat", bd=0, font=FONT_LABEL,
                  command=root.destroy).pack(side="right", padx=6)
        self._cap_btn = _btn(bar, "⊙ CAPTURE",
                             self._toggle_capture, color=C["dim"])
        self._cap_btn.pack(side="right", padx=2)

        # ── Turn / player header ────────────────
        hdr = _panel(root)
        hdr.pack(fill="x", padx=6, pady=(4, 0))
        self._turn_lbl   = _label(hdr, "Turn —", color=C["gold"],
                                  font=FONT_BIG)
        self._turn_lbl.pack(side="left", padx=8, pady=4)
        self._active_lbl = _label(hdr, "Waiting…", color=C["dim"],
                                  font=FONT_LABEL)
        self._active_lbl.pack(side="right", padx=8)

        # ── Player / Opponent side-by-side ──────
        sides = tk.Frame(root, bg=C["bg"])
        sides.pack(fill="x", padx=6, pady=4)
        sides.columnconfigure(0, weight=1)
        sides.columnconfigure(1, weight=1)

        self._player_panel   = self._build_side(sides, "PLAYER",  C["accent"], 0)
        self._opponent_panel = self._build_side(sides, "OPPONENT", C["accent2"], 1)

        # ── Model suggestion ───────────────────
        sug = _panel(root)
        sug.pack(fill="x", padx=6, pady=(0, 4))
        _label(sug, " ▶ MODEL", color=C["gold"],
               font=FONT_TITLE).pack(side="left", padx=6, pady=3)
        sug_body = tk.Frame(sug, bg=sug["bg"])
        sug_body.pack(side="left", padx=4, fill="x", expand=True)
        self._sug_lbl = _label(sug_body, "—", color=C["text"], font=FONT_MONO,
                               wraplength=280, justify="left")
        self._sug_lbl.pack(side="top", anchor="w", fill="x")
        # Q(state, 即将执行的动作) 显示行（游戏线程经 set_q_value 更新）
        self._qval_lbl = _label(sug_body, "", color=C["dim"], font=FONT_MONO,
                                justify="left")
        self._qval_lbl.pack(side="top", anchor="w", fill="x")

        # ── Capture status (hidden until active) ─
        self._cap_frame = _panel(root)
        self._cap_frame.pack(fill="x", padx=6, pady=(0, 2))
        self._cap_status = _label(self._cap_frame,
                                  "⊙ Capture inactive — manual mode",
                                  color=C["dim"], font=FONT_LABEL)
        self._cap_status.pack(side="left", padx=6, pady=2)

        # ── Log sync panel ────────────────────
        self._sync_panel = LogSyncPanel(root, on_toggle=self._on_sync_toggle)

        # ── Action input area ──────────────────
        self._input_frame = _panel(root)
        self._input_frame.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._build_input_area()

        # ── Log ───────────────────────────────
        log_hdr = tk.Frame(root, bg=C["bg"])
        log_hdr.pack(fill="x", padx=6)
        _label(log_hdr, "LOG", color=C["dim"], font=FONT_LABEL).pack(side="left")
        _btn(log_hdr, "clear", self._clear_log,
             color=C["dim"]).pack(side="right")
        self._log = scrolledtext.ScrolledText(
            root, height=10, bg=C["panel"], fg=C["text"],
            font=FONT_MONO, bd=0, highlightthickness=0,
            insertbackground=C["accent"], state="disabled",
            relief="flat"
        )
        self._log.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        # Colour tags
        self._log.tag_config("sys",  foreground=C["dim"])
        self._log.tag_config("ai",   foreground=C["gold"])
        self._log.tag_config("opp",  foreground=C["accent2"])
        self._log.tag_config("good", foreground=C["success"])
        self._log.tag_config("warn", foreground=C["warn"])

    def _build_side(self, parent, title, color, col) -> dict:
        f = _panel(parent)
        f.grid(row=0, column=col, sticky="nsew",
               padx=(0 if col else 0, 2 if col == 0 else 0))
        _label(f, title, color=color,
               font=FONT_TITLE).pack(anchor="w", padx=6, pady=(4, 0))
        hp  = _label(f, "HP: —", color=C["text"], font=FONT_MONO)
        hp.pack(anchor="w", padx=6)
        dfs = _label(f, "DEF: —", color=C["text"], font=FONT_MONO)
        dfs.pack(anchor="w", padx=6)
        heroes = _label(f, "", color=C["dim"], font=FONT_LABEL,
                        wraplength=180, justify="left")
        heroes.pack(anchor="w", padx=6)
        hand = _label(f, "", color=C["text"], font=FONT_LABEL,
                      wraplength=180, justify="left")
        hand.pack(anchor="w", padx=6, pady=(2, 4))
        return {"hp": hp, "dfs": dfs, "heroes": heroes, "hand": hand}

    def _build_input_area(self):
        f = self._input_frame
        for w in f.winfo_children():
            w.destroy()

        self._prompt_lbl = _label(f, "Waiting for game loop…",
                                  color=C["dim"], font=FONT_LABEL)
        self._prompt_lbl.pack(anchor="w", padx=6, pady=(4, 0))

        row = tk.Frame(f, bg=f["bg"])
        row.pack(fill="x", padx=6, pady=4)
        self._entry_row = row          # 引用输入框行，便于隐藏/恢复
        self._allow_empty_submit = False
        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(row, textvariable=self._entry_var,
                               bg=C["btn"], fg=C["text"],
                               insertbackground=C["accent"],
                               relief="flat", font=FONT_MONO, bd=4)
        self._entry.pack(side="left", fill="x", expand=True)
        self._entry.bind("<Return>", lambda e: self._submit_entry())
        _btn(row, "OK", self._submit_entry,
             color=C["success"]).pack(side="left", padx=(4, 0))

        # Action list (for opponent multi-choice)
        self._action_list = tk.Frame(f, bg=f["bg"])
        self._action_list.pack(fill="both", expand=True, padx=6, pady=(0, 4))

    # ── PUBLIC API (called from game-loop thread) ──

    def update_snapshot(self, snap: GameSnapshot):
        self._q.put(("snapshot", snap))

    def set_model_action(self, text: str):
        self._q.put(("model_action", text))

    def set_q_value(self, text: str):
        self._q.put(("q_value", text))

    def append_log(self, text: str, tag: str = ""):
        self._q.put(("log", text, tag))

    def ask_input(self, prompt: str, on_done: Callable[[str], None],
                  allow_empty: bool = False):
        """
        Show a one-line prompt.
        allow_empty=True 时空输入直接回车也会提交（返回 ""），默认忽略空提交。
        """
        self._q.put(("ask_input", prompt, on_done, allow_empty))

    def ask_execute_or_response(self, prompt: str,
                                on_done: Callable[[str], None]):
        """
        Replace the entry box with two buttons after a model action.
        on_done receives "execute" (no response) or "response".
        """
        self._q.put(("ask_exec_resp", prompt, on_done))

    def ask_opponent_action(self, legal_actions: List[Any],
                            on_done: Callable[[Any], None]):
        self._q.put(("ask_opponent", legal_actions, on_done))

    def wait_for_continue(self, message: str = "Press OK to continue"):
        """Blocking call — suspends the game thread until user clicks OK."""
        evt = threading.Event()
        self._q.put(("wait_continue", message, evt))
        evt.wait()

    # ── QUEUE PROCESSING (UI thread) ──────────

    def _poll_queue(self):
        try:
            while True:
                item = self._q.get_nowait()
                self._dispatch(item)
        except queue.Empty:
            pass
        self._root.after(50, self._poll_queue)

    def _dispatch(self, item):
        tag_key = item[0]
        if tag_key == "snapshot":
            self._render_snapshot(item[1])
        elif tag_key == "model_action":
            self._sug_lbl.config(text=item[1], fg=C["gold"])
        elif tag_key == "q_value":
            self._qval_lbl.config(text=item[1])
        elif tag_key == "log":
            self._append_log_ui(item[1], item[2] if len(item) > 2 else "")
        elif tag_key == "ask_input":
            self._show_input_prompt(item[1], item[2],
                                    item[3] if len(item) > 3 else False)
        elif tag_key == "ask_exec_resp":
            self._show_execute_or_response(item[1], item[2])
        elif tag_key == "ask_opponent":
            self._show_opponent_chooser(item[1], item[2])
        elif tag_key == "wait_continue":
            self._show_continue(item[1], item[2])
        elif tag_key == "cap_status":
            self._cap_status.config(text=item[1], fg=item[2])
        elif tag_key == "sync_toggle":
            mode = item[1]
            if mode == OpponentSyncMode.AUTO:
                if not self.capture.is_available():
                    self._q.put(("sync_status", "error"))
                    self._sync_panel.add_warning(
                        "PaddleOCR not available — cannot enable sync", "error")
                    return
                self.capture.start(1.0)
                self._sync_panel.set_status("capturing")
            else:
                self.capture.stop()
                self._sync_panel.set_status("idle")
                self._sync_panel.set_mode(OpponentSyncMode.MANUAL)
        elif tag_key == "sync_set_mode":
            self._sync_panel.set_mode(item[1])
        elif tag_key == "sync_status":
            self._sync_panel.set_status(item[1])
        elif tag_key == "sync_entries":
            self._sync_panel.add_entries(item[1])
        elif tag_key == "sync_heartbeat":
            # Update status with current pipeline stats
            stats = self.capture.get_stats()
            metrics = self.capture.get_detection_metrics()
            is_open = metrics.get('is_open')
            if is_open:
                self._sync_panel.set_status("capturing")
            elif stats.get('capture_attempts', 0) > 0:
                self._sync_panel.set_status(
                    f"waiting (dark={metrics.get('dark_ratio', 0):.2f})")
            self._cap_status.config(
                text=f"⊙ attempts={stats.get('capture_attempts',0)} "
                     f"open={stats.get('log_open_count',0)} "
                     f"ocr={stats.get('last_ocr_text_count',0)} "
                     f"parsed={stats.get('last_parsed_count',0)}",
                fg=C["accent"] if is_open else C["dim"])
        elif tag_key == "sync_warning":
            self._sync_panel.add_warning(item[1], item[2] if len(item) > 2 else "warn")

    # ── RENDER ────────────────────────────────

    def _render_snapshot(self, snap: GameSnapshot):
        self._turn_lbl.config(
            text=f"Turn {snap.turn}" if snap.turn else "Turn —")
        self._active_lbl.config(
            text=f"Active: {snap.current_player}",
            fg=C["accent"] if snap.current_player == "Player" else C["accent2"])

        pp = self._player_panel
        pp["hp"].config(text=f"HP:  {snap.player_hp}")
        pp["dfs"].config(text=f"DEF: {snap.player_defense}")
        pp["heroes"].config(text=", ".join(snap.player_heroes) or "—")
        hand_str = "\n".join(f"  {c}" for c in snap.player_hand) or "  (empty)"
        pp["hand"].config(text=f"Hand:\n{hand_str}")

        op = self._opponent_panel
        op["hp"].config(text=f"HP:  {snap.opponent_hp}")
        op["dfs"].config(text=f"DEF: {snap.opponent_defense}")
        op["heroes"].config(text=", ".join(snap.opponent_heroes) or "—")
        op["hand"].config(text=f"Hand count: {snap.opponent_hand_count}")

        if snap.model_suggestion:
            self._sug_lbl.config(text=snap.model_suggestion, fg=C["gold"])

        for line in snap.log_lines:
            self._append_log_ui(line, "sys")

        # ── Sync fields ──
        if snap.sync_status:
            self._sync_panel.set_status(snap.sync_status)
        for w in snap.sync_warnings:
            self._sync_panel.add_warning(w)

    def _append_log_ui(self, text: str, tag: str = ""):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n", tag or "")
        self._log.see("end")
        self._log.config(state="disabled")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ── INPUT WIDGETS ─────────────────────────

    def _show_input_prompt(self, prompt: str, callback: Callable[[str], None],
                           allow_empty: bool = False):
        self._prompt_lbl.config(text=prompt, fg=C["text"])
        self._entry_var.set("")
        self._allow_empty_submit = allow_empty
        # 输入框可能已被 execute/response 按钮替换，恢复到原位（action_list 之前）
        if self._entry_row.winfo_manager() != "pack":
            self._entry_row.pack(fill="x", padx=6, pady=4,
                                 before=self._action_list)
        self._entry.focus()
        # Clear old action buttons and unregister scroll canvas
        self._active_scroll_canvas = None
        for w in self._action_list.winfo_children():
            w.destroy()
        self._current_callback = callback

    def _submit_entry(self):
        val = self._entry_var.get().strip()
        if not val and not self._allow_empty_submit:
            return
        self._allow_empty_submit = False
        self._entry_var.set("")
        self._prompt_lbl.config(text="Waiting…", fg=C["dim"])
        cb = getattr(self, "_current_callback", None)
        if cb:
            self._current_callback = None
            threading.Thread(target=cb, args=(val,), daemon=True).start()

    def _show_opponent_chooser(self, legal_actions: List[Any],
                               callback: Callable[[Any], None]):
        self._prompt_lbl.config(text="Opponent's action:", fg=C["accent2"])
        for w in self._action_list.winfo_children():
            w.destroy()
        self._entry_var.set("")

        frame = self._action_list
        # Scrollable list of buttons
        canvas = tk.Canvas(frame, bg=C["panel"], bd=0,
                           highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=C["panel"])
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)

        # Register this canvas for root-level mousewheel routing so
        # scrolling works even when the cursor is over child buttons.
        self._active_scroll_canvas = canvas

        def _on_inner_configure(e):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_configure(e):
            # Keep inner frame width matched to canvas width
            canvas.itemconfig(inner_id, width=e.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        # Mousewheel scrolling — also bound directly for when cursor is
        # over the canvas itself (belt-and-suspenders with root-level).
        def _on_mousewheel(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _on_mousewheel)
        inner.bind("<MouseWheel>", _on_mousewheel)
        # Bind to scrollbar so drag-scrolling works
        sb.bind("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _cleanup():
            """Unregister the canvas when the chooser is dismissed."""
            if self._active_scroll_canvas is canvas:
                self._active_scroll_canvas = None

        def make_handler(idx, action):
            def _h():
                _cleanup()
                for w in self._action_list.winfo_children():
                    w.destroy()
                self._prompt_lbl.config(text="Waiting…", fg=C["dim"])
                threading.Thread(target=callback, args=(action,),
                                 daemon=True).start()
            return _h

        for i, action in enumerate(legal_actions):
            lbl = str(action)[:60]
            b = tk.Button(inner, text=f"{i+1}. {lbl}",
                          bg=C["btn"], fg=C["text"], anchor="w",
                          relief="flat", bd=0, font=FONT_LABEL,
                          cursor="hand2", pady=2,
                          command=make_handler(i, action))
            b.pack(fill="x", pady=1, padx=2)
            b.bind("<Enter>", lambda e, w=b: w.config(bg=C["btn_hover"]))
            b.bind("<Leave>", lambda e, w=b: w.config(bg=C["btn"]))

        # "Play a card" — passes None → game loop handles card entry
        def _play_card():
            _cleanup()
            for w in self._action_list.winfo_children():
                w.destroy()
            self._prompt_lbl.config(text="Enter card name:", fg=C["warn"])
            self._entry.focus()
            self._current_callback = lambda v: callback(("play_card", v))

        b_card = tk.Button(inner, text="▸ Play a card…",
                           bg=C["btn"], fg=C["warn"], anchor="w",
                           relief="flat", bd=0, font=FONT_LABEL,
                           cursor="hand2", pady=2,
                           command=_play_card)
        b_card.pack(fill="x", pady=1, padx=2)

    def _show_continue(self, message: str, evt: threading.Event):
        self._prompt_lbl.config(text=message, fg=C["gold"])
        self._active_scroll_canvas = None
        for w in self._action_list.winfo_children():
            w.destroy()

        def _ok():
            for w in self._action_list.winfo_children():
                w.destroy()
            self._prompt_lbl.config(text="Waiting…", fg=C["dim"])
            evt.set()

        _btn(self._action_list, "▶  OK — Next Step", _ok,
             color=C["success"]).pack(padx=4, pady=4, anchor="w")

    def _show_execute_or_response(self, prompt: str,
                                  callback: Callable[[str], None]):
        """模型动作给出后：隐藏输入框，用两个按钮选择执行或处理响应。"""
        self._prompt_lbl.config(text=prompt, fg=C["gold"])
        self._active_scroll_canvas = None
        for w in self._action_list.winfo_children():
            w.destroy()
        # 隐藏输入框，用按钮替代
        self._entry_row.pack_forget()
        self._entry_var.set("")

        def _finish(choice: str):
            # 恢复输入框到原位（action_list 之前）
            self._entry_row.pack(fill="x", padx=6, pady=4,
                                 before=self._action_list)
            for w in self._action_list.winfo_children():
                w.destroy()
            self._prompt_lbl.config(text="Waiting…", fg=C["dim"])
            threading.Thread(target=callback, args=(choice,),
                             daemon=True).start()

        _btn(self._action_list, "▶  Execute Action",
             lambda: _finish("execute"), color=C["success"]
             ).pack(fill="x", padx=4, pady=(8, 3), ipady=8)
        _btn(self._action_list, "⚡  Handle Response",
             lambda: _finish("response"), color=C["accent2"]
             ).pack(fill="x", padx=4, pady=3, ipady=8)

    # ── CAPTURE TOGGLE ────────────────────────

    def _toggle_capture(self):
        if self.mode == InputMode.MANUAL:
            if not self.capture.is_available():
                self._q.put(("cap_status",
                             "⚠ PaddleOCR not available — install paddleocr",
                             C["warn"]))
                return
            self.mode = InputMode.CAPTURE
            self._mode_lbl.config(text="[CAPTURE]", fg=C["success"])
            self._cap_btn.config(fg=C["success"])
            self._q.put(("cap_status", "⊙ Capture active", C["success"]))
            self._sync_panel.set_mode(OpponentSyncMode.AUTO)
            self.capture.start(1.0)
        else:
            self.mode = InputMode.MANUAL
            self.capture.stop()
            self._mode_lbl.config(text="[MANUAL]", fg=C["dim"])
            self._cap_btn.config(fg=C["dim"])
            self._q.put(("cap_status",
                         "⊙ Capture inactive — manual mode", C["dim"]))
            self._sync_panel.set_mode(OpponentSyncMode.MANUAL)

    def _on_root_mousewheel(self, event):
        """Route mousewheel events to the active scrollable canvas.

        This ensures scrolling works even when the cursor is over child
        widgets (buttons, labels) that would otherwise consume the event.
        """
        if self._active_scroll_canvas is not None:
            self._active_scroll_canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units")

    def _on_capture(self, snap: GameSnapshot):
        self.update_snapshot(snap)
        self.append_log("[capture] state refreshed", "sys")

    def _on_sync_toggle(self, mode: OpponentSyncMode):
        """Called when the user toggles sync mode via the panel button."""
        self._q.put(("sync_toggle", mode))

    def _on_log_entries(self, entries: list[BattleLogEntry]):
        """Called from CaptureBackend thread when new log entries arrive."""
        if entries:
            self._q.put(("sync_entries", entries))
        else:
            # Periodic heartbeat — update status with pipeline stats
            self._q.put(("sync_heartbeat", None))

    # ── Sync API (called from game-loop thread) ──

    def set_sync_mode(self, mode: OpponentSyncMode):
        """Set the opponent sync mode from the game loop."""
        self._q.put(("sync_set_mode", mode))

    def set_sync_status(self, status: str):
        """Update the sync status indicator."""
        self._q.put(("sync_status", status))

    def add_sync_warning(self, msg: str, severity: str = "warn"):
        """Add a sync warning to the panel."""
        self._q.put(("sync_warning", msg, severity))

    # ── RUN ───────────────────────────────────

    def run(self):
        """Call from main thread to start the Tk event loop."""
        self._root.mainloop()

    def start_background(self):
        """
        Launch Tk in a separate thread so the game loop can stay on main.
        (Use run() instead when possible — Tk prefers the main thread.)
        """
        t = threading.Thread(target=self._root.mainloop, daemon=True)
        t.start()


# ─────────────────────────────────────────────
#  BRIDGE  — connects the existing game loop
# ─────────────────────────────────────────────

class GUIBridge:
    """
    Drop-in replacements for the CLI input/print calls in inference_full_game.py.

    Usage
    -----
    bridge = GUIBridge(gui)

    # instead of: input("Please enter hero …")
    hero = bridge.ask("Please enter hero No.1 of the player: ")

    # instead of: input("Model's action: …\nPress enter …")
    bridge.show_model_action(str(action))
    bridge.wait_continue()

    # instead of: print(…)  / for-loop printing legal actions
    bridge.show_opponent_actions(legal_actions)
    chosen = bridge.get_opponent_choice()
    """

    def __init__(self, gui: InferenceGUI):
        self.gui = gui
        self._result: queue.Queue = queue.Queue()

    # ── synchronous wrappers ──────────────────

    def ask(self, prompt: str) -> str:
        """Block until user submits text."""
        evt = threading.Event()
        result_holder = [None]

        def on_done(val):
            result_holder[0] = val
            evt.set()

        self.gui.ask_input(prompt, on_done)
        evt.wait()
        return result_holder[0]

    def ask_allow_empty(self, prompt: str) -> str:
        """
        Like ask(), but empty input + Enter is accepted and returns "".
        （GameRecorder 包装的是 ask，签名保持不变；空提交走此方法）
        """
        evt = threading.Event()
        result_holder = [None]

        def on_done(val):
            result_holder[0] = val
            evt.set()

        self.gui.ask_input(prompt, on_done, allow_empty=True)
        evt.wait()
        return result_holder[0]

    def ask_execute_or_response(
        self,
        prompt: str = "Execute action, or handle opponent response?",
    ) -> str:
        """
        Block until user picks after a model action.
        Returns "execute" or "response".
        """
        evt = threading.Event()
        result_holder = [None]

        def on_done(choice):
            result_holder[0] = choice
            evt.set()

        self.gui.ask_execute_or_response(prompt, on_done)
        evt.wait()
        return result_holder[0]

    def show_model_action(self, text: str):
        self.gui.set_model_action(text)
        self.gui.append_log(f"[AI] {text}", "ai")

    def show_q_value(self, text: str):
        self.gui.set_q_value(text)

    def wait_continue(self, msg: str = "▶ Press OK to execute model action"):
        self.gui.wait_for_continue(msg)

    def log(self, text: str, tag: str = ""):
        self.gui.append_log(text, tag)

    def update_state(self, snap: GameSnapshot):
        self.gui.update_snapshot(snap)

    def show_opponent_actions(self, legal_actions: List[Any]) -> Any:
        """
        Presents the action list; returns the chosen action
        (or ("play_card", card_name_str) tuple for card plays).
        """
        evt = threading.Event()
        result_holder = [None]

        def on_done(action):
            result_holder[0] = action
            evt.set()

        self.gui.ask_opponent_action(legal_actions, on_done)
        evt.wait()
        return result_holder[0]

    # ── Sync API ───────────────────────────────

    def set_sync_mode(self, mode: OpponentSyncMode):
        """Set opponent sync mode (from game-loop thread)."""
        self.gui.set_sync_mode(mode)

    def on_sync_entries(self, entries: list[BattleLogEntry]):
        """Called when new battle-log entries arrive for processing."""
        self.gui.append_log(f"[sync] {len(entries)} new log entries", "sys")

    def set_sync_status(self, status: str):
        """Update sync status indicator."""
        self.gui.set_sync_status(status)

    def add_sync_warning(self, msg: str, severity: str = "warn"):
        """Add a sync verification warning."""
        self.gui.add_sync_warning(msg, severity)


# ─────────────────────────────────────────────
#  EXAMPLE INTEGRATION SHIM
#  (shows how to wire GUIBridge into the
#   existing inference_full_game.py loop)
# ─────────────────────────────────────────────

def build_snapshot_from_game(game, player1, player2) -> GameSnapshot:
    """
    Convert live game objects into a GameSnapshot for the GUI.
    Expand as more state becomes relevant.
    """
    try:
        # 手牌排序：按己方式神顺序 → 等级需求 → 到手顺序
        hero_order = {h.type_name: i for i, h in enumerate(player1.heroes)}
        p1_hand = [str(c) for c in sorted(
            player1.hand.cards,
            key=lambda c: (hero_order.get(c.hero, len(hero_order)), c.level_req)
        )]
    except Exception:
        p1_hand = []
    try:
        p1_heroes = [h.eng_name if hasattr(h, "eng_name") else str(h)
                     for h in player1.heroes]
    except Exception:
        p1_heroes = []
    try:
        p2_heroes = [h.eng_name if hasattr(h, "eng_name") else str(h)
                     for h in player2.heroes]
    except Exception:
        p2_heroes = []

    return GameSnapshot(
        turn=getattr(game, "turn_count", 0),
        current_player="Player" if game.current_player is player1 else "Opponent",
        player_hp=getattr(player1, "hp", 0),
        player_defense=getattr(player1, "defense", 0),
        player_hand=p1_hand,
        player_heroes=p1_heroes,
        opponent_hp=getattr(player2, "hp", 0),
        opponent_defense=getattr(player2, "defense", 0),
        opponent_hand_count=len(getattr(player2.hand, "cards", [])),
        opponent_heroes=p2_heroes,
        sync_mode=OpponentSyncMode.MANUAL,
        sync_status="",
    )


# ─────────────────────────────────────────────
#  STANDALONE PREVIEW  (run this file directly)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import random

    gui = InferenceGUI()

    def _demo():
        time.sleep(0.4)
        # Simulate a game snapshot
        snap = GameSnapshot(
            turn=3,
            current_player="Player",
            player_hp=20,
            player_defense=2,
            player_hand=["WuShiZhiQuan", "XinZhan", "FengShi"],
            player_heroes=["ZhiRenWuShi", "QuanShen"],
            opponent_hp=15,
            opponent_defense=5,
            opponent_hand_count=4,
            opponent_heroes=["TianXieGuiTuanHuo", "TaoHuaYao"],
            model_suggestion="Attack → hero[0]",
        )
        gui.update_snapshot(snap)
        gui.append_log("Game started — demo mode", "sys")
        gui.append_log("[AI] Recommended: Attack hero[0]", "ai")

        # Simulate model action pause
        gui.set_model_action("Attack → hero[0]  (q=0.87)")
        gui.wait_for_continue("▶ Model action ready — press OK to execute")
        gui.append_log("Action executed.", "good")

        # Simulate opponent turn
        from collections import namedtuple
        FakeAction = namedtuple("FakeAction", ["type", "__str__"])
        legal = [
            type("A", (), {"__str__": lambda s: "End Turn"})(),
            type("A", (), {"__str__": lambda s: "Attack player"})(),
            type("A", (), {"__str__": lambda s: "Use skill"})(),
        ]
        result = gui._create_bridge().show_opponent_actions(legal)  # type: ignore
        gui.append_log(f"Opponent chose: {result}", "opp")

    class _DemoBridge:
        def __init__(self, g): self.gui = g
        def show_opponent_actions(self, actions):
            evt = threading.Event()
            holder = [None]
            def done(a): holder[0]=a; evt.set()
            g.ask_opponent_action(actions, done)
            evt.wait()
            return holder[0]

    gui._create_bridge = lambda: _DemoBridge(gui)   # type: ignore

    threading.Thread(target=_demo, daemon=True).start()
    gui.run()