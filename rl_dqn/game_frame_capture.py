"""
Reusable game-frame capture helpers.

This module owns the screen-source layer: finding the ToDesk window, grabbing
its pixels, and cropping the mirrored phone/game image out of the window.
Recognition modules should depend on the BGR frame returned here instead of
knowing about ToDesk directly.
"""

from __future__ import annotations

import logging
import ctypes
import ctypes.wintypes
from typing import Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

try:
    from ctypes import windll
    import win32con
    import win32gui
    import win32ui
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False

try:
    import mss as _mss_mod
    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False


DEFAULT_TODESK_TITLE = "HNELP的Android"
GAME_ASPECT_RATIO = 2700.0 / 1224.0

if _WIN32_AVAILABLE:
    try:
        windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _largest_activity_span(activity: np.ndarray, min_len: int) -> Optional[Tuple[int, int]]:
    idx = np.flatnonzero(activity)
    if len(idx) == 0:
        return None

    best = None
    start = prev = int(idx[0])
    for value in idx[1:]:
        value = int(value)
        if value > prev + 1:
            if prev - start + 1 >= min_len and (best is None or prev - start > best[1] - best[0]):
                best = (start, prev + 1)
            start = value
        prev = value
    if prev - start + 1 >= min_len and (best is None or prev - start > best[1] - best[0]):
        best = (start, prev + 1)
    return best


def _detect_top_chrome(frame: np.ndarray) -> int:
    """Return the bottom y of a ToDesk-style bright title/toolbar strip."""
    H, W = frame.shape[:2]
    if H < 80 or W < 160:
        return 0

    limit = min(H // 5, 120)
    hsv = cv2.cvtColor(frame[:limit], cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    chrome_rows = []
    for y in range(limit):
        mean_v = float(val[y].mean())
        mean_s = float(sat[y].mean())
        bright_ratio = float((val[y] > 185).mean())
        chrome_rows.append(mean_v > 185 and mean_s < 130 and bright_ratio > 0.70)

    first_run = 0
    while first_run < limit and chrome_rows[first_run]:
        first_run += 1
    if first_run < 5:
        return 0

    y0 = first_run
    while y0 < min(limit, first_run + 4) and float(val[y0].mean()) < 70:
        y0 += 1
    return y0


def _trim_uniform_borders(frame: np.ndarray) -> Tuple[int, int, int, int]:
    """Conservatively trim only very flat window padding around the phone."""
    H, W = frame.shape[:2]
    grey = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    row_var = grey.var(axis=1)
    col_var = grey.var(axis=0)
    row_sat = hsv[:, :, 1].mean(axis=1)
    col_sat = hsv[:, :, 1].mean(axis=0)

    x0, x1 = 0, W
    y0, y1 = 0, H
    max_y_trim = H // 12
    max_x_trim = W // 12

    while y0 < max_y_trim and row_var[y0] < 20 and row_sat[y0] < 35:
        y0 += 1
    while H - y1 < max_y_trim and row_var[y1 - 1] < 20 and row_sat[y1 - 1] < 35:
        y1 -= 1
    while x0 < max_x_trim and col_var[x0] < 20 and col_sat[x0] < 35:
        x0 += 1
    while W - x1 < max_x_trim and col_var[x1 - 1] < 20 and col_sat[x1 - 1] < 35:
        x1 -= 1

    return x0, y0, x1, y1


def crop_game_frame_from_window(
    frame: np.ndarray,
    target_aspect: float = GAME_ASPECT_RATIO,
    aspect_tolerance: float = 0.08,
) -> np.ndarray:
    """
    Crop the phone/game picture out of a ToDesk window capture.

    The ToDesk window can include a title bar, tool buttons, padding, and
    letterboxing.  We find the largest textured/non-background region, then
    trim it toward the game's landscape aspect ratio.  If no confident crop is
    found, return the original frame so plain screenshots still work.
    """
    if frame is None or frame.size == 0:
        return frame

    H, W = frame.shape[:2]
    if H < 120 or W < 160:
        return frame

    top = _detect_top_chrome(frame)
    work = frame[top:]
    bx0, by0, bx1, by1 = _trim_uniform_borders(work)
    x0, y0, x1, y1 = bx0, top + by0, bx1, top + by1
    crop_w, crop_h = x1 - x0, y1 - y0
    if crop_w <= 0 or crop_h <= 0:
        return frame

    # Prefer preserving the complete phone image.  Aspect correction is only a
    # small, centered trim for chrome/padding; large corrections are left alone.
    aspect = crop_w / crop_h
    if abs(aspect - target_aspect) > aspect_tolerance:
        if aspect > target_aspect:
            new_w = int(crop_h * target_aspect)
            if crop_w - new_w > W * 0.12:
                return frame[y0:y1, x0:x1].copy()
            cx = (x0 + x1) // 2
            x0 = max(0, cx - new_w // 2)
            x1 = min(W, x0 + new_w)
        else:
            new_h = int(crop_w / target_aspect)
            if crop_h - new_h > H * 0.12:
                return frame[y0:y1, x0:x1].copy()
            y0 = max(0, y1 - new_h)
            y1 = min(H, y0 + new_h)

    if (x1 - x0) * (y1 - y0) < 0.50 * W * H:
        return frame
    return frame[y0:y1, x0:x1].copy()


class WindowGrabber:
    """Capture a window by partial title match as a BGR numpy array."""

    def __init__(
        self,
        title_hint: str = DEFAULT_TODESK_TITLE,
        monitor: int = 1,
        capture_method: str = "window",
    ):
        self.title_hint = title_hint.lower()
        self.monitor = monitor
        self.capture_method = capture_method
        self._hwnd: Optional[int] = None
        self._sct = None

    def find_window(self) -> Optional[int]:
        if not _WIN32_AVAILABLE:
            return None
        found = []

        def _cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                if self.title_hint in win32gui.GetWindowText(hwnd).lower():
                    found.append(hwnd)

        win32gui.EnumWindows(_cb, None)
        if found:
            self._hwnd = found[0]
            logger.info(
                "WindowGrabber: window '%s' (hwnd=%d)",
                win32gui.GetWindowText(self._hwnd),
                self._hwnd,
            )
        else:
            logger.warning("WindowGrabber: no window matching '%s'", self.title_hint)
        return self._hwnd

    def grab(self) -> np.ndarray:
        if _WIN32_AVAILABLE:
            hwnd = self._hwnd or self.find_window()
            if hwnd:
                if self.capture_method in {"screen", "auto"}:
                    frame = self._screen_grab_window(hwnd)
                    if frame is not None:
                        return frame
                    if self.capture_method == "screen":
                        self._hwnd = None
                        return self._mss_grab()
                if self.capture_method in {"window", "auto"}:
                    frame = self._bitblt(hwnd)
                    if frame is not None:
                        return frame
                self._hwnd = None
        return self._mss_grab()

    def close(self):
        if self._sct:
            try:
                self._sct.close()
            except Exception:
                pass

    @staticmethod
    def _window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
        try:
            rect = ctypes.wintypes.RECT()
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            hr = windll.dwmapi.DwmGetWindowAttribute(
                hwnd,
                DWMWA_EXTENDED_FRAME_BOUNDS,
                ctypes.byref(rect),
                ctypes.sizeof(rect),
            )
            if hr == 0:
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        try:
            return win32gui.GetWindowRect(hwnd)
        except Exception as exc:
            logger.warning("GetWindowRect failed: %s", exc)
            return None

    def _screen_grab_window(self, hwnd: int) -> Optional[np.ndarray]:
        if not _MSS_AVAILABLE:
            return None
        rect = self._window_rect(hwnd)
        if not rect:
            return None
        l, t, r, b = rect
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return None

        if self._sct is None:
            self._sct = _mss_mod.mss()

        monitors = self._sct.monitors[1:] or [self._sct.monitors[0]]
        virt_left = min(mon["left"] for mon in monitors)
        virt_top = min(mon["top"] for mon in monitors)
        virt_right = max(mon["left"] + mon["width"] for mon in monitors)
        virt_bottom = max(mon["top"] + mon["height"] for mon in monitors)
        l = max(l, virt_left)
        t = max(t, virt_top)
        r = min(r, virt_right)
        b = min(b, virt_bottom)
        if r <= l or b <= t:
            return None

        raw = self._sct.grab({"left": l, "top": t, "width": r - l, "height": b - t})
        return cv2.cvtColor(np.array(raw, np.uint8), cv2.COLOR_BGRA2BGR)

    @staticmethod
    def _bitblt(hwnd: int) -> Optional[np.ndarray]:
        try:
            rect = WindowGrabber._window_rect(hwnd)
            if rect is None:
                return None
            l, t, r, b = rect
            w, h = r - l, b - t
            if w <= 0 or h <= 0:
                return None
            hdc = win32gui.GetWindowDC(hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hdc)
            mem_dc = mfc_dc.CreateCompatibleDC()
            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(mfc_dc, w, h)
            mem_dc.SelectObject(bmp)
            if not windll.user32.PrintWindow(hwnd, mem_dc.GetSafeHdc(), 2):
                mem_dc.BitBlt((0, 0), (w, h), mfc_dc, (0, 0), win32con.SRCCOPY)
            info = bmp.GetInfo()
            raw = bmp.GetBitmapBits(True)
            img = np.frombuffer(raw, np.uint8).reshape(
                info["bmHeight"], info["bmWidth"], 4
            )
            win32gui.DeleteObject(bmp.GetHandle())
            mem_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(hwnd, hdc)
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        except Exception as exc:
            logger.warning("BitBlt failed: %s", exc)
            return None

    def _mss_grab(self) -> np.ndarray:
        if not _MSS_AVAILABLE:
            raise RuntimeError(
                "Neither pywin32 nor mss available.\n"
                "  pip install pywin32   # preferred on Windows\n"
                "  pip install mss       # cross-platform fallback"
            )
        if self._sct is None:
            self._sct = _mss_mod.mss()
        mon = self._sct.monitors[self.monitor]
        raw = self._sct.grab(mon)
        return cv2.cvtColor(np.array(raw, np.uint8), cv2.COLOR_BGRA2BGR)


class ToDeskGameFrameGrabber(WindowGrabber):
    """Grab a ToDesk window and return only the mirrored phone/game area."""

    def __init__(
        self,
        title_hint: str = DEFAULT_TODESK_TITLE,
        monitor: int = 1,
        crop_to_game: bool = True,
    ):
        super().__init__(title_hint=title_hint, monitor=monitor, capture_method="screen")
        self.crop_to_game = crop_to_game

    def grab_window(self) -> np.ndarray:
        return super().grab()

    def grab(self) -> np.ndarray:
        frame = self.grab_window()
        if not self.crop_to_game:
            return frame
        return crop_game_frame_from_window(frame)


def capture_game_frame(
    window_title_hint: str = DEFAULT_TODESK_TITLE,
    monitor: int = 1,
    crop_to_game: bool = True,
) -> np.ndarray:
    """
    Capture the current game image from the ToDesk mirror window.

    Returns a BGR OpenCV image cropped to the phone/game display when possible.
    """
    grabber = ToDeskGameFrameGrabber(
        title_hint=window_title_hint,
        monitor=monitor,
        crop_to_game=crop_to_game,
    )
    try:
        return grabber.grab()
    finally:
        grabber.close()
