from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import io
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

from PIL import Image
from PIL import ImageGrab
import numpy as np

try:
    import uiautomation as auto
except Exception:  # pragma: no cover - optional runtime dependency
    auto = None

from .config import Settings

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = ctypes.c_void_p
kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
user32.OpenClipboard.argtypes = [ctypes.c_void_p]
user32.OpenClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
user32.SetClipboardData.restype = ctypes.c_void_p
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL

SW_RESTORE = 9
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
CF_UNICODETEXT = 13
CF_DIB = 8
GMEM_MOVEABLE = 0x0002
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_RETURN = 0x0D
VK_ESCAPE = 0x1B
VK_V = 0x56


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("union", INPUT_UNION)]


@dataclass
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return max(0, self.right - self.left)

    @property
    def height(self) -> int:
        return max(0, self.bottom - self.top)

    @property
    def area(self) -> int:
        return self.width * self.height


class GuiAutomationError(RuntimeError):
    pass


def _send_input(inputs: Iterable[INPUT]) -> None:
    rows = list(inputs)
    if not rows:
        return
    array_type = INPUT * len(rows)
    count = user32.SendInput(len(rows), array_type(*rows), ctypes.sizeof(INPUT))
    if count != len(rows):
        raise GuiAutomationError("SendInput failed.")


def _vk_input(vk: int, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_KEYUP if key_up else 0
    return INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=None)))


def _unicode_input(char: str, key_up: bool = False) -> INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if key_up else 0)
    return INPUT(type=INPUT_KEYBOARD, union=INPUT_UNION(ki=KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags, time=0, dwExtraInfo=None)))


def _mouse_input(flags: int) -> INPUT:
    return INPUT(type=INPUT_MOUSE, union=INPUT_UNION(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=flags, time=0, dwExtraInfo=None)))


class WindowsCodexController:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def codex_thread_deeplink(self, thread_id: str) -> str:
        return f"codex://threads/{thread_id}"

    def codex_new_thread_deeplink(self, project_path: str = "") -> str:
        query = f"?{urlencode({'path': project_path})}" if project_path else ""
        return f"codex://threads/new{query}"

    def open_uri(self, uri: str) -> None:
        log.info("Opening URI %s", uri)
        try:
            os.startfile(uri)  # type: ignore[attr-defined]
        except OSError:
            subprocess.run(["cmd", "/c", "start", "", uri], check=True)

    def _window_process_path(self, hwnd: int) -> str:
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if not process_id.value:
            return ""

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        process = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id.value)
        if not process:
            return ""
        try:
            buffer = ctypes.create_unicode_buffer(32768)
            size = ctypes.c_ulong(len(buffer))
            if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                return buffer.value
            return ""
        finally:
            kernel32.CloseHandle(process)

    def list_codex_windows(self) -> list[WindowInfo]:
        windows: list[WindowInfo] = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def enum_proc(hwnd: int, lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            title_buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
            title = title_buffer.value.strip()
            process_path = self._window_process_path(hwnd)
            process_name = os.path.basename(process_path).lower()
            owner_ok = (
                process_name in {"codex.exe", "codex"} or
                "openai.codex" in process_path.lower() or
                title == "Codex"
            )
            if not owner_ok:
                return True
            rect = RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            windows.append(WindowInfo(hwnd=hwnd, title=title, left=rect.left, top=rect.top, right=rect.right, bottom=rect.bottom))
            return True

        user32.EnumWindows(enum_proc, 0)
        return sorted(windows, key=lambda item: item.area, reverse=True)

    def find_codex_window(self) -> WindowInfo:
        windows = self.list_codex_windows()
        if not windows:
            raise GuiAutomationError("No visible Codex window found. Start Codex Desktop first.")
        return windows[0]

    def _uia_codex_root(self):
        if auto is None:
            return None
        try:
            window = self.find_codex_window()
            root = auto.ControlFromHandle(window.hwnd)
            return root if root and root.Exists(0.5) else None
        except Exception:
            return None

    def _uia_content_rect(self) -> Rect | None:
        root = self._uia_codex_root()
        if root is None:
            return None

        try:
            descendants = [root]
            index = 0
            while index < len(descendants):
                control = descendants[index]
                index += 1
                try:
                    descendants.extend(control.GetChildren())
                except Exception:
                    continue
        except Exception:
            return None

        best: Rect | None = None
        for control in descendants:
            try:
                control_type = control.ControlTypeName or ""
                class_name = control.ClassName or ""
                rect = control.BoundingRectangle
                candidate = Rect(rect.left, rect.top, rect.right, rect.bottom)
            except Exception:
                continue

            if candidate.width < 400 or candidate.height < 250:
                continue

            is_document = control_type == "DocumentControl"
            is_render_host = class_name in {"Chrome_RenderWidgetHostHWND", "Chrome_WidgetWin_1"}
            is_main_view = class_name == "View"
            if not (is_document or is_render_host or is_main_view):
                continue

            if best is None or candidate.area > best.area:
                best = candidate

        return best

    def _capture_rect(self, rect: Rect) -> Image.Image:
        return ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)

    def _detect_composer_rect(self, content_rect: Rect) -> Rect | None:
        if content_rect.width < 500 or content_rect.height < 350:
            return None

        try:
            image = self._capture_rect(content_rect).convert("L")
        except Exception:
            return None

        pixels = np.array(image)
        height, width = pixels.shape
        matches: list[tuple[int, int, int]] = []
        threshold = 40

        for y in range(int(height * 0.5), max(int(height * 0.5) + 1, height - 5)):
            indexes = np.where(pixels[y] > threshold)[0]
            if len(indexes) == 0:
                continue
            splits = np.where(np.diff(indexes) > 1)[0]
            starts = np.r_[0, splits + 1]
            ends = np.r_[splits, len(indexes) - 1]

            for start, end in zip(starts, ends):
                x1 = int(indexes[start])
                x2 = int(indexes[end])
                segment_width = x2 - x1 + 1
                center_x = (x1 + x2) / 2
                if segment_width < width * 0.45 or segment_width > width * 0.82:
                    continue
                if abs(center_x - (width / 2)) > width * 0.12:
                    continue
                matches.append((y, x1, x2))
                break

        if not matches:
            return None

        bands: list[list[tuple[int, int, int]]] = []
        current: list[tuple[int, int, int]] = []
        for row in matches:
            if not current or row[0] - current[-1][0] <= 2:
                current.append(row)
            else:
                bands.append(current)
                current = [row]
        if current:
            bands.append(current)

        best_band = max(bands, key=len)
        if len(best_band) < 18:
            return None

        top = min(row[0] for row in best_band)
        bottom = max(row[0] for row in best_band)
        left = int(sum(row[1] for row in best_band) / len(best_band))
        right = int(sum(row[2] for row in best_band) / len(best_band))

        # Expand a touch beyond the detected bright band so the click lands inside
        # the prompt body even if the text baseline or button row shifts slightly.
        return Rect(
            left=content_rect.left + max(0, left + 24),
            top=content_rect.top + max(0, top + 18),
            right=content_rect.left + min(width, right - 24),
            bottom=content_rect.top + min(height, bottom - 18),
        )

    def bring_to_front(self, hwnd: int) -> None:
        foreground = user32.GetForegroundWindow()
        current_thread = user32.GetWindowThreadProcessId(foreground, None)
        target_thread = user32.GetWindowThreadProcessId(hwnd, None)
        this_thread = kernel32.GetCurrentThreadId()

        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.AttachThreadInput(current_thread, this_thread, True)
        user32.AttachThreadInput(target_thread, this_thread, True)
        try:
            user32.SetForegroundWindow(hwnd)
            user32.SetActiveWindow(hwnd)
            user32.SetFocus(hwnd)
        finally:
            user32.AttachThreadInput(current_thread, this_thread, False)
            user32.AttachThreadInput(target_thread, this_thread, False)

    def focus_codex(self, thread_id: str = "") -> WindowInfo:
        if thread_id:
            self.open_uri(self.codex_thread_deeplink(thread_id))
            time.sleep(self.settings.deep_link_settle_ms / 1000)
        window = self.find_codex_window()
        self.bring_to_front(window.hwnd)
        time.sleep(self.settings.focus_settle_ms / 1000)
        return self.find_codex_window()

    def open_new_thread(self, project_path: str = "") -> WindowInfo:
        self.open_uri(self.codex_new_thread_deeplink(project_path))
        time.sleep(self.settings.deep_link_settle_ms / 1000)
        return self.focus_codex()

    def composer_point(self, window: WindowInfo) -> tuple[int, int]:
        content_rect = self._uia_content_rect() or Rect(window.left, window.top, window.right, window.bottom)
        composer_rect = self._detect_composer_rect(content_rect)
        if composer_rect:
            x = int(composer_rect.left + composer_rect.width / 2)
            y = int(composer_rect.top + composer_rect.height / 2)
            log.info("Composer detected via screenshot at (%s,%s) within %s", x, y, composer_rect)
            return x, y

        x = int(content_rect.left + (content_rect.width / 2))
        y = int(content_rect.bottom - self.settings.composer_bottom_offset)
        log.info("Composer fallback point at (%s,%s) within %s", x, y, content_rect)
        return x, y

    def click(self, x: int, y: int) -> None:
        if not user32.SetCursorPos(int(x), int(y)):
            raise GuiAutomationError("Failed to move cursor.")
        time.sleep(0.03)
        _send_input([_mouse_input(MOUSEEVENTF_LEFTDOWN), _mouse_input(MOUSEEVENTF_LEFTUP)])
        time.sleep(self.settings.click_settle_ms / 1000)

    def set_clipboard_text(self, text: str) -> None:
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not handle:
            raise GuiAutomationError("GlobalAlloc failed for text clipboard.")
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, encoded, len(encoded))
        kernel32.GlobalUnlock(handle)

        if not user32.OpenClipboard(None):
            raise GuiAutomationError("OpenClipboard failed.")
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, handle)
            handle = None
        finally:
            user32.CloseClipboard()

    def set_clipboard_image(self, image_path: Path) -> None:
        with Image.open(image_path) as image:
            output = io.BytesIO()
            image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise GuiAutomationError("GlobalAlloc failed for image clipboard.")
        pointer = kernel32.GlobalLock(handle)
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)

        if not user32.OpenClipboard(None):
            raise GuiAutomationError("OpenClipboard failed.")
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_DIB, handle)
            handle = None
        finally:
            user32.CloseClipboard()

    def paste(self) -> None:
        _send_input([_vk_input(VK_CONTROL), _vk_input(VK_V), _vk_input(VK_V, key_up=True), _vk_input(VK_CONTROL, key_up=True)])

    def press_enter(self) -> None:
        _send_input([_vk_input(VK_RETURN), _vk_input(VK_RETURN, key_up=True)])

    def press_shift_enter(self) -> None:
        _send_input(
            [
                _vk_input(VK_SHIFT),
                _vk_input(VK_RETURN),
                _vk_input(VK_RETURN, key_up=True),
                _vk_input(VK_SHIFT, key_up=True),
            ]
        )

    def press_escape(self) -> None:
        _send_input([_vk_input(VK_ESCAPE), _vk_input(VK_ESCAPE, key_up=True)])

    def type_text(self, text: str) -> None:
        index = 0
        while index < len(text):
            char = text[index]
            if char == "\r":
                if index + 1 < len(text) and text[index + 1] == "\n":
                    index += 1
                self.press_shift_enter()
            elif char == "\n":
                self.press_shift_enter()
            else:
                _send_input([_unicode_input(char), _unicode_input(char, key_up=True)])
            index += 1

    def paste_attachments(self, attachments: list[Path]) -> None:
        for path in attachments:
            self.set_clipboard_image(path)
            self.paste()
            time.sleep(self.settings.attachment_paste_settle_ms / 1000)

    def focus_composer(self, thread_id: str = "") -> WindowInfo:
        window = self.focus_codex(thread_id)
        x, y = self.composer_point(window)
        self.click(x, y)
        return window

    def send_message(self, text: str, attachments: list[Path], thread_id: str = "") -> None:
        self.focus_composer(thread_id)
        if attachments:
            self.paste_attachments(attachments)
            self.focus_composer(thread_id)
        if text:
            if attachments:
                self.type_text(text)
            else:
                self.set_clipboard_text(text)
                self.paste()
            time.sleep(self.settings.text_paste_settle_ms / 1000)
        self.press_enter()

    def interrupt(self, thread_id: str = "") -> None:
        self.focus_codex(thread_id)
        time.sleep(0.08)
        self.press_escape()
        time.sleep(0.12)
        self.press_escape()

    def decode_attachment_data_url(self, data_url: str) -> bytes:
        prefix, _, body = data_url.partition(",")
        if ";base64" not in prefix or not body:
            raise GuiAutomationError("Attachment data URL is invalid.")
        try:
            return base64.b64decode(body)
        except ValueError as exc:
            raise GuiAutomationError("Attachment base64 decode failed.") from exc
