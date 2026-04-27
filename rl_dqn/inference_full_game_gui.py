"""
inference_gui.py
----------------
Compact overlay GUI for the DQN inference loop.
Replaces inference_full_game.py's CLI interactions with a small,
always-on-top Tkinter window that sits over the actual game screen.

Screen-capture hooks are stubbed out in `CaptureBackend` — swap in
a real implementation (e.g., mss + PaddleOCR) when ready.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import queue
import time
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
from enum import Enum, auto


# ─────────────────────────────────────────────
#  DATA STRUCTURES
# ─────────────────────────────────────────────

class InputMode(Enum):
    MANUAL   = auto()   # human types everything
    CAPTURE  = auto()   # screen-capture backend feeds data


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


# ─────────────────────────────────────────────
#  CAPTURE BACKEND  (stub — replace later)
# ─────────────────────────────────────────────

class CaptureBackend:
    """
    Abstract interface for reading game state from the screen.

    To implement real capture:
      1. Install `mss` for screenshots, `paddleocr` or `easyocr` for text.
      2. Override `capture_snapshot()` with actual logic.
      3. Pass `mode=InputMode.CAPTURE` to InferenceGUI.
    """

    def is_available(self) -> bool:
        """Return True when the capture library is loaded and ready."""
        return False

    def capture_snapshot(self) -> Optional[GameSnapshot]:
        """
        Take a screenshot, run OCR, parse fields, return a GameSnapshot.
        Return None if capture fails.
        """
        # ── STUB ──────────────────────────────────────────────────────────
        # import mss, numpy as np
        # from paddleocr import PaddleOCR
        # ocr = PaddleOCR(use_angle_cls=True, lang='ch')
        # with mss.mss() as sct:
        #     raw = np.array(sct.grab(sct.monitors[1]))
        # result = ocr.ocr(raw, cls=True)
        # ... parse result into GameSnapshot fields ...
        # return snapshot
        # ──────────────────────────────────────────────────────────────────
        return None

    def capture_loop(self, interval: float, callback: Callable[[GameSnapshot], None]):
        """Poll at `interval` seconds; call `callback` with each snapshot."""
        while self._running:
            snap = self.capture_snapshot()
            if snap:
                callback(snap)
            time.sleep(interval)

    def start(self, interval: float, callback: Callable[[GameSnapshot], None]):
        self._running = True
        t = threading.Thread(target=self.capture_loop,
                             args=(interval, callback), daemon=True)
        t.start()

    def stop(self):
        self._running = False


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
#  MAIN GUI
# ─────────────────────────────────────────────

class InferenceGUI:
    """
    Compact overlay window (~420 × 680 px).

    Public interface used by the game loop
    ───────────────────────────────────────
    gui.update_snapshot(snap: GameSnapshot)   – refresh all panels
    gui.set_model_action(text: str)           – display AI suggestion
    gui.append_log(text: str)                 – add a line to the log
    gui.ask_opponent_action(legal, on_done)   – open opponent input sheet
    gui.ask_input(prompt, on_done)            – simple one-line prompt
    gui.wait_for_continue()                   – blocking pause (confirm step)
    """

    WIDTH  = 420
    HEIGHT = 680

    def __init__(self, mode: InputMode = InputMode.MANUAL,
                 capture_backend: Optional[CaptureBackend] = None):
        self.mode    = mode
        self.capture = capture_backend or CaptureBackend()
        self._q: queue.Queue = queue.Queue()        # thread→UI events
        self._response: queue.Queue = queue.Queue() # UI→thread answers

        self._build_window()
        self._build_ui()

        if mode == InputMode.CAPTURE and self.capture.is_available():
            self.capture.start(0.5, self._on_capture)

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
        self._sug_lbl = _label(sug, "—", color=C["text"], font=FONT_MONO,
                               wraplength=280, justify="left")
        self._sug_lbl.pack(side="left", padx=4, fill="x", expand=True)

        # ── Capture status (hidden until active) ─
        self._cap_frame = _panel(root)
        self._cap_frame.pack(fill="x", padx=6, pady=(0, 2))
        self._cap_status = _label(self._cap_frame,
                                  "⊙ Capture inactive — manual mode",
                                  color=C["dim"], font=FONT_LABEL)
        self._cap_status.pack(side="left", padx=6, pady=2)

        # ── Action input area ──────────────────
        self._input_frame = _panel(root)
        self._input_frame.pack(fill="x", padx=6, pady=(0, 4))
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
        self._action_list.pack(fill="x", padx=6, pady=(0, 4))

    # ── PUBLIC API (called from game-loop thread) ──

    def update_snapshot(self, snap: GameSnapshot):
        self._q.put(("snapshot", snap))

    def set_model_action(self, text: str):
        self._q.put(("model_action", text))

    def append_log(self, text: str, tag: str = ""):
        self._q.put(("log", text, tag))

    def ask_input(self, prompt: str, on_done: Callable[[str], None]):
        self._q.put(("ask_input", prompt, on_done))

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
        elif tag_key == "log":
            self._append_log_ui(item[1], item[2] if len(item) > 2 else "")
        elif tag_key == "ask_input":
            self._show_input_prompt(item[1], item[2])
        elif tag_key == "ask_opponent":
            self._show_opponent_chooser(item[1], item[2])
        elif tag_key == "wait_continue":
            self._show_continue(item[1], item[2])
        elif tag_key == "cap_status":
            self._cap_status.config(text=item[1], fg=item[2])

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

    def _show_input_prompt(self, prompt: str, callback: Callable[[str], None]):
        self._prompt_lbl.config(text=prompt, fg=C["text"])
        self._entry_var.set("")
        self._entry.focus()
        # Clear old action buttons
        for w in self._action_list.winfo_children():
            w.destroy()
        self._current_callback = callback

    def _submit_entry(self):
        val = self._entry_var.get().strip()
        if not val:
            return
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
                           highlightthickness=0, height=80)
        sb = ttk.Scrollbar(frame, orient="vertical",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=C["panel"])
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def make_handler(idx, action):
            def _h():
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
        for w in self._action_list.winfo_children():
            w.destroy()

        def _ok():
            for w in self._action_list.winfo_children():
                w.destroy()
            self._prompt_lbl.config(text="Waiting…", fg=C["dim"])
            evt.set()

        _btn(self._action_list, "▶  OK — Next Step", _ok,
             color=C["success"]).pack(padx=4, pady=4, anchor="w")

    # ── CAPTURE TOGGLE ────────────────────────

    def _toggle_capture(self):
        if self.mode == InputMode.MANUAL:
            if not self.capture.is_available():
                self._q.put(("cap_status",
                             "⚠ Capture backend not available",
                             C["warn"]))
                return
            self.mode = InputMode.CAPTURE
            self._mode_lbl.config(text="[CAPTURE]", fg=C["success"])
            self._cap_btn.config(fg=C["success"])
            self._q.put(("cap_status", "⊙ Capture active", C["success"]))
            self.capture.start(0.5, self._on_capture)
        else:
            self.mode = InputMode.MANUAL
            self.capture.stop()
            self._mode_lbl.config(text="[MANUAL]", fg=C["dim"])
            self._cap_btn.config(fg=C["dim"])
            self._q.put(("cap_status",
                         "⊙ Capture inactive — manual mode", C["dim"]))

    def _on_capture(self, snap: GameSnapshot):
        self.update_snapshot(snap)
        self.append_log("[capture] state refreshed", "sys")

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

    def show_model_action(self, text: str):
        self.gui.set_model_action(text)
        self.gui.append_log(f"[AI] {text}", "ai")

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
        p1_hand = [str(c) for c in player1.hand.cards]
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