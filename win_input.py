"""Windows global push-to-talk keys and Unicode text input."""

import ctypes as c
import logging
import struct
import threading
import time
from ctypes import wintypes as w


HOTKEYS = {"Left Ctrl": 0xA2, "Right Ctrl": 0xA3, "F8": 0x77, "F9": 0x78,
           "F10": 0x79, "F11": 0x7A}
MODIFIERS = (0x10, 0x11, 0x12, 0x5B, 0x5C)  # Shift, Ctrl, Alt and both Windows keys
MOUSE_CHORDS = (0x201, 0x204, 0x207, 0x20A, 0x20B, 0x20E)

user32 = c.WinDLL("user32", use_last_error=True)
kernel32 = c.WinDLL("kernel32", use_last_error=True)
UIntPtr = c.c_size_t
HookProc = c.WINFUNCTYPE(c.c_ssize_t, c.c_int, w.WPARAM, w.LPARAM)


class KeyboardEvent(c.Structure):
    _fields_ = [("key", w.DWORD), ("scan", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", UIntPtr)]


class GuiThread(c.Structure):
    _fields_ = [("size", w.DWORD), ("flags", w.DWORD), ("active", w.HWND),
                ("focus", w.HWND), ("capture", w.HWND), ("menu", w.HWND),
                ("move_size", w.HWND), ("caret", w.HWND), ("caret_rect", w.RECT)]


class KeyInput(c.Structure):
    _fields_ = [("key", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", UIntPtr)]


class MouseInput(c.Structure):
    _fields_ = [("x", w.LONG), ("y", w.LONG), ("data", w.DWORD),
                ("flags", w.DWORD), ("time", w.DWORD), ("extra", UIntPtr)]


class InputData(c.Union):
    # SendInput requires the full Windows INPUT size, even for keyboard events.
    _fields_ = [("key", KeyInput), ("mouse", MouseInput)]


class Input(c.Structure):
    _fields_ = [("kind", w.DWORD), ("data", InputData)]


def bind(dll, name, result, *arguments):
    function = getattr(dll, name)
    function.restype = result
    function.argtypes = arguments
    return function


set_hook = bind(user32, "SetWindowsHookExW", w.HANDLE, c.c_int, HookProc, w.HANDLE, w.DWORD)
next_hook = bind(user32, "CallNextHookEx", c.c_ssize_t, w.HANDLE, c.c_int, w.WPARAM, w.LPARAM)
remove_hook = bind(user32, "UnhookWindowsHookEx", w.BOOL, w.HANDLE)
get_message = bind(user32, "GetMessageW", w.BOOL, c.POINTER(w.MSG), w.HWND, w.UINT, w.UINT)
peek_message = bind(user32, "PeekMessageW", w.BOOL, c.POINTER(w.MSG), w.HWND,
                    w.UINT, w.UINT, w.UINT)
post_message = bind(user32, "PostThreadMessageW", w.BOOL, w.DWORD, w.UINT, w.WPARAM, w.LPARAM)
foreground = bind(user32, "GetForegroundWindow", w.HWND)
gui_thread = bind(user32, "GetGUIThreadInfo", w.BOOL, w.DWORD, c.POINTER(GuiThread))
key_state = bind(user32, "GetAsyncKeyState", w.SHORT, c.c_int)
send_input = bind(user32, "SendInput", w.UINT, w.UINT, c.POINTER(Input), c.c_int)
module_handle = bind(kernel32, "GetModuleHandleW", w.HANDLE, w.LPCWSTR)
thread_id = bind(kernel32, "GetCurrentThreadId", w.DWORD)
create_mutex = bind(kernel32, "CreateMutexW", w.HANDLE, w.LPVOID, w.BOOL, w.LPCWSTR)
close_handle = bind(kernel32, "CloseHandle", w.BOOL, w.HANDLE)


def focused_target():
    window = foreground()
    if not window:
        return None
    info = GuiThread(size=c.sizeof(GuiThread))
    if gui_thread(0, c.byref(info)) and info.active == window:
        return window, info.focus
    return None


def insert_text(text, target, press_enter=False):
    """Return False when the original target is unavailable or input is blocked."""
    strokes = [KeyInput(scan=unit, flags=flags)
               for (unit,) in struct.iter_unpack("<H", text.encode("utf-16-le"))
               for flags in (0x04, 0x06)]  # KEYEVENTF_UNICODE, then key up
    if press_enter:
        strokes.extend((KeyInput(key=0x0D), KeyInput(key=0x0D, flags=0x02)))
    events = (Input * len(strokes))(*(Input(1, InputData(key=stroke)) for stroke in strokes))
    if any(key_state(key) < 0 for key in MODIFIERS):
        return False
    if target is None or focused_target() != target:
        return False
    return send_input(len(events), events, c.sizeof(Input)) == len(events)


class HoldKey:
    """Track a single hold and cancel it on keyboard or mouse shortcuts."""

    def __init__(self, events, key):
        self.events = events
        self.key = key
        self.enabled = False
        self.pressed = set()
        self.trigger = None
        self.suppressed = None
        self.thread = threading.Thread(target=self._run, daemon=True, name="Hotkey")
        self.thread_id = None
        self.closing = threading.Event()

    def start(self):
        self.thread.start()

    def close(self):
        self.closing.set()
        if self.thread_id is not None:
            post_message(self.thread_id, 0x12, 0, 0)  # WM_QUIT
        self.thread.join(timeout=0.25)

    def cancel(self):
        if self.trigger is not None:
            self.trigger = None
            self.events.put(("cancel", None))

    def keyboard_event(self, key, down):
        swallow = key == self.suppressed
        if down:
            if key in self.pressed:
                return swallow
            if self.trigger is not None:
                self.cancel()
            elif self.enabled and key == self.key and not self.pressed:
                self.trigger = key
                if key not in (HOTKEYS["Left Ctrl"], HOTKEYS["Right Ctrl"]):
                    self.suppressed = key
                    swallow = True
                self.events.put(("hold", (time.monotonic(), focused_target())))
            self.pressed.add(key)
        else:
            self.pressed.discard(key)
            if key == self.trigger:
                self.trigger = None
                self.events.put(("release", (time.monotonic(), focused_target())))
            if swallow:
                self.suppressed = None
        return swallow

    def _keyboard_hook(self, code, message, address):
        if code == 0:
            event = c.cast(address, c.POINTER(KeyboardEvent)).contents
            if not event.flags & 0x10:  # LLKHF_INJECTED
                down = message in (0x100, 0x104)  # WM_KEYDOWN, WM_SYSKEYDOWN
                if self.keyboard_event(event.key, down):
                    return 1
        return next_hook(None, code, message, address)

    def _mouse_hook(self, code, message, address):
        if code == 0 and message in MOUSE_CHORDS:
            self.cancel()
        return next_hook(None, code, message, address)

    def _run(self):
        keyboard = HookProc(self._keyboard_hook)
        mouse = HookProc(self._mouse_hook)
        keyboard_handle = mouse_handle = None
        try:
            message = w.MSG()
            peek_message(c.byref(message), None, 0, 0, 0)
            self.thread_id = thread_id()
            if self.closing.is_set():
                return
            self.pressed = {key for key in range(8, 255)
                            if key not in (0x10, 0x11, 0x12) and key_state(key) < 0}
            instance = module_handle(None)
            keyboard_handle = set_hook(13, keyboard, instance, 0)  # WH_KEYBOARD_LL
            if not keyboard_handle:
                raise c.WinError(c.get_last_error())
            mouse_handle = set_hook(14, mouse, instance, 0)  # WH_MOUSE_LL
            if not mouse_handle:
                raise c.WinError(c.get_last_error())
            self.events.put(("hotkey_ready", None))
            while (result := get_message(c.byref(message), None, 0, 0)) > 0:
                pass
            if result < 0:
                raise c.WinError(c.get_last_error())
        except OSError:
            logging.exception("Windows hotkey setup failed")
            self.events.put(("hotkey_error", None))
        finally:
            if mouse_handle:
                remove_hook(mouse_handle)
            if keyboard_handle:
                remove_hook(keyboard_handle)
