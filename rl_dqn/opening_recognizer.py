"""
opening_recognizer.py
====================
Automatic recognition of opening-sequence UI elements after hero reveal:
  1. First/Second player indicator ("你是先手" / "你是后手") at centre-bottom.
  2. Initial hand of 5 cards displayed side-by-side.

This module uses PaddleOCR (Chinese) for text recognition and follows the
same background-thread + callback pattern as hero_recognizer.py.

Quick start
-----------
  # Calibrate on a screenshot:
  python opening_recognizer.py screenshot.png

  # Live debug against the projection window:
  python opening_recognizer.py --live [window_hint] [out_dir]

  # In code:
  rec = OpeningSceneRecognizer(
      window_title_hint="HONOR 11001000 Pro",
      card_names_cn=["武士之拳", "武士之笛", ...],
      card_lookup_cn_to_en={"武士之拳": "WuShiZhiQuan", ...},
  )
  result = rec.detect_turn_order(timeout=30.0)
  result = rec.detect_initial_hand(timeout=30.0)
"""

from __future__ import annotations

import os
import sys
import json
import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, "E:/more_random_project_vibe")

import cv2
import numpy as np

from rl_dqn.game_frame_capture import (
    DEFAULT_TODESK_TITLE,
    ToDeskGameFrameGrabber,
    WindowGrabber,
    crop_game_frame_from_window,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
#  DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class TurnOrderResult:
    """Result of first/second player detection."""
    is_first: bool           # True = 你是先手, False = 你是后手
    raw_text: str            # OCR recognized text
    confidence: float        # match confidence [0, 1]


@dataclass
class HandCard:
    """A single card detected in the initial hand."""
    position_index: int      # 0-4, left to right
    cn_name: str             # matched Chinese card name
    eng_name: str            # matched English card name
    raw_ocr_text: str        # raw OCR output
    confidence: float        # match confidence [0, 1]


@dataclass
class InitialHandResult:
    """Result of initial hand detection."""
    cards: List[HandCard]          # 5 detected cards (left->right)
    all_confident: bool            # True if all cards have confidence >= threshold

    def card_eng_names(self) -> List[str]:
        return [c.eng_name for c in self.cards]


# ═══════════════════════════════════════════════════════════════════════════════
#  REGION CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

_REGION_DIR = os.path.join(os.path.dirname(__file__), "config", "opening_regions.json")


def _load_region_config() -> dict:
    """Load opening screen region definitions from config JSON."""
    if os.path.exists(_REGION_DIR):
        with open(_REGION_DIR, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_region_config(cfg: dict):
    """Save opening screen region definitions to config JSON."""
    os.makedirs(os.path.dirname(_REGION_DIR), exist_ok=True)
    with open(_REGION_DIR, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
#  CARD NAME MATCHER
# ═══════════════════════════════════════════════════════════════════════════════


class CardNameMatcher:
    """
    Fuzzy card name matcher against the cards.json database.

    Matching strategy (tiered):
      1. Exact match -> confidence 1.0
      2. Substring containment -> confidence 0.85
      3. Character-level Jaccard similarity -> confidence = score
      4. Below threshold -> reject
    """

    def __init__(self, match_threshold: float = 0.5):
        self.match_threshold = match_threshold
        self.cn_to_en: Dict[str, str] = {}
        self.cn_names: List[str] = []

    @classmethod
    def from_cards_json(cls, match_threshold: float = 0.5) -> "CardNameMatcher":
        """Factory: build matcher from game_core/cards/cards.json."""
        root = os.path.join(
            os.path.dirname(__file__), "..", "game_core", "cards", "cards.json"
        )
        matcher = cls(match_threshold)
        try:
            with open(root, "r", encoding="utf-8") as f:
                cards = json.load(f)
            for c in cards:
                cn = c.get("name", "")
                en = c.get("eng_name", "")
                if cn and en:
                    matcher.cn_to_en[cn] = en
            matcher.cn_names = sorted(matcher.cn_to_en.keys(), key=len, reverse=True)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.warning("CardNameMatcher: could not load cards.json")
        logger.info("CardNameMatcher: %d card names loaded", len(matcher.cn_to_en))
        return matcher

    def fuzzy_match(self, ocr_text: str) -> Tuple[Optional[str], Optional[str], float]:
        """
        Match OCR text against the card name database.

        Returns (eng_name, cn_name, confidence).
        Returns (None, None, 0.0) if no match found.
        """
        ocr_text = ocr_text.strip()
        if not ocr_text:
            return (None, None, 0.0)

        # Tier 1: exact match
        if ocr_text in self.cn_to_en:
            return (self.cn_to_en[ocr_text], ocr_text, 1.0)

        # Tier 2: substring containment (handle OCR missing prefix/suffix chars)
        for cn_name in self.cn_names:
            if ocr_text in cn_name or cn_name in ocr_text:
                return (self.cn_to_en[cn_name], cn_name, 0.85)

        # Tier 3: character-level Jaccard similarity
        best_name, best_score = None, 0.0
        for cn_name in self.cn_names:
            score = _jaccard_similarity(ocr_text, cn_name)
            if score > best_score:
                best_score = score
                best_name = cn_name

        if best_score >= self.match_threshold and best_name is not None:
            return (self.cn_to_en[best_name], best_name, best_score)

        return (None, None, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  TEXT UTILITY
# ═══════════════════════════════════════════════════════════════════════════════


def _jaccard_similarity(a: str, b: str) -> float:
    """Character-level Jaccard similarity (same algorithm as battle_log_capture.py)."""
    if a == b:
        return 1.0
    set_a = set(a)
    set_b = set(b)
    if not set_a and not set_b:
        return 1.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


# ═══════════════════════════════════════════════════════════════════════════════
#  OPENING SCENE RECOGNISER
# ═══════════════════════════════════════════════════════════════════════════════


class OpeningSceneRecognizer:
    """
    Recognises opening-sequence text on the game screen.

    Provides two main detection methods:
      - detect_turn_order()  -> wait for "你是先手" / "你是后手"
      - detect_initial_hand() -> wait for 5 card names

    Both methods block until detection succeeds or timeout expires.

    Parameters
    ----------
    window_title_hint : partial title of the projection window
    matcher           : CardNameMatcher instance (if None, built from cards.json)
    turn_order_roi    : (x0, y0, x1, y1) as fractions of game frame for
                        the first/second indicator text region.
    hand_cards_roi    : (x0, y0, x1, y1) as fractions of game frame for
                        the region containing all 5 card names.
    confirm_frames    : number of consecutive matching frames required.
    poll_interval     : seconds between frame grabs.
    debug_dir         : directory for stage-by-stage debug image dumps at key
                        moments (None disables).  Each dump shares a
                        dbgNNN_<moment> prefix and covers the full chain:
                        1_window -> 2_title_bar -> 3_game_crop ->
                        4_game_frame(+_roi) -> 5_roi -> 6_roi_pp.
    """

    def __init__(
        self,
        window_title_hint: str = DEFAULT_TODESK_TITLE,
        matcher: Optional[CardNameMatcher] = None,
        turn_order_roi: Optional[Tuple[float, float, float, float]] = None,
        hand_cards_roi: Optional[Tuple[float, float, float, float]] = None,
        confirm_frames: int = 2,
        poll_interval: float = 0.3,
        debug_dir: Optional[str] = "debug_frames",
    ):
        self.grabber = ToDeskGameFrameGrabber(window_title_hint)
        self.matcher = matcher or CardNameMatcher.from_cards_json()
        self.confirm_frames = confirm_frames
        self.poll_interval = poll_interval
        # 调试转储目录（None 关闭）：在关键时刻保存 抓帧→各级裁剪→ROI→预处理
        # 全链图像，用于定位"识别文字落在裁剪区域外"一类问题
        self.debug_dir = debug_dir
        self._dbg_seq = 0

        # Load region config (may be overridden by explicit args)
        cfg = _load_region_config()
        self.turn_order_roi = turn_order_roi or tuple(
            cfg.get("turn_order_roi", [0.25, 0.72, 0.75, 0.90])
        )
        self.hand_cards_roi = hand_cards_roi or tuple(
            cfg.get("hand_cards_roi", [0.05, 0.45, 0.95, 0.72])
        )

        # ── PaddleOCR lazy init ──
        self._ocr = None
        self._ocr_lock = threading.Lock()

    # ── OCR init ────────────────────────────────────────────────────────────

    def _init_ocr(self):
        """Lazy-initialise PaddleOCR (Chinese)."""
        with self._ocr_lock:
            if self._ocr is not None:
                return self._ocr
            try:
                from paddleocr import PaddleOCR
                logger.info("OpeningSceneRecognizer: initialising PaddleOCR (v6 tiny)...")
                self._ocr = PaddleOCR(
                    lang='ch',
                    text_detection_model_name='PP-OCRv6_tiny_det',
                    text_recognition_model_name='PP-OCRv6_tiny_rec',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                )
                logger.info("OpeningSceneRecognizer: PaddleOCR ready.")
            except ImportError:
                logger.error("OpeningSceneRecognizer: PaddleOCR not installed.")
                self._ocr = False  # sentinel
            except Exception as e:
                logger.error("OpeningSceneRecognizer: PaddleOCR init failed: %s", e)
                self._ocr = False
        return self._ocr if self._ocr is not False else None

    # ── Image preprocessing ─────────────────────────────────────────────────

    @staticmethod
    def _preprocess_roi(roi: np.ndarray, scale: float = 1.5) -> tuple:
        """
        Preprocess a cropped ROI for better OCR accuracy:
          1. Scale up (small text is hard for detection model)
          2. Convert to greyscale
          3. CLAHE contrast enhancement
          4. Convert back to BGR (3-channel) for PaddleOCR

        Scale is capped to avoid exceeding PaddleOCR's internal 4000px limit.

        Returns (preprocessed_image, effective_scale).
        """
        h, w = roi.shape[:2]
        # Ensure preprocessed image stays under PaddleOCR's 4000px max_side_limit
        max_dim = max(w, h)
        effective_scale = min(scale, 3900.0 / max_dim) if max_dim > 0 else scale
        new_w, new_h = int(w * effective_scale), int(h * effective_scale)
        scaled = cv2.resize(roi, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

        grey = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(grey)

        # Back to 3-channel BGR for PaddleOCR
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR), effective_scale

    # ── Public API ──────────────────────────────────────────────────────────

    def detect_turn_order(self, timeout: float = 30.0) -> Optional[TurnOrderResult]:
        """
        Block until the first/second-player indicator appears at centre-bottom.

        Polls frames at self.poll_interval, OCRs the turn_order_roi, and
        looks for the substrings "先手" or "后手".  Requires confirm_frames
        consecutive frames with the same result.

        Returns TurnOrderResult, or None on timeout / error.
        """
        self.grabber.find_window()
        ocr = self._init_ocr()
        if ocr is None:
            logger.error("detect_turn_order: OCR not available")
            return None

        logger.info("detect_turn_order: waiting for first/second indicator...")
        confirmed_text = ""
        confirm_count = 0
        deadline = time.monotonic() + timeout
        dbg_first = 0    # 已转储的开场前几帧数
        dbg_hits = 0     # 已转储的命中帧数
        last = ({}, None, None, None)  # 最后一帧 (stages, game_frame, roi, pp_roi)

        while time.monotonic() < deadline:
            try:
                frame, stages = self._grab_with_stages()
            except Exception as e:
                logger.error("detect_turn_order: grab error: %s", e)
                time.sleep(self.poll_interval)
                continue

            game_frame = crop_game_frame_from_window(frame)
            if game_frame is None or game_frame.size == 0:
                time.sleep(self.poll_interval)
                continue

            # Crop the turn-order region
            roi = self._crop_roi(game_frame, self.turn_order_roi)
            if roi is None:
                time.sleep(self.poll_interval)
                continue

            # 调试：最初 2 帧全链转储（横幅出现前的基线画面）
            if dbg_first < 2:
                dbg_first += 1
                self._dbg_dump(stages, game_frame, self.turn_order_roi,
                               roi, None, "first")
            last = (stages, game_frame, roi, None)

            # Quick check: does the region have enough variance to contain text?
            grey = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            if grey.var() < 15:
                # No text in region yet; keep waiting but don't reset confirm
                time.sleep(self.poll_interval)
                continue

            # Preprocess for better OCR
            pp_roi, _ = self._preprocess_roi(roi)
            last = (stages, game_frame, roi, pp_roi)

            # OCR
            try:
                results = ocr.predict(pp_roi)
                if isinstance(results, list):
                    result = results[0] if results else None
                else:
                    result = next(results, None)
            except Exception as e:
                logger.error("detect_turn_order: OCR error: %s", e)
                time.sleep(self.poll_interval)
                continue

            if result is None:
                time.sleep(self.poll_interval)
                continue

            rec_texts = list(result.get("rec_texts", []))
            rec_scores = list(result.get("rec_scores", []))
            if not rec_texts:
                time.sleep(self.poll_interval)
                continue

            # Look for lines containing "先手" or "后手" with confidence filter
            found = None
            for i, text in enumerate(rec_texts):
                t = text.strip()
                # Require OCR confidence >= 0.5
                score = rec_scores[i] if i < len(rec_scores) else 1.0
                if score < 0.5:
                    continue
                if "先手" in t:
                    found = ("先手", True, t)
                    break
                elif "后手" in t:
                    found = ("后手", False, t)
                    break

            if found is not None:
                keyword, is_first, raw_text = found
                # 调试：命中帧全链转储（前 3 帧），核对横幅在各裁剪阶段是否完整
                if dbg_hits < 3:
                    dbg_hits += 1
                    self._dbg_dump(stages, game_frame, self.turn_order_roi,
                                   roi, pp_roi, f"hit{dbg_hits}")
                if keyword == confirmed_text:
                    confirm_count += 1
                    if confirm_count >= self.confirm_frames:
                        logger.info("detect_turn_order: confirmed %s (text='%s')",
                                    "先手" if is_first else "后手", raw_text)
                        self._dbg_dump(stages, game_frame, self.turn_order_roi,
                                       roi, pp_roi, "confirm")
                        return TurnOrderResult(
                            is_first=is_first,
                            raw_text=raw_text,
                            confidence=1.0,
                        )
                else:
                    confirmed_text = keyword
                    confirm_count = 1

            time.sleep(self.poll_interval)

        # 调试：超时时转储最后一帧全链
        st, gf, roi_l, pp_l = last
        if gf is not None:
            self._dbg_dump(st, gf, self.turn_order_roi, roi_l, pp_l, "timeout")
        logger.warning("detect_turn_order: timeout (%.1fs)", timeout)
        return None

    def detect_initial_hand(self, timeout: float = 30.0) -> Optional[InitialHandResult]:
        """
        Block until 5 initial hand cards appear and are recognised.

        Polls frames, OCRs the hand_cards_roi, filters text by height
        (to exclude smaller description text), and fuzzy-matches against
        the card name database.

        收紧：确认前要求 5 张全部模糊匹配成功（无 "unknown"）。发牌动画
        从左到右逐张亮牌，中途帧的空槽会被无关大字填充凑数，带脏数据
        确认返回会在后续 Card.GetCard 上崩溃；匹配不全的帧直接跳过，
        持续等待到完整稳定帧，等不到则超时返回 None（走手动输入）。

        Returns InitialHandResult, or None on timeout / error.
        """
        self.grabber.find_window()
        ocr = self._init_ocr()
        if ocr is None:
            logger.error("detect_initial_hand: OCR not available")
            return None

        logger.info("detect_initial_hand: waiting for 5 hand cards...")
        last_cards: List[HandCard] = []
        confirm_count = 0
        deadline = time.monotonic() + timeout
        dbg_first = 0    # 已转储的开场前几帧数
        dbg_hands = 0    # 已转储的凑满 5 候选帧数
        last = ({}, None, None, None)  # 最后一帧 (stages, game_frame, roi, pp_roi)

        while time.monotonic() < deadline:
            try:
                frame, stages = self._grab_with_stages()
            except Exception as e:
                logger.error("detect_initial_hand: grab error: %s", e)
                time.sleep(self.poll_interval)
                continue

            game_frame = crop_game_frame_from_window(frame)
            if game_frame is None or game_frame.size == 0:
                time.sleep(self.poll_interval)
                continue

            # Crop the hand-cards region
            roi = self._crop_roi(game_frame, self.hand_cards_roi)
            if roi is None:
                time.sleep(self.poll_interval)
                continue

            # 调试：最初 2 帧全链转储（发牌前的基线画面）
            if dbg_first < 2:
                dbg_first += 1
                self._dbg_dump(stages, game_frame, self.hand_cards_roi,
                               roi, None, "first")
            last = (stages, game_frame, roi, None)

            # Quick check: enough variance?
            grey = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            if grey.var() < 20:
                time.sleep(self.poll_interval)
                continue

            # Preprocess for better OCR
            pp_roi, pp_scale = self._preprocess_roi(roi)
            last = (stages, game_frame, roi, pp_roi)

            # OCR
            try:
                results = ocr.predict(pp_roi)
                if isinstance(results, list):
                    ocr_result = results[0] if results else None
                else:
                    ocr_result = next(results, None)
            except Exception as e:
                logger.error("detect_initial_hand: OCR error: %s", e)
                time.sleep(self.poll_interval)
                continue

            if ocr_result is None:
                time.sleep(self.poll_interval)
                continue

            rec_texts = list(ocr_result.get("rec_texts", []))
            rec_scores = list(ocr_result.get("rec_scores", []))
            dt_polys = list(ocr_result.get("dt_polys", []))
            rec_boxes = list(ocr_result.get("rec_boxes", []))

            if not rec_texts:
                time.sleep(self.poll_interval)
                continue

            # ── Build list of (text, height, x_center, y_min, ocr_conf) tuples ──
            text_blocks: List[Tuple[str, float, float, float, float]] = []
            for i, text in enumerate(rec_texts):
                if not text or not text.strip():
                    continue
                # OCR confidence filter
                ocr_conf = rec_scores[i] if i < len(rec_scores) else 1.0
                if ocr_conf < 0.5:
                    continue
                # Get bounding box height (coordinates are in pp_roi / scaled space)
                if i < len(dt_polys):
                    poly = dt_polys[i]
                    y_vals = [p[1] for p in poly]
                    x_vals = [p[0] for p in poly]
                    height = max(y_vals) - min(y_vals)
                    y_min = min(y_vals)
                    x_center = (min(x_vals) + max(x_vals)) / 2.0
                elif i < len(rec_boxes):
                    box = rec_boxes[i]
                    height = box[3] - box[1]
                    y_min = box[1]
                    x_center = (box[0] + box[2]) / 2.0
                else:
                    height = 0.0
                    y_min = 0.0
                    x_center = 0.0

                if height <= 0:
                    continue

                text_blocks.append((text.strip(), height, x_center, y_min, ocr_conf))

            if len(text_blocks) < 5:
                time.sleep(self.poll_interval)
                continue

            # ── Filter: keep only larger-font text blocks (card names) ──
            # The height distribution has two clusters: larger (card names)
            # and smaller (description text).  We take blocks whose height
            # is at least 60% of the maximum height in this batch.
            heights = [h for _, h, _, _, _ in text_blocks]
            max_height = max(heights)
            height_threshold = max_height * 0.55

            name_candidates = [
                (text, x_center, y_min, height, ocr_conf)
                for text, height, x_center, y_min, ocr_conf in text_blocks
                if height >= height_threshold
            ]

            if len(name_candidates) < 5:
                # Not enough large-font text blocks yet
                time.sleep(self.poll_interval)
                continue

            # ── Sort by x position and take the 5 highest-confidence matches ──
            name_candidates.sort(key=lambda t: t[1])  # sort by x_center

            # If there are more than 5 large-font blocks, cluster by x and
            # take the highest (topmost) one in each cluster
            if len(name_candidates) > 5:
                name_candidates = self._cluster_and_pick(
                    name_candidates, target_count=5
                )

            if len(name_candidates) < 5:
                time.sleep(self.poll_interval)
                continue

            # Take exactly the first 5 by x position
            selected = name_candidates[:5]

            # 临时调试：CLI 输出本帧选中的 5 个原始 OCR 文本
            # （观察发牌动画期的脏数据，定位后删除）
            print(f"[hand-debug] raw texts: {[t for t, *_ in selected]}",
                  flush=True)

            # 调试：凑满 5 候选的帧全链转储（前 3 帧）
            if dbg_hands < 3:
                dbg_hands += 1
                self._dbg_dump(stages, game_frame, self.hand_cards_roi,
                               roi, pp_roi, f"hand{dbg_hands}")

            # Match each candidate against card name database
            cards: List[HandCard] = []
            for idx, (text, xc, ym, h, ocr_conf) in enumerate(selected):
                eng, cn, match_conf = self.matcher.fuzzy_match(text)
                # Combine OCR confidence with match confidence
                combined_conf = match_conf * ocr_conf
                cards.append(HandCard(
                    position_index=idx,
                    cn_name=cn or text,
                    eng_name=eng or "unknown",
                    raw_ocr_text=text,
                    confidence=combined_conf,
                ))

            # ── 收紧：5 张必须全部匹配成功，含 "unknown" 的帧不参与确认 ──
            # 不重置 confirm_count / last_cards：中间的脏帧视为未就绪，
            # 仍是同一稳定内容的两帧照样可以先后确认
            if any(c.eng_name == "unknown" for c in cards):
                time.sleep(self.poll_interval)
                continue

            # Check if this batch matches the previous batch
            if self._same_cards(cards, last_cards):
                confirm_count += 1
                if confirm_count >= self.confirm_frames:
                    self._dbg_dump(stages, game_frame, self.hand_cards_roi,
                                   roi, pp_roi, "confirm")
                    all_good = all(c.confidence >= 0.35 for c in cards)
                    logger.info(
                        "detect_initial_hand: confirmed %d cards (all_confident=%s)",
                        len(cards), all_good,
                    )
                    for c in cards:
                        logger.info("  card %d: %s (%s) conf=%.2f",
                                    c.position_index, c.cn_name, c.eng_name, c.confidence)
                    return InitialHandResult(cards=cards, all_confident=all_good)
            else:
                confirm_count = 1
                last_cards = cards

            time.sleep(self.poll_interval)

        # 调试：超时时转储最后一帧全链
        st, gf, roi_l, pp_l = last
        if gf is not None:
            self._dbg_dump(st, gf, self.hand_cards_roi, roi_l, pp_l, "timeout")
        logger.warning("detect_initial_hand: timeout (%.1fs)", timeout)
        return None

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _grab_with_stages(self) -> Tuple[np.ndarray, dict]:
        """
        grab() 一次，并让 self.grabber.last_stages 记录抓取管线各阶段中间帧
        （仅本次调用生效）。返回 (frame, stages)。
        """
        stages: dict = {}
        self.grabber.last_stages = stages
        try:
            frame = self.grabber.grab()
        finally:
            self.grabber.last_stages = None
        return frame, stages

    def _dbg_dump(self, stages: dict, game_frame: Optional[np.ndarray],
                  roi_fracs: Tuple[float, float, float, float],
                  roi: Optional[np.ndarray], pp_roi: Optional[np.ndarray],
                  moment: str) -> None:
        """
        把一个关键帧的全链图像存到 debug_dir（self.debug_dir 为 None 时跳过）：

          dbgNNN_<moment>_1_window.png          原始窗口抓帧（未做任何裁剪）
          dbgNNN_<moment>_2_title_bar.png       顶部"手机屏幕"标题栏裁剪之后
          dbgNNN_<moment>_3_game_crop.png       grabber 内 crop_game_frame_from_window 之后
          dbgNNN_<moment>_4_game_frame.png      detect_* 内再次 crop 后（ROI 的来源帧）
          dbgNNN_<moment>_4_game_frame_roi.png  同上并画出 ROI 框
          dbgNNN_<moment>_5_roi.png             送识别的 ROI 裁剪
          dbgNNN_<moment>_6_roi_pp.png          ROI 预处理（放大/CLAHE）后，OCR 实际输入
        """
        if not self.debug_dir:
            return
        try:
            os.makedirs(self.debug_dir, exist_ok=True)
            self._dbg_seq += 1
            prefix = os.path.join(
                self.debug_dir, f"dbg{self._dbg_seq:03d}_{moment}")
            for name in ("1_window", "2_title_bar", "3_game_crop"):
                img = stages.get(name)
                if img is not None and img.size > 0:
                    cv2.imwrite(f"{prefix}_{name}.png", img)
            if game_frame is not None and game_frame.size > 0:
                cv2.imwrite(f"{prefix}_4_game_frame.png", game_frame)
                vis = game_frame.copy()
                H, W = vis.shape[:2]
                x0 = int(roi_fracs[0] * W)
                y0 = int(roi_fracs[1] * H)
                x1 = int(roi_fracs[2] * W)
                y1 = int(roi_fracs[3] * H)
                cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 0, 255), 2)
                cv2.imwrite(f"{prefix}_4_game_frame_roi.png", vis)
            if roi is not None and roi.size > 0:
                cv2.imwrite(f"{prefix}_5_roi.png", roi)
            if pp_roi is not None and pp_roi.size > 0:
                cv2.imwrite(f"{prefix}_6_roi_pp.png", pp_roi)
            print(f"[dbg] saved {prefix}_*.png", flush=True)
        except Exception as exc:
            logger.warning("debug dump failed: %s", exc)

    @staticmethod
    def _crop_roi(frame: np.ndarray,
                  roi_fracs: Tuple[float, float, float, float]
                  ) -> Optional[np.ndarray]:
        """Crop a relative-coordinate ROI from a frame."""
        H, W = frame.shape[:2]
        x0 = max(0, int(roi_fracs[0] * W))
        y0 = max(0, int(roi_fracs[1] * H))
        x1 = min(W, int(roi_fracs[2] * W))
        y1 = min(H, int(roi_fracs[3] * H))
        if x1 <= x0 or y1 <= y0:
            return None
        return frame[y0:y1, x0:x1]

    @staticmethod
    def _cluster_and_pick(
        candidates: List[Tuple[str, float, float, float, float]],
        target_count: int = 5,
    ) -> List[Tuple[str, float, float, float, float]]:
        """
        Cluster text blocks by x position and keep the highest (smallest y)
        block in each cluster.  Used to merge multiple detections in the same
        card column (name + description) into a single candidate per column.

        Each candidate: (text, x_center, y_min, height, ocr_conf)
        """
        if len(candidates) <= target_count:
            return candidates

        # Use the actual x-range of candidates for column width calculation
        x_min = min(c[1] for c in candidates)
        x_max = max(c[1] for c in candidates)
        roi_width = x_max - x_min if x_max > x_min else 1.0
        col_width = roi_width / target_count

        # Assign each candidate to a column bucket by x_center
        buckets: Dict[int, List[Tuple[str, float, float, float, float]]] = {}
        for item in candidates:
            xc = item[1]
            col = min(target_count - 1, max(0, int((xc - x_min) / col_width)))
            if isinstance(col, float):
                col = int(col)
            buckets.setdefault(col, []).append(item)

        # From each bucket pick the topmost (smallest y_min) text block
        result = []
        for col in range(target_count):
            bucket = buckets.get(col, [])
            if bucket:
                # Pick the one with smallest y_min (card name is above description)
                best = min(bucket, key=lambda t: t[2])
                result.append(best)

        result.sort(key=lambda t: t[1])  # re-sort by x_center
        return result

    @staticmethod
    def _same_cards(a: List[HandCard], b: List[HandCard]) -> bool:
        """Check if two hand card batches are the same (for confirm_frames)."""
        if len(a) != len(b) or len(a) == 0:
            return False
        for ca, cb in zip(a, b):
            if ca.eng_name != cb.eng_name or ca.position_index != cb.position_index:
                return False
        return True

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def close(self):
        """Release the window grabber."""
        self.grabber.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  CALIBRATION / DEBUG TOOLS
# ═══════════════════════════════════════════════════════════════════════════════


def calibrate_on_screenshot(screenshot_path: str,
                            out_dir: str = "./debug_frames") -> None:
    """
    Run turn-order and initial-hand detection on a static screenshot
    for calibration purposes.  Saves annotated debug frames.

    Usage
    -----
        python opening_recognizer.py screenshot.png
    """
    frame = cv2.imread(screenshot_path)
    if frame is None:
        print(f"ERROR: cannot read '{screenshot_path}'")
        return

    H, W = frame.shape[:2]
    print(f"Image: {W}x{H}")

    cfg = _load_region_config()
    turn_roi = tuple(cfg.get("turn_order_roi", [0.25, 0.72, 0.75, 0.90]))
    hand_roi = tuple(cfg.get("hand_cards_roi", [0.05, 0.45, 0.95, 0.72]))

    matcher = CardNameMatcher.from_cards_json()

    os.makedirs(out_dir, exist_ok=True)

    # ── Turn order region ──
    to_x0 = int(turn_roi[0] * W)
    to_y0 = int(turn_roi[1] * H)
    to_x1 = int(turn_roi[2] * W)
    to_y1 = int(turn_roi[3] * H)

    vis = frame.copy()
    cv2.rectangle(vis, (to_x0, to_y0), (to_x1, to_y1), (0, 255, 255), 2)
    cv2.putText(vis, "turn_order_roi", (to_x0 + 2, to_y0 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)

    hc_x0 = int(hand_roi[0] * W)
    hc_y0 = int(hand_roi[1] * H)
    hc_x1 = int(hand_roi[2] * W)
    hc_y1 = int(hand_roi[3] * H)
    cv2.rectangle(vis, (hc_x0, hc_y0), (hc_x1, hc_y1), (255, 200, 0), 2)
    cv2.putText(vis, "hand_cards_roi", (hc_x0 + 2, hc_y0 - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 200, 0), 1)

    cv2.imwrite(os.path.join(out_dir, "opening_regions.png"), vis)
    print(f"Annotated regions -> {os.path.join(out_dir, 'opening_regions.png')}")

    # ── Run OCR on turn-order region ──
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang='ch')
    except Exception as e:
        print(f"PaddleOCR init failed: {e}")
        return

    # Reuse the same preprocessing as the real-time detector
    preprocess = OpeningSceneRecognizer._preprocess_roi

    turn_crop = frame[to_y0:to_y1, to_x0:to_x1]
    if turn_crop.size > 0:
        print("\n── Turn-order region OCR ──")
        pp_turn, _ = preprocess(turn_crop)
        results = ocr.predict(pp_turn)
        if isinstance(results, list):
            result = results[0] if results else None
        else:
            result = next(results, None)
        if result:
            rec_texts = result.get("rec_texts", [])
            rec_scores = result.get("rec_scores", [])
            for i, text in enumerate(rec_texts):
                score = rec_scores[i] if i < len(rec_scores) else -1.0
                is_first = "先手" in text
                is_second = "后手" in text
                tag = ""
                if is_first:
                    tag = "  <-- 先手"
                elif is_second:
                    tag = "  <-- 后手"
                print(f"  '{text}'  ocr_conf={score:.2f}{tag}")
        else:
            print("  (no text detected)")

    # ── Run OCR on hand-cards region ──
    hand_crop = frame[hc_y0:hc_y1, hc_x0:hc_x1]
    if hand_crop.size > 0:
        print("\n── Hand-cards region OCR ──")
        print(f"  crop size: {hand_crop.shape[1]}x{hand_crop.shape[0]}")
        pp_hand, _ = preprocess(hand_crop)
        print(f"  after preprocess: {pp_hand.shape[1]}x{pp_hand.shape[0]}")
        results = ocr.predict(pp_hand)
        if isinstance(results, list):
            ocr_result = results[0] if results else None
        else:
            ocr_result = next(results, None)
        if ocr_result:
            rec_texts = list(ocr_result.get("rec_texts", []))
            rec_scores = list(ocr_result.get("rec_scores", []))
            dt_polys = list(ocr_result.get("dt_polys", []))
            print(f"  Total text blocks: {len(rec_texts)}")

            # Build items with OCR confidence and height
            items = []
            for i, text in enumerate(rec_texts):
                if not text or not text.strip():
                    continue
                ocr_conf = rec_scores[i] if i < len(rec_scores) else -1.0
                poly = dt_polys[i] if i < len(dt_polys) else None
                if poly is not None:
                    y_vals = [p[1] for p in poly]
                    x_vals = [p[0] for p in poly]
                    height = max(y_vals) - min(y_vals)
                    xc = (min(x_vals) + max(x_vals)) / 2.0
                else:
                    height = 0
                    xc = 0
                eng, cn, match_conf = matcher.fuzzy_match(text)
                combined = match_conf * ocr_conf
                items.append((xc, height, text, cn, eng, match_conf, ocr_conf, combined))

            if not items:
                print("  (no text blocks with content)")
            else:
                items.sort(key=lambda t: t[0])

                # ── Height analysis ──
                heights = [h for _, h, _, _, _, _, _, _ in items]
                max_h = max(heights)
                threshold = max_h * 0.55
                print(f"  Height range: {min(heights):.0f} - {max_h:.0f}  "
                      f"(threshold for card-name: >{threshold:.0f})")

                # ── Print all detected text blocks ──
                print(f"  {'Status':<6} {'x':>6s} {'h':>5s} {'ocr':>5s} {'match':>6s} {'comb':>6s}  text -> match")
                print(f"  {'-'*6} {'-'*6} {'-'*5} {'-'*5} {'-'*6} {'-'*6}  {'-'*30}")
                for xc, h, text, cn, eng, match_conf, ocr_conf, combined in items:
                    is_name = "NAME" if h >= threshold else "desc"
                    status = "OK" if combined >= 0.4 else "--"
                    cn_str = f"{cn}" if cn else "?"
                    print(f"  [{status}] {is_name:<4s} x={xc:5.0f} h={h:4.0f} "
                          f"ocr={ocr_conf:.2f} match={match_conf:.2f} comb={combined:.2f}  "
                          f"'{text}' -> {cn_str}")

            # ── Save debug visualisation ──
            _save_hand_debug_image(pp_hand, items, matcher, out_dir)

        else:
            print("  (no text detected)")


def _save_hand_debug_image(pp_roi: np.ndarray,
                           items: list,
                           matcher: CardNameMatcher,
                           out_dir: str) -> None:
    """
    Save an annotated debug image of the hand-cards ROI showing:
      - All detected text blocks with bounding boxes
      - Green = card-name height (>= 55% of max), Red = description height
      - OCR text, confidence, and match result labels
      - Also saves a side-by-side: original crop vs preprocessed
    """
    # items: list of (xc, height, text, cn, eng, match_conf, ocr_conf, combined)
    if not items:
        return

    vis = pp_roi.copy()
    heights = [h for _, h, _, _, _, _, _, _ in items]
    max_h = max(heights)
    threshold = max_h * 0.55

    for xc, h, text, cn, eng, match_conf, ocr_conf, combined in items:
        is_name = h >= threshold
        color = (0, 255, 0) if is_name else (0, 0, 255)

        # Draw a marker at the text centre
        cx, cy = int(xc), int(pp_roi.shape[0] * 0.5)  # approximate y-centre
        cv2.circle(vis, (cx, cy), max(3, int(h * 0.3)), color, -1)

        # Label
        cn_label = cn if cn else "?"
        label = f"{text}"
        status = "OK" if combined >= 0.4 else "??"
        full_label = f"[{status}] {label} -> {cn_label} (h={h:.0f})"
        y_pos = 15 + items.index((xc, h, text, cn, eng, match_conf, ocr_conf, combined)) * 22
        cv2.putText(vis, full_label, (5, y_pos),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1)

    debug_path = os.path.join(out_dir, "hand_cards_debug.png")
    cv2.imwrite(debug_path, vis)
    print(f"\n  Debug image saved: {debug_path}")


def run_live_debug(window_hint: str = DEFAULT_TODESK_TITLE,
                   out_dir: str = "./debug_frames"):
    """
    Continuously grab frames and run opening detection for live calibration.

    Usage
    -----
        python opening_recognizer.py --live [window_hint] [out_dir]
    """
    os.makedirs(out_dir, exist_ok=True)
    grabber = ToDeskGameFrameGrabber(window_hint)
    grabber.find_window()

    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(lang='ch')
    except Exception as e:
        print(f"PaddleOCR init failed: {e}")
        return

    matcher = CardNameMatcher.from_cards_json()
    cfg = _load_region_config()
    turn_roi = tuple(cfg.get("turn_order_roi", [0.25, 0.72, 0.75, 0.90]))
    hand_roi = tuple(cfg.get("hand_cards_roi", [0.05, 0.45, 0.95, 0.72]))

    n = 0
    print(f"Live debug  window='{window_hint}'  Ctrl-C to stop")
    try:
        while True:
            raw = grabber.grab()
            frame = crop_game_frame_from_window(raw)
            H, W = frame.shape[:2]

            # Turn-order region
            to_x0 = int(turn_roi[0] * W)
            to_y0 = int(turn_roi[1] * H)
            to_x1 = int(turn_roi[2] * W)
            to_y1 = int(turn_roi[3] * H)
            turn_crop = frame[to_y0:to_y1, to_x0:to_x1]

            hand_x0 = int(hand_roi[0] * W)
            hand_y0 = int(hand_roi[1] * H)
            hand_x1 = int(hand_roi[2] * W)
            hand_y1 = int(hand_roi[3] * H)
            hand_crop = frame[hand_y0:hand_y1, hand_x0:hand_x1]

            # OCR
            turn_texts = []
            if turn_crop.size > 0:
                r = ocr.predict(turn_crop)
                if isinstance(r, list):
                    r = r[0] if r else None
                else:
                    r = next(r, None)
                if r:
                    turn_texts = r.get("rec_texts", [])

            hand_texts = []
            if hand_crop.size > 0:
                r = ocr.predict(hand_crop)
                if isinstance(r, list):
                    r = r[0] if r else None
                else:
                    r = next(r, None)
                if r:
                    hand_texts = r.get("rec_texts", [])

            # Print
            turn_summary = ", ".join(
                f"'{t}'" for t in turn_texts) if turn_texts else "(empty)"
            hand_matches = []
            for t in hand_texts:
                eng, cn, conf = matcher.fuzzy_match(t)
                if cn:
                    hand_matches.append(f"'{t}'->{cn}({conf:.2f})")
                else:
                    hand_matches.append(f"'{t}'->?")
            hand_summary = ", ".join(hand_matches) if hand_matches else "(empty)"

            print(f"#{n:04d}  turn_order: {turn_summary}  |  hand: {hand_summary}")

            # Save debug thumbnail
            thumb = cv2.resize(frame, (W // 3, H // 3))
            cv2.rectangle(thumb,
                          (to_x0 // 3, to_y0 // 3),
                          (to_x1 // 3, to_y1 // 3),
                          (0, 255, 255), 1)
            cv2.rectangle(thumb,
                          (hand_x0 // 3, hand_y0 // 3),
                          (hand_x1 // 3, hand_y1 // 3),
                          (255, 200, 0), 1)
            cv2.imwrite(os.path.join(out_dir, f"opening_{n:04d}.png"), thumb)

            n += 1
            time.sleep(0.3)
    except KeyboardInterrupt:
        print(f"\nStopped after {n} frames. Output -> '{out_dir}'")
    finally:
        grabber.close()


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]

    if "--live" in flags:
        run_live_debug(
            window_hint=pos[0] if len(pos) > 0 else DEFAULT_TODESK_TITLE,
            out_dir=pos[1] if len(pos) > 1 else "./debug_frames",
        )
    elif len(pos) >= 1:
        calibrate_on_screenshot(screenshot_path=pos[0])
    else:
        print("Usage:")
        print("  python opening_recognizer.py <screenshot.png>")
        print("  python opening_recognizer.py --live [window_hint] [out_dir]")
        sys.exit(1)
