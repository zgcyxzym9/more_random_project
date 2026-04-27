"""
hero_recognizer.py
==================
Automatic hero identification from the game's opening hero-display scene,
running against a Windows 11 wireless-projection (投屏) window.

Quick start
-----------
  # 1. Calibrate on a screenshot:
  python hero_recognizer.py screenshot.png ./assets [out.png]

  # 2. Live debug against the projection window:
  python hero_recognizer.py --live [window_hint] [assets_dir] [out_dir]

  # 3. In code:
  rec = HeroRecognizer("./assets", window_title_hint="投屏")
  rec.start(callback=lambda r: print(r.player_heroes, r.opponent_heroes))
  ...
  rec.stop()

Architecture
------------
  WindowGrabber   – captures the projection window via BitBlt (pywin32),
                    falls back to mss full-screen when pywin32 is absent.
  SceneDetector   – decides whether the hero-reveal overlay is on screen by
                    probing the PLAYER'S own card-back stack in the lower-right
                    corner (robust to opponent deck-skin changes).
  CardLocator     – finds the 8 hero card bounding boxes dynamically using a
                    variance-based sliding-window scan; no stored coordinates,
                    works on any background colour.
  TemplateLibrary – matches each crop to a hero face template via normalised
                    cross-correlation (TM_CCOEFF_NORMED).
  HeroRecognizer  – orchestrates the above in a background thread; fires a
                    callback(HeroResult) once per detected scene.

Scene detection
---------------
Primary signal: the player's own card-back stack appears in the lower-right
  quadrant of the frame (approx x 72-97 %, y 45-87 % of frame size).
  We look for dark-teal / navy pixels there (H 100-155, S 30-150, V 45-130).
  Only the PLAYER's deck is used; the opponent's upper-right stack is ignored
  because opponents can use any deck skin.

Secondary signal: the bright central background (sunburst / glowing orb) that
  appears during the hero-reveal has a high mean V-channel in the centre of
  the frame.  Both signals must be true simultaneously.

Card location (variance scan)
-----------------------------
This approach is entirely background-agnostic:
  1. Convert to greyscale.
  2. For each row band (upper = opponent, lower = player):
     a. Slide a CARD_W-wide window across the game-content x-range,
        compute variance of every column.  Card-art columns have much higher
        variance than blank background.
     b. Find the 4 highest-scoring non-overlapping peaks → card x-centres.
     c. For each x-centre, slide a CARD_H-tall window vertically within the
        row band; the position with maximum variance is the card y-top.
  3. Returns two lists of 4 bounding boxes.
"""

from __future__ import annotations

import os
import sys
import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

sys.path.insert(0, "E:/more_random_project")

import cv2
import numpy as np
from scipy.signal import find_peaks
from rl_dqn.game_frame_capture import (
    DEFAULT_TODESK_TITLE,
    ToDeskGameFrameGrabber,
    WindowGrabber,
    crop_game_frame_from_window,
)

logger = logging.getLogger(__name__)

# ── Optional platform dependencies ───────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
#  DATA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HeroResult:
    player_heroes:   List[str]    # eng_names, index 0 = leftmost hero
    opponent_heroes: List[str]    # index 0 = leftmost hero
    confidence:      List[float]  # 8 values: opp[0..3] then player[0..3]
    screenshot:      Optional[np.ndarray] = None

    def all_confident(self, threshold: float = 0.45) -> bool:
        return all(c >= threshold for c in self.confidence)

    def low_confidence_slots(self, threshold: float = 0.45) -> List[str]:
        slots = ([f"opp{i+1}" for i in range(4)] +
                 [f"me{i+1}"  for i in range(4)])
        return [s for s, c in zip(slots, self.confidence) if c < threshold]
class SceneDetector:
    """
    Detects whether the hero-reveal overlay is currently visible.

    Two signals, BOTH must be true:

    Signal 1 – card-back colour probe (lower-right, player's deck stack)
        The player's card backs are dark teal/navy (H 100-155, S 30-150, V 45-130).
        We probe the lower-right region of the frame where the player's deck
        stack appears during the hero reveal.  The opponent's upper-right stack
        is intentionally ignored because opponents may use different skins.

        probe_rel = (rel_x, rel_y, rel_w, rel_h) covering lower-right ~25×42 %

    Signal 2 – bright central background
        The hero-reveal background has a bright sunburst / glowing orb in the
        centre.  We check the mean V-channel in a central region.

    Parameters
    ----------
    probe_rel          : region to sample for card-back colour
    card_back_hsv_lo/hi: HSV bounds for the card-back colour
    card_back_ratio    : minimum fraction of probe pixels matching the colour
    centre_rel         : region to check for bright background
    centre_min_v       : minimum mean V for the bright-background check
    """

    def __init__(
        self,
        probe_rel:         Tuple[float,float,float,float] = (0.72, 0.45, 0.25, 0.42),
        card_back_hsv_lo:  Tuple[int,int,int]             = (100, 30,  45),
        card_back_hsv_hi:  Tuple[int,int,int]             = (155, 150, 130),
        card_back_ratio:   float                          = 0.04,
        centre_rel:        Tuple[float,float,float,float] = (0.35, 0.25, 0.30, 0.50),
        centre_min_v:      int                            = 130,
        fixed_avatar_min_white: float                      = 0.12,
        fixed_avatar_min_var:   float                      = 1200.0,
        health_min_white:       float                      = 0.12,
        health_min_red:         float                      = 0.07,
        health_min_edge:        float                      = 0.07,
    ):
        self.probe_rel       = probe_rel
        self.lo              = np.array(card_back_hsv_lo,  np.uint8)
        self.hi              = np.array(card_back_hsv_hi,  np.uint8)
        self.card_back_ratio = card_back_ratio
        self.centre_rel      = centre_rel
        self.centre_min_v    = centre_min_v
        self.fixed_avatar_min_white = fixed_avatar_min_white
        self.fixed_avatar_min_var   = fixed_avatar_min_var
        self.health_min_white       = health_min_white
        self.health_min_red         = health_min_red
        self.health_min_edge        = health_min_edge

    def is_hero_scene(self, frame: np.ndarray) -> bool:
        return self.is_fixed_board_scene(frame)

    def is_fixed_board_scene(self, frame: np.ndarray) -> bool:
        """Detect the stable opening board scene by the two left player badges."""
        H, W = frame.shape[:2]
        regions = [
            (0.00, 0.00, 0.14, 0.20),  # opponent badge + health 30
            (0.00, 0.72, 0.14, 0.28),  # player badge + health 30
        ]
        for rx, ry, rw, rh in regions:
            x0, y0 = int(rx * W), int(ry * H)
            x1, y1 = min(W, int((rx + rw) * W)), min(H, int((ry + rh) * H))
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0:
                return False
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            white_ratio = float(((hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 160)).mean())
            grey_var = float(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).var())
            if white_ratio < self.fixed_avatar_min_white or grey_var < self.fixed_avatar_min_var:
                return False
        return self.has_fixed_health_numbers(frame)

    def _health_30_score(self, frame: np.ndarray, rel_box: Tuple[float,float,float,float]) -> dict:
        H, W = frame.shape[:2]
        rx, ry, rw, rh = rel_box
        x0, y0 = int(rx * W), int(ry * H)
        x1, y1 = min(W, int((rx + rw) * W)), min(H, int((ry + rh) * H))
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return {"white": 0.0, "red": 0.0, "edge": 0.0, "ok": False}

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        white = float(((hsv[:, :, 1] < 80) & (hsv[:, :, 2] > 170)).mean())
        red = float(((((hsv[:, :, 0] < 15) | (hsv[:, :, 0] > 165)) &
                      (hsv[:, :, 1] > 50) & (hsv[:, :, 2] > 50))).mean())
        grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        edge = float(cv2.Canny(grey, 50, 150).mean() / 255.0)
        return {
            "white": white,
            "red": red,
            "edge": edge,
            "ok": (white >= self.health_min_white and
                   red >= self.health_min_red and
                   edge >= self.health_min_edge),
        }

    def fixed_health_info(self, frame: np.ndarray) -> dict:
        top = self._health_30_score(frame, (0.045, 0.055, 0.065, 0.13))
        bottom = self._health_30_score(frame, (0.045, 0.855, 0.065, 0.13))
        return {"top": top, "bottom": bottom, "ok": top["ok"] and bottom["ok"]}

    def has_fixed_health_numbers(self, frame: np.ndarray) -> bool:
        return bool(self.fixed_health_info(frame)["ok"])

    def is_reveal_scene(self, frame: np.ndarray) -> bool:
        H, W = frame.shape[:2]

        # Signal 1: card-back colour in lower-right
        rx, ry, rw, rh = self.probe_rel
        x0, y0 = int(rx*W), int(ry*H)
        x1, y1 = min(W, int((rx+rw)*W)), min(H, int((ry+rh)*H))
        probe = frame[y0:y1, x0:x1]
        if probe.size == 0:
            return False
        hsv    = cv2.cvtColor(probe, cv2.COLOR_BGR2HSV)
        ratio  = cv2.inRange(hsv, self.lo, self.hi).mean() / 255.0
        if ratio < self.card_back_ratio:
            return False

        # Signal 2: bright central background
        cx, cy, cw, ch = self.centre_rel
        px0, py0 = int(cx*W), int(cy*H)
        px1, py1 = int((cx+cw)*W), int((cy+ch)*H)
        centre = frame[py0:py1, px0:px1]
        if centre.size == 0:
            return False
        mean_v = float(cv2.cvtColor(centre, cv2.COLOR_BGR2HSV)[:,:,2].mean())
        return mean_v >= self.centre_min_v

    def probe_info(self, frame: np.ndarray) -> dict:
        """Return diagnostic values for debugging / threshold tuning."""
        H, W = frame.shape[:2]
        rx,ry,rw,rh = self.probe_rel
        probe = frame[int(ry*H):min(H,int((ry+rh)*H)),
                      int(rx*W):min(W,int((rx+rw)*W))]
        cx,cy,cw,ch = self.centre_rel
        centre = frame[int(cy*H):int((cy+ch)*H), int(cx*W):int((cx+cw)*W)]
        ratio = 0.0; mean_v = 0.0
        if probe.size:
            hsv = cv2.cvtColor(probe, cv2.COLOR_BGR2HSV)
            ratio = float(cv2.inRange(hsv, self.lo, self.hi).mean() / 255.0)
        if centre.size:
            mean_v = float(cv2.cvtColor(centre, cv2.COLOR_BGR2HSV)[:,:,2].mean())
        health = self.fixed_health_info(frame)
        fixed_scene = self.is_fixed_board_scene(frame)
        reveal_scene = ratio >= self.card_back_ratio and mean_v >= self.centre_min_v
        return {"card_back_ratio": ratio, "centre_mean_v": mean_v,
                "health_top": health["top"], "health_bottom": health["bottom"],
                "health_ok": health["ok"],
                "fixed_scene": fixed_scene, "reveal_scene": reveal_scene,
                "scene": fixed_scene}


# ─────────────────────────────────────────────────────────────────────────────
#  CARD LOCATOR  (variance scan — background-agnostic)
# ─────────────────────────────────────────────────────────────────────────────

class CardLocator:
    """
    Locates the 8 hero card bounding boxes in a hero-scene frame without any
    stored coordinates, using a variance-based sliding-window scan.

    How it works
    ------------
    Cards contain complex artwork that has high greyscale variance.  The game
    background (solid colour, gradients, or blurry art) has much lower variance.

    For each of the two horizontal row bands:
      1. Slide a CARD_W-wide window across the game-content x-range.
         Compute variance of the full-height strip at each x position.
         → 4 peaks = 4 card columns.
      2. For each column, slide a CARD_H-tall window vertically within the
         row band.  The y position with maximum variance = card y-top.

    Parameters
    ----------
    game_x_frac   : (left, right) fraction of frame width — game area only,
                    excludes player avatars (left) and deck stacks (right).
    upper_y_frac  : (top, bottom) fraction of frame height for opponent row.
    lower_y_frac  : (top, bottom) fraction of frame height for player row.
    card_w_frac   : card width as fraction of frame width.
    card_h_frac   : card height as fraction of frame height.
    peak_min_frac : peaks below this fraction of the row maximum are ignored.
    """

    def __init__(
        self,
        game_x_frac:   Tuple[float, float] = (0.22, 0.77),
        upper_y_frac:  Tuple[float, float] = (0.00, 0.46),
        lower_y_frac:  Tuple[float, float] = (0.36, 1.00),
        card_w_frac:   float               = 0.072,
        card_h_frac:   float               = 0.26,
        peak_min_frac: float               = 0.15,
    ):
        self.game_x_frac   = game_x_frac
        self.upper_y_frac  = upper_y_frac
        self.lower_y_frac  = lower_y_frac
        self.card_w_frac   = card_w_frac
        self.card_h_frac   = card_h_frac
        self.peak_min_frac = peak_min_frac

    def locate(self, frame: np.ndarray
               ) -> Tuple[List[Tuple[int,int,int,int]],
                          List[Tuple[int,int,int,int]]]:
        """
        Returns (opponent_boxes, player_boxes).
        Each is a list of 4 (x0, y0, x1, y1) pixel boxes, sorted left→right.
        Returns ([], []) if fewer than 4 total boxes are found.
        """
        H, W  = frame.shape[:2]
        grey  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)

        cw = max(40, int(W * self.card_w_frac))
        ch = max(60, int(H * self.card_h_frac))
        gx0 = int(self.game_x_frac[0] * W)
        gx1 = int(self.game_x_frac[1] * W)

        rows = [
            ("upper", int(self.upper_y_frac[0]*H), int(self.upper_y_frac[1]*H)),
            ("lower", int(self.lower_y_frac[0]*H), int(self.lower_y_frac[1]*H)),
        ]

        result: dict[str, List[Tuple[int,int,int,int]]] = {}
        for row_name, ry0, ry1 in rows:
            strip  = grey[ry0:ry1, gx0:gx1]
            rH, rW = strip.shape

            # Column variance profile
            col_var = np.array([
                strip[:, x : x+cw].var()
                for x in range(max(1, rW - cw))
            ], dtype=np.float32)

            if col_var.max() < 50:          # no cards in this band
                result[row_name] = []
                continue

            peaks, _ = find_peaks(
                col_var,
                distance=cw,
                height=col_var.max() * self.peak_min_frac,
            )
            if len(peaks) == 0:
                result[row_name] = []
                continue

            # Take top-4 by variance value, then re-sort by x
            scored = sorted(zip(peaks.tolist(), col_var[peaks].tolist()),
                            key=lambda p: -p[1])
            top4   = sorted(int(p) for p, _ in scored[:4])

            boxes = []
            for xp in top4:
                ax0 = gx0 + xp
                ax1 = ax0 + cw
                # Vertical scan for best y within this column
                col_pix = grey[ry0:ry1, ax0:ax1]
                col_rH  = col_pix.shape[0]
                if col_rH <= ch:
                    best_y = 0
                else:
                    row_var = np.array([col_pix[y:y+ch].var()
                                        for y in range(col_rH - ch)],
                                       dtype=np.float32)
                    best_y  = int(row_var.argmax())
                ay0 = ry0 + best_y
                ay1 = ay0 + ch
                boxes.append((ax0, ay0, ax1, ay1))

            result[row_name] = boxes

        opp = result.get("upper", [])
        me  = result.get("lower", [])

        if len(opp) < 4 or len(me) < 4:
            logger.debug("CardLocator: incomplete  opp=%d  me=%d", len(opp), len(me))
            return [], []

        return opp, me


# ─────────────────────────────────────────────────────────────────────────────
#  TEMPLATE LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

class FixedBoardLocator:
    """
    Returns the eight stable hero-card slots in the post-deal board scene.

    The boxes are relative coordinates measured from the supplied 2700x1224
    samples, with padding for minor capture scaling and UI shimmer.
    """

    OPP_BOXES = [
        (0.254, 0.130, 0.334, 0.382),
        (0.361, 0.048, 0.441, 0.306),
        (0.561, 0.045, 0.644, 0.307),
        (0.667, 0.130, 0.748, 0.382),
    ]
    ME_BOXES = [
        (0.253, 0.520, 0.334, 0.777),
        (0.361, 0.616, 0.442, 0.875),
        (0.565, 0.616, 0.646, 0.875),
        (0.667, 0.520, 0.748, 0.777),
    ]

    def locate(self, frame: np.ndarray
               ) -> Tuple[List[Tuple[int,int,int,int]],
                          List[Tuple[int,int,int,int]]]:
        H, W = frame.shape[:2]

        def _scale(boxes):
            out = []
            for x0, y0, x1, y1 in boxes:
                out.append((
                    max(0, int(x0 * W)),
                    max(0, int(y0 * H)),
                    min(W, int(x1 * W)),
                    min(H, int(y1 * H)),
                ))
            return out

        return _scale(self.OPP_BOXES), _scale(self.ME_BOXES)


class TemplateLibrary:
    """
    Loads hero face templates from assets_dir (filename stem = eng_name).
    Matches crops via normalised cross-correlation.
    """

    def __init__(self, assets_dir: str, template_size: Tuple[int,int] = (100,140)):
        self.size      = template_size
        self.feature_size = (260, 370)
        self.templates: dict[str, np.ndarray] = {}
        self.features: dict[str, Tuple[List[cv2.KeyPoint], Optional[np.ndarray]]] = {}
        self._sift = cv2.SIFT_create(nfeatures=1200) if hasattr(cv2, "SIFT_create") else None
        self._matcher = cv2.BFMatcher(cv2.NORM_L2) if self._sift is not None else None
        self._load(assets_dir)

    def _load(self, assets_dir: str):
        if not os.path.isdir(assets_dir):
            logger.warning("TemplateLibrary: dir not found: %s", assets_dir)
            return
        for fname in os.listdir(assets_dir):
            stem, ext = os.path.splitext(fname)
            if ext.lower() not in {".png",".jpg",".jpeg",".webp"}:
                continue
            img = cv2.imread(os.path.join(assets_dir, fname), cv2.IMREAD_GRAYSCALE)
            if img is None: continue
            self.templates[stem] = cv2.resize(img, self.size,
                                              interpolation=cv2.INTER_AREA)
            if self._sift is not None:
                feat_img = cv2.resize(img, self.feature_size,
                                      interpolation=cv2.INTER_AREA)
                self.features[stem] = self._sift.detectAndCompute(feat_img, None)
        logger.info("TemplateLibrary: %d templates loaded", len(self.templates))

    def reload(self, assets_dir: str):
        self.templates.clear()
        self.features.clear()
        self._load(assets_dir)

    def best_match(self, crop: np.ndarray) -> Tuple[str, float]:
        """Return (eng_name, NCC_score ∈ [-1,1])."""
        if not self.templates:
            return ("unknown", 0.0)
        grey    = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
        if self._sift is not None and self._matcher is not None and self.features:
            feat_crop = cv2.resize(grey, self.feature_size,
                                   interpolation=cv2.INTER_AREA)
            _kp, des = self._sift.detectAndCompute(feat_crop, None)
            if des is not None:
                best_n, best_s = "unknown", 0.0
                for name, (_tmpl_kp, tmpl_des) in self.features.items():
                    if tmpl_des is None:
                        continue
                    matches = self._matcher.knnMatch(tmpl_des, des, k=2)
                    good = [m for m, n in matches if m.distance < 0.75 * n.distance]
                    score = min(1.0, len(good) / 80.0)
                    if score > best_s:
                        best_s, best_n = score, name
                return (best_n, best_s)

        resized = cv2.resize(grey, self.size, interpolation=cv2.INTER_AREA)
        best_n, best_s = "unknown", -1.0
        for name, tmpl in self.templates.items():
            s = float(cv2.matchTemplate(resized, tmpl, cv2.TM_CCOEFF_NORMED).max())
            if s > best_s:
                best_s, best_n = s, name
        return (best_n, best_s)


# ─────────────────────────────────────────────────────────────────────────────
#  HERO RECOGNISER
# ─────────────────────────────────────────────────────────────────────────────

class HeroRecognizer:
    """
    Background-thread recogniser.  Grabs the projection window, waits for the
    hero-reveal scene, finds all 8 cards, matches them, fires the callback.

    Parameters
    ----------
    assets_dir        : folder containing hero PNG templates
    window_title_hint : partial title of the projection window (default "投屏")
    template_size     : (w, h) used for both templates and crop resizing
    match_threshold   : NCC score below which a match is flagged as uncertain
    confirm_frames    : consecutive positive scene-detections before callback
    poll_idle         : seconds between grabs when not in scene
    poll_active       : seconds between grabs once in scene
    scene_detector    : custom SceneDetector or None
    card_locator      : custom CardLocator or None
    grabber           : custom WindowGrabber or None
    """

    def __init__(
        self,
        assets_dir:        str,
        window_title_hint: str                     = DEFAULT_TODESK_TITLE,
        template_size:     Tuple[int,int]          = (100, 140),
        match_threshold:   float                   = 0.45,
        confirm_frames:    int                     = 2,
        poll_idle:         float                   = 0.10,
        poll_active:       float                   = 0.03,
        scene_detector:    Optional[SceneDetector] = None,
        card_locator:      Optional[object]        = None,
        grabber:           Optional[WindowGrabber] = None,
    ):
        self.match_threshold = match_threshold
        self.confirm_frames  = confirm_frames
        self.poll_idle       = poll_idle
        self.poll_active     = poll_active
        self.library         = TemplateLibrary(assets_dir, template_size)
        self.detector        = scene_detector or SceneDetector()
        self.locator         = card_locator   or FixedBoardLocator()
        self.grabber         = grabber        or ToDeskGameFrameGrabber(window_title_hint)
        self._callback: Optional[Callable[[HeroResult], None]] = None
        self._thread:   Optional[threading.Thread] = None
        self._running = False
        self._confirm = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, callback: Callable[[HeroResult], None]):
        """Start the background detection thread."""
        self._callback = callback
        if self._running:
            return
        self.grabber.find_window()
        self._running = True
        self._thread  = threading.Thread(target=self._loop,
                                         name="HeroRecognizer", daemon=True)
        self._thread.start()
        logger.info("HeroRecognizer started.")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        self.grabber.close()
        logger.info("HeroRecognizer stopped.")

    def reload_assets(self, assets_dir: str):
        self.library.reload(assets_dir)

    def recognise_frame(self, frame: np.ndarray) -> Optional[HeroResult]:
        """One-shot recogniser on a pre-captured frame (for testing)."""
        if not self.detector.is_hero_scene(frame):
            return None
        return self._match(frame)

    # ── Background loop ───────────────────────────────────────────────────────

    def _loop(self):
        in_scene = False
        while self._running:
            try:
                frame = self.grabber.grab()
            except Exception as e:
                logger.error("Grab error: %s", e)
                time.sleep(1.0)
                continue

            if self.detector.is_hero_scene(frame):
                self._confirm += 1
                if not in_scene and self._confirm >= self.confirm_frames:
                    in_scene = True
                    result   = self._match(frame)
                    low = result.low_confidence_slots(self.match_threshold)
                    if low:
                        logger.warning("Low-confidence slots: %s", low)
                    logger.info("player=%s  opp=%s",
                                result.player_heroes, result.opponent_heroes)
                    if self._callback:
                        try:
                            self._callback(result)
                        except Exception as e:
                            logger.error("Callback error: %s", e)
                time.sleep(self.poll_active)
            else:
                self._confirm = 0
                in_scene      = False
                time.sleep(self.poll_idle)

    def _match(self, frame: np.ndarray) -> HeroResult:
        opp_boxes, me_boxes = self.locator.locate(frame)
        H, W = frame.shape[:2]
        opp_names, me_names, confs = [], [], []
        for box_list, name_list in [(opp_boxes, opp_names), (me_boxes, me_names)]:
            for x0, y0, x1, y1 in box_list:
                crop = frame[max(0,y0):min(H,y1), max(0,x0):min(W,x1)]
                if crop.size == 0:
                    name_list.append("unknown"); confs.append(0.0)
                else:
                    n, s = self.library.best_match(crop)
                    name_list.append(n); confs.append(s)
        return HeroResult(player_heroes=me_names, opponent_heroes=opp_names,
                          confidence=confs, screenshot=frame.copy())


# ─────────────────────────────────────────────────────────────────────────────
#  DEBUG / CALIBRATION TOOLS
# ─────────────────────────────────────────────────────────────────────────────

def draw_debug(frame:     np.ndarray,
               opp_boxes: List[Tuple[int,int,int,int]],
               me_boxes:  List[Tuple[int,int,int,int]],
               opp_names: List[str],
               me_names:  List[str],
               confs:     List[float],
               detector:  Optional[SceneDetector] = None,
               locator:   Optional[CardLocator]   = None,
               out_path:  str = "debug_heroes.png") -> str:
    """
    Save an annotated frame showing:
      • Card bounding boxes + matched name + confidence
      • SceneDetector probe region  (blue rectangle)
      • CardLocator game-content boundary  (cyan vertical lines)
    """
    vis = frame.copy()
    H, W = vis.shape[:2]

    def _rect(x0, y0, x1, y1, color, label):
        cv2.rectangle(vis, (x0,y0), (x1,y1), color, 2)
        cv2.putText(vis, label, (x0, max(y0-4,12)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.40, color, 1, cv2.LINE_AA)

    for i, ((x0,y0,x1,y1), name) in enumerate(zip(opp_boxes, opp_names)):
        c = confs[i] if i < len(confs) else 0.0
        _rect(x0,y0,x1,y1, (0,200,255), f"opp{i+1}:{name}({c:.2f})")
    for i, ((x0,y0,x1,y1), name) in enumerate(zip(me_boxes, me_names)):
        c = confs[4+i] if 4+i < len(confs) else 0.0
        _rect(x0,y0,x1,y1, (0,255,100), f"me{i+1}:{name}({c:.2f})")

    if detector:
        rx,ry,rw,rh = detector.probe_rel
        cv2.rectangle(vis,
                      (int(rx*W), int(ry*H)),
                      (min(W-1,int((rx+rw)*W)), min(H-1,int((ry+rh)*H))),
                      (255,100,0), 2)
        cv2.putText(vis, "card-back probe",
                    (int(rx*W)+2, int(ry*H)-4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255,100,0), 1)

    if locator:
        if hasattr(locator, "game_x_frac"):
            for xf in locator.game_x_frac:
                cv2.line(vis, (int(xf*W),0), (int(xf*W),H), (0,255,255), 1)

    cv2.imwrite(out_path, vis)
    return out_path


def calibrate(screenshot_path: str,
              assets_dir:      str,
              out_path:        str = "debug_heroes.png") -> Optional[HeroResult]:
    """
    Static-screenshot calibration tool.

    Loads the image, runs SceneDetector + CardLocator + TemplateLibrary,
    saves an annotated debug image, and prints a report.

    Usage
    -----
        python hero_recognizer.py screenshot.png ./assets [out.png]
    """
    frame = cv2.imread(screenshot_path)
    if frame is None:
        print(f"ERROR: cannot read '{screenshot_path}'")
        return None

    H, W = frame.shape[:2]
    print(f"Image: {W}×{H}")

    det  = SceneDetector()
    loc  = FixedBoardLocator()
    lib  = TemplateLibrary(assets_dir)

    # Scene detection
    info = det.probe_info(frame)
    print(f"Scene detected : {info['scene']}")
    print(f"  card_back_ratio = {info['card_back_ratio']:.3f}"
          f"  (threshold {det.card_back_ratio})")
    print(f"  centre_mean_v   = {info['centre_mean_v']:.1f}"
          f"  (threshold {det.centre_min_v})")

    # Card location
    opp_b, me_b = loc.locate(frame)
    print(f"Opponent boxes : {len(opp_b)} / 4")
    print(f"Player   boxes : {len(me_b)} / 4")

    # Matching
    opp_n, me_n, confs = [], [], []
    thresh = 0.45
    for i, (x0,y0,x1,y1) in enumerate(opp_b):
        n, s = lib.best_match(frame[y0:y1,x0:x1])
        opp_n.append(n); confs.append(s)
        print(f"  {'✓' if s>=thresh else '✗'} opp{i+1}: {n:<28s} conf={s:.3f}"
              f"  box=({x0},{y0},{x1},{y1})")
    for i, (x0,y0,x1,y1) in enumerate(me_b):
        n, s = lib.best_match(frame[y0:y1,x0:x1])
        me_n.append(n); confs.append(s)
        print(f"  {'✓' if s>=thresh else '✗'} me{i+1}:  {n:<28s} conf={s:.3f}"
              f"  box=({x0},{y0},{x1},{y1})")

    draw_debug(frame, opp_b, me_b,
               opp_n or ["?"]*4, me_n or ["?"]*4,
               confs, det, loc, out_path)
    print(f"\nDebug image → {out_path}")

    if opp_n and me_n:
        return HeroResult(player_heroes=me_n, opponent_heroes=opp_n,
                          confidence=confs, screenshot=frame)
    return None


def run_live_debug(window_hint: str = DEFAULT_TODESK_TITLE,
                   assets_dir:  str = "./game_core/assets",
                   out_dir:     str = "./debug_frames"):
    """
    Grab frames from the projection window continuously and save annotated
    debug images.  Press Ctrl-C to stop.

    Every frame is saved as  debug_frames/preview_NNNN.png  (small thumbnail).
    Frames where the scene is detected also get a full  scene_NNNN.png.

    Usage
    -----
        python hero_recognizer.py --live [window_hint] [assets_dir] [out_dir]
    """
    os.makedirs(out_dir, exist_ok=True)
    grabber = ToDeskGameFrameGrabber(window_hint)
    grabber.find_window()
    det = SceneDetector()
    loc = FixedBoardLocator()
    lib = TemplateLibrary(assets_dir)

    n = 0
    print(f"Live debug  window='{window_hint}'  Ctrl-C to stop")
    try:
        while True:
            raw_frame = grabber.grab_window()
            frame = crop_game_frame_from_window(raw_frame)
            H, W  = frame.shape[:2]
            info  = det.probe_info(frame)

            # Always save a thumbnail
            rH, rW = raw_frame.shape[:2]
            raw_thumb = cv2.resize(raw_frame, (max(1, rW//3), max(1, rH//3)))
            cv2.putText(raw_thumb, f"raw #{n}",
                        (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                        (255, 220, 0), 1)
            cv2.imwrite(os.path.join(out_dir, f"raw_{n:04d}.png"), raw_thumb)

            thumb = cv2.resize(frame, (W//3, H//3))
            color = (0,200,0) if info["scene"] else (0,0,180)
            cv2.putText(thumb,
                        f"{'SCENE' if info['scene'] else 'idle'} "
                        f"cb={info['card_back_ratio']:.2f} "
                        f"v={info['centre_mean_v']:.0f} #{n}",
                        (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 1)
            cv2.imwrite(os.path.join(out_dir, f"preview_{n:04d}.png"), thumb)

            if info["scene"]:
                opp_b, me_b = loc.locate(frame)
                opp_n = [lib.best_match(frame[y0:y1,x0:x1])[0]
                         for x0,y0,x1,y1 in opp_b]
                me_n  = [lib.best_match(frame[y0:y1,x0:x1])[0]
                         for x0,y0,x1,y1 in me_b]
                confs = ([lib.best_match(frame[y0:y1,x0:x1])[1]
                          for x0,y0,x1,y1 in opp_b] +
                         [lib.best_match(frame[y0:y1,x0:x1])[1]
                          for x0,y0,x1,y1 in me_b])
                out = os.path.join(out_dir, f"scene_{n:04d}.png")
                draw_debug(frame, opp_b, me_b, opp_n, me_n, confs, det, loc, out)
                print(f"  #{n} SCENE  opp={opp_n}  me={me_n}")

            n += 1
            time.sleep(0.15)
    except KeyboardInterrupt:
        print(f"\nStopped after {n} frames.  Output → '{out_dir}'")
    finally:
        grabber.close()


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    pos   = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--live" in flags:
        run_live_debug(
            window_hint = pos[0] if len(pos) > 0 else DEFAULT_TODESK_TITLE,
            assets_dir  = pos[1] if len(pos) > 1 else "./game_core/assets",
            out_dir     = pos[2] if len(pos) > 2 else "./debug_frames",
        )
    elif len(pos) >= 2:
        calibrate(
            screenshot_path = pos[0],
            assets_dir      = pos[1],
            out_path        = pos[2] if len(pos) > 2 else "debug_heroes.png",
        )
    else:
        print("Usage:")
        print("  python hero_recognizer.py <screenshot.png> <assets_dir> [out.png]")
        print("  python hero_recognizer.py --live [window_hint] [assets_dir] [out_dir]")
        sys.exit(1)
