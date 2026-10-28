"""Win32 bits via ctypes (Windows only): global hotkeys, no-activate window, foreground monitor."""

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter

from .config import parse_hotkey

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.MonitorFromWindow.restype = wintypes.HMONITOR
user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]

WM_HOTKEY = 0x0312
MOD_NOREPEAT = 0x4000
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONEAREST = 2


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]


def no_activate(hwnd: int):
    """Clicks on the window never take focus."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)


def foreground_monitor() -> tuple[str, tuple[int, int]] | None:
    """(device name, native top-left) of the active window's monitor."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    mon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    info = MONITORINFOEXW(cbSize=ctypes.sizeof(MONITORINFOEXW))
    if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
        return None
    return info.szDevice, (info.rcMonitor.left, info.rcMonitor.top)


class Hotkeys(QAbstractNativeEventFilter):
    """Global hotkeys posted to `hwnd`; on_command(name) when one fires."""

    def __init__(self, hwnd: int, on_command):
        super().__init__()
        self.hwnd, self.on_command = hwnd, on_command
        self.ids: dict[int, str] = {}

    def register(self, keys: dict[str, str]):
        """keys: command -> "ctrl+alt+t". Re-registers everything (used on reload)."""
        for i in self.ids:
            user32.UnregisterHotKey(self.hwnd, i)
        self.ids = {}
        for i, (cmd, key) in enumerate(keys.items(), 1):
            mods, vk = parse_hotkey(key)  # config already validated it
            if user32.RegisterHotKey(self.hwnd, i, mods | MOD_NOREPEAT, vk):
                self.ids[i] = cmd
            else:
                print(f"taskviewer-board: hotkey {key} for {cmd} is taken "
                      f"(error {ctypes.get_last_error()})", flush=True)

    def nativeEventFilter(self, event_type, message):
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == WM_HOTKEY and msg.wParam in self.ids:
            self.on_command(self.ids[msg.wParam])
            return True, 0
        return False, 0
