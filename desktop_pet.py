"""An original animated cat in a non-activating, click-through Win32 overlay."""

import ctypes as c
import logging
import time
import tkinter as tk
from ctypes import wintypes as w

from win_input import bind, user32


PET_MODES = ("Follow cursor", "While dictating", "Off")
WIDTH, HEIGHT = 68, 62
TRANSPARENT = "#ff00ff"
INK = "#38251e"
GINGER = "#eaa062"
CREAM = "#fff1d5"
PINK = "#ed9b8b"
ACTIVE = {"opening", "listening", "thinking"}

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010
SWP_NOSIZE = 0x0001
HWND_TOPMOST = -1

get_cursor = bind(user32, "GetCursorPos", w.BOOL, c.POINTER(w.POINT))
monitor_at = bind(user32, "MonitorFromPoint", w.HMONITOR, w.POINT, w.DWORD)
get_ancestor = bind(user32, "GetAncestor", w.HWND, w.HWND, w.UINT)
get_style = bind(user32, "GetWindowLongW", w.LONG, w.HWND, c.c_int)
set_style = bind(user32, "SetWindowLongW", w.LONG, w.HWND, c.c_int, w.LONG)
show_window = bind(user32, "ShowWindow", w.BOOL, w.HWND, c.c_int)
move_window = bind(user32, "SetWindowPos", w.BOOL, w.HWND, w.HWND,
                   c.c_int, c.c_int, c.c_int, c.c_int, w.UINT)
system_parameters = bind(user32, "SystemParametersInfoW", w.BOOL,
                         w.UINT, w.UINT, w.LPVOID, w.UINT)


class MonitorInfo(c.Structure):
    _fields_ = [("size", w.DWORD), ("screen", w.RECT), ("work", w.RECT), ("flags", w.DWORD)]


get_monitor_info = bind(user32, "GetMonitorInfoW", w.BOOL, w.HMONITOR, c.POINTER(MonitorInfo))


def animations_enabled():
    animate = w.BOOL()
    return bool(system_parameters(0x1042, 0, c.byref(animate), 0) and animate.value)


def nearby_position(point, area):
    """Leave a clear gap around the actual pointer and stay inside the work area."""
    x, y = point
    left, top, right, bottom = area
    gap = 18
    x = x + gap if x + gap + WIDTH <= right else x - gap - WIDTH
    y = y + gap if y + gap + HEIGHT <= bottom else y - gap - HEIGHT
    return max(left, min(x, right - WIDTH)), max(top, min(y, bottom - HEIGHT))


class Cat(tk.Canvas):
    def __init__(self, parent, background):
        super().__init__(parent, width=WIDTH, height=HEIGHT, bg=background,
                         highlightthickness=0, borderwidth=0, takefocus=False)
        self.frame = None

    def draw(self, state="idle", blink=False, step=0):
        frame = (state, blink, step)
        if self.frame == frame:
            return
        self.frame = frame
        self.delete("all")

        self.create_line(40, 48, 52, 49, 59, 40, 57, 35, fill=INK, width=8,
                         smooth=True, capstyle="round")
        self.create_line(40, 48, 52, 49, 59, 40, 57, 35, fill=GINGER, width=4,
                         smooth=True, capstyle="round")
        self.create_oval(14, 29, 48, 56, fill=GINGER, outline=INK, width=2)
        self.create_oval(23, 35, 40, 54, fill=CREAM, outline="")
        self.create_oval(15, 48, 29, 58, fill=CREAM, outline=INK, width=2)
        self.create_oval(35, 48, 48, 58, fill=CREAM, outline=INK, width=2)

        self.create_polygon(10, 26, 10, 10, 12, 8, 24, 15, 34, 15, 45, 8,
                            48, 9, 49, 26, 47, 33, 42, 38, 37, 40, 21, 40,
                            15, 37, 11, 32, fill=GINGER, outline=INK, width=2, joinstyle="round")
        self.create_polygon(13, 12, 20, 17, 14, 20, fill=PINK, outline="")
        self.create_polygon(44, 12, 45, 20, 38, 17, fill=PINK, outline="")
        self.create_line(26, 17, 27, 21, fill="#b46742", width=2, capstyle="round")
        self.create_line(32, 17, 31, 21, fill="#b46742", width=2, capstyle="round")
        self.create_oval(21, 27, 37, 38, fill=CREAM, outline="")
        self.create_oval(14, 29, 20, 33, fill=PINK, outline="")
        self.create_oval(38, 29, 44, 33, fill=PINK, outline="")
        for x in (21, 37):
            if blink or state == "done":
                self.create_arc(x-3, 24, x+3, 30, start=20, extent=140, style="arc",
                                outline=INK, width=2)
            elif state == "thinking":
                self.create_oval(x-1, 23, x+3, 27, fill=INK, outline="")
            else:
                self.create_oval(x-2, 23, x+2, 29, fill=INK, outline="")
        self.create_polygon(26, 29, 32, 29, 29, 32, fill=INK, outline="")
        if state == "listening":
            self.create_oval(26, 33, 32, 37, fill=INK, outline="")
        else:
            self.create_line(25, 33, 27, 35, 29, 33, 31, 35, 33, 33,
                             fill=INK, width=1, smooth=True)
        self.draw_cue(state, step)

    def draw_cue(self, state, step):
        if state in ("opening", "listening"):
            self.create_oval(45, 2, 67, 24, fill="#a53627", outline=CREAM, width=2)
            heights = ((4, 9, 5), (7, 5, 10), (4, 11, 7))[step % 3]
            for x, height in zip((51, 56, 61), heights):
                self.create_line(x, 13-height/2, x, 13+height/2, fill="white", width=2,
                                 capstyle="round")
        elif state == "thinking":
            self.create_oval(45, 2, 67, 24, fill="#68457c", outline=CREAM, width=2)
            for index, x in enumerate((51, 56, 61)):
                radius = 1.5 if step == index else 1
                self.create_oval(x-radius, 13-radius, x+radius, 13+radius,
                                 fill="white", outline="")
        elif state == "done":
            self.create_oval(45, 2, 67, 24, fill="#216655", outline=CREAM, width=2)
            self.create_line(51, 13, 55, 16, 61, 9, fill="white", width=2, joinstyle="round")
        elif state == "error":
            self.create_oval(45, 2, 67, 24, fill="#a53627", outline=CREAM, width=2)
            self.create_line(56, 8, 56, 14, fill="white", width=2, capstyle="round")
            self.create_oval(55, 16, 57, 18, fill="white", outline="")


class CursorPet:
    def __init__(self, root, preview, animate):
        self.root = root
        self.preview = preview
        self.animate = animate
        self.mode = "Off"
        self.state = "loading"
        self.state_at = time.monotonic()
        self.window = None
        self.job = None
        self.visible = False
        self.position = None
        self.monitor = None
        self.preview.draw()

    def create_overlay(self):
        window = tk.Toplevel(self.root)
        window.title("Pantenee · Cursor cat")
        window.overrideredirect(True)
        window.attributes("-transparentcolor", TRANSPARENT)
        window.geometry(f"{WIDTH}x{HEIGHT}+0+0")
        self.cat = Cat(window, TRANSPARENT)
        self.cat.pack()
        window.update_idletasks()
        self.hwnd = get_ancestor(window.winfo_id(), 2)  # GA_ROOT, the Win32 wrapper around the Tk canvas
        flags = WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if not self.hwnd:
            window.destroy()
            raise c.WinError(c.get_last_error())
        c.set_last_error(0)
        previous = set_style(self.hwnd, GWL_EXSTYLE, get_style(self.hwnd, GWL_EXSTYLE) | flags)
        if not previous and c.get_last_error():
            error = c.get_last_error()
            window.destroy()
            raise c.WinError(error)
        show_window(self.hwnd, 0)  # SW_HIDE. Subsequent shows use SWP_NOACTIVATE.
        self.window = window

    def set_mode(self, mode):
        self.mode = mode
        if mode != "Off" and self.window is None:
            try:
                self.create_overlay()
            except (OSError, tk.TclError):
                logging.exception("Could not start the desktop pet")
                self.mode = "Off"
        self.schedule(0)

    def set_state(self, state):
        self.state = state
        self.state_at = time.monotonic()
        self.schedule(0)

    def schedule(self, delay):
        if self.job is not None:
            self.root.after_cancel(self.job)
        self.job = self.root.after(delay, self.tick)

    def tick(self):
        self.job = None
        now = time.monotonic()
        elapsed = now - self.state_at
        state = self.state
        flash = state in ("done", "error") and elapsed < 1.0
        if state in ("done", "error") and not flash:
            state = "idle"
        blink = self.animate and state == "idle" and now % 4.4 < 0.15
        step = int(elapsed * 4) % 3 if self.animate and state in ("listening", "thinking") else 0
        self.preview.draw(state, blink, step)

        show = self.mode == "Follow cursor" or (
            self.mode == "While dictating" and (state in ACTIVE or flash))
        if show:
            self.cat.draw(state, blink, step)
            self.follow_pointer()
            self.schedule(34 if self.animate else 50)
        else:
            if self.visible:
                show_window(self.hwnd, 0)
                self.visible = False
                self.position = None
            if flash or (self.animate and self.root.state() == "normal"):
                self.schedule(80)

    def follow_pointer(self):
        # Keep the pet anchored for reduced-motion users in dictation-only mode.
        if self.visible and not self.animate and self.mode == "While dictating":
            return
        point = w.POINT()
        if not get_cursor(c.byref(point)):
            return
        monitor = monitor_at(point, 2)  # MONITOR_DEFAULTTONEAREST
        info = MonitorInfo(size=c.sizeof(MonitorInfo))
        if not get_monitor_info(monitor, c.byref(info)):
            return
        area = info.work
        target = nearby_position((point.x, point.y), (area.left, area.top, area.right, area.bottom))
        position = target
        if self.animate and self.position and monitor == self.monitor:
            position = tuple(old + round((new - old) * 0.38) if abs(new - old) > 2 else new
                             for old, new in zip(self.position, target))
            if (position[0] <= point.x < position[0] + WIDTH
                    and position[1] <= point.y < position[1] + HEIGHT):
                position = target
        if not self.visible or position != self.position:
            flags = SWP_NOACTIVATE | SWP_NOSIZE | SWP_SHOWWINDOW
            if move_window(self.hwnd, HWND_TOPMOST, *position, 0, 0, flags):
                self.position = position
                self.monitor = monitor
                self.visible = True
