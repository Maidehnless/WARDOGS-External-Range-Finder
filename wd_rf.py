"""WARDOGS map distance calculator. Run with Python 3: python wardogs_distance.py

Uses Python's built-in tkinter (included in the standard Windows installer).
On Windows, copy coordinates and press F9 for current position or F10 for
destination, even with the game focused. Click a shortcut box and press a
key combination to rebind it. Changes save automatically in
%LOCALAPPDATA%/WardogsDistance/settings.json. Escape cancels capture;
Backspace removes the bind. Restore resets a row to its default shortcut.
No extra packages or administrator rights are required by this program.
Scale: 100 metres per coordinate unit, as documented by the community tool:
https://github.com/apollyon-sys/wardogs-calculator/blob/main/docs/maps.md
Calculates horizontal straight-line distance; terrain and routes are excluded.
Bearing runs clockwise from north (0 degrees), with positive Y pointing north.
"""

import ctypes
import json
import math
import os
from pathlib import Path
import queue
import re
import sys
import threading
import tkinter as tk
from tkinter import ttk


METRES_PER_UNIT = 100.0
MAX_COORDINATE = 164.0
DEFAULT_HOTKEYS = ("F9", "F10")
NAMED_KEYS = {"SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D,
              "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
              "PAGEUP": 0x21, "PAGEDOWN": 0x22, "LEFT": 0x25, "UP": 0x26,
              "RIGHT": 0x27, "DOWN": 0x28}


def settings_path():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "WardogsDistance" / "settings.json"


def parse_hotkey(text):
    """Return canonical name, Win32 modifiers and virtual-key code."""
    parts = [part.strip().upper() for part in text.split("+")]
    aliases = {"CONTROL": "CTRL", "ESC": "ESCAPE", "RETURN": "ENTER",
               "DEL": "DELETE", "INS": "INSERT", "PGUP": "PAGEUP", "PGDN": "PAGEDOWN"}
    parts = [aliases.get(part, part) for part in parts]
    flags = {"CTRL": 2, "ALT": 1, "SHIFT": 4}
    if not parts or any(part not in flags for part in parts[:-1]):
        raise ValueError("Use a key such as F9 or Ctrl+Shift+K.")
    modifiers = parts[:-1]
    if len(set(modifiers)) != len(modifiers):
        raise ValueError("Do not repeat a modifier in a keybind.")
    key = parts[-1]
    if key in ("ESCAPE", "BACKSPACE"):
        raise ValueError("Escape cancels rebinding; Backspace removes a bind.")
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        if key == "F12":
            raise ValueError("Windows reserves F12. Choose another key.")
        virtual_key = 0x70 + int(key[1:]) - 1
    elif re.fullmatch(r"[A-Z0-9]", key):
        virtual_key = ord(key)
    elif key in NAMED_KEYS:
        virtual_key = NAMED_KEYS[key]
    else:
        raise ValueError("Use F1–F24 (except F12), a letter, number or navigation key.")
    prefix = [label for modifier, label in (("CTRL", "Ctrl"), ("ALT", "Alt"), ("SHIFT", "Shift"))
              if modifier in modifiers]
    return "+".join(prefix + [key]), sum(flags[item] for item in modifiers), virtual_key


def normalise_hotkeys(keys):
    """Keep two fixed action slots; an empty string disables that action."""
    keys = tuple(parse_hotkey(key)[0] if key.strip() else "" for key in keys)
    if len(keys) != 2 or (keys[0] and keys[0] == keys[1]):
        raise ValueError("Choose two different keybinds.")
    return keys


def captured_hotkey(event, modifiers, windows=False):
    """Translate a keyboard event without confusing shifted digits or mouse input."""
    if windows:
        code = event.keycode
        if code in (1, 2, 4, 5, 6, 0x10, 0x11, 0x12, 0x5B, 0x5C,
                    0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5):
            return None
        if 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A:
            key = chr(code)
        elif 0x70 <= code <= 0x87:
            key = f"F{code - 0x70 + 1}"
        else:
            key = next((name for name, value in NAMED_KEYS.items() if value == code), None)
            if key is None:
                raise ValueError("Choose a function key, letter, number or navigation key.")
    else:
        key = event.keysym
        if key in ("Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
                   "Meta_L", "Meta_R", "Super_L", "Super_R", "ISO_Level3_Shift"):
            return None
        key = {"Prior": "PAGEUP", "Next": "PAGEDOWN", "ISO_Left_Tab": "TAB"}.get(key, key)
    return parse_hotkey("+".join([*modifiers, key]))[0]


def replace_hotkeys(native, previous, requested):
    """Change both keys on their owning thread; restore old keys on conflict."""
    try:
        keys = normalise_hotkeys(requested)
        parsed = tuple(parse_hotkey(key) if key else None for key in keys)
    except ValueError as error:
        return False, previous, str(error)
    for identifier in range(1, len(previous) + 1):
        native.UnregisterHotKey(None, identifier)
    for identifier, item in enumerate(parsed, 1):
        if item is None:
            continue
        name, modifiers, key = item
        if not native.RegisterHotKey(None, identifier, modifiers | 0x4000, key):
            for registered in range(1, identifier):
                native.UnregisterHotKey(None, registered)
            restored = []
            for old_id, old_name in enumerate(previous, 1):
                if not old_name:
                    continue
                _, old_modifiers, old_key = parse_hotkey(old_name)
                if native.RegisterHotKey(None, old_id, old_modifiers | 0x4000, old_key):
                    restored.append(old_id)
                else:
                    break
            if len(restored) != sum(bool(key) for key in previous):
                for old_id in restored:
                    native.UnregisterHotKey(None, old_id)
                return False, ("", ""), f"{name} is unavailable; old keys could not be restored. Choose new keys."
            return False, previous, f"{name} is unavailable or already used by another app. Choose another key."
    return True, keys, ""


class WindowsHotkeys(threading.Thread):
    """Own the Windows message queue separately from Tk's event loop."""
    def __init__(self):
        super().__init__(daemon=True)
        self.commands = queue.Queue()
        self.events = queue.Queue()

    def run(self):
        active = ("", "")
        suspended = False
        native = None
        try:
            from ctypes import wintypes
            native = ctypes.WinDLL("user32", use_last_error=True)
            native.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            native.RegisterHotKey.restype = wintypes.BOOL
            native.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            native.UnregisterHotKey.restype = wintypes.BOOL
            native.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND,
                                           wintypes.UINT, wintypes.UINT, wintypes.UINT]
            native.PeekMessageW.restype = wintypes.BOOL
            message = wintypes.MSG()
            # Create and service this thread's queue; Tk never consumes these messages.
            native.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            while True:
                try:
                    command, payload = self.commands.get(timeout=0.02)
                except queue.Empty:
                    command, payload = None, None
                if command == "stop":
                    break
                if command == "capture":
                    # Registered shortcuts can consume the key before Tk sees it.
                    for identifier in (1, 2):
                        native.UnregisterHotKey(None, identifier)
                    suspended = True
                    while native.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                        pass
                    self.events.put(("capture_ready", None))
                if command == "configure":
                    success, active, detail = replace_hotkeys(native, active, payload)
                    suspended = False
                    # Discard notifications queued under the previous key mapping.
                    while native.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                        pass
                    self.events.put(("configured", (success, active, detail)))
                while native.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if not suspended and message.wParam in (1, 2) and active[int(message.wParam) - 1]:
                        self.events.put(("paste", int(message.wParam) - 1))
        except Exception as error:
            self.events.put(("error", f"Global shortcuts could not start: {error}"))
        finally:
            if native is not None:
                for identifier in range(1, len(active) + 1):
                    native.UnregisterHotKey(None, identifier)


def load_hotkeys():
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
        return normalise_hotkeys(data[name] for name in ("current", "destination"))
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return DEFAULT_HOTKEYS


def save_hotkeys(keys):
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(dict(zip(("current", "destination"), keys)), indent=2),
                         encoding="utf-8")
    temporary.replace(path)


NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
COORDINATES = re.compile(
    rf"\s*x\s*[:=]?\s*({NUMBER})\s*,\s*y\s*[:=]?\s*({NUMBER})\s*",
    re.IGNORECASE,
)
PLAIN_COORDINATES = re.compile(rf"\s*({NUMBER})\s*,\s*({NUMBER})\s*")


def parse_coordinates(text):
    """Accept x80.27, y82.27 or 80.27, 82.27, optionally in quotes."""
    text = text.strip()
    if len(text) >= 2 and (text[0], text[-1]) in (
        ('"', '"'), ("'", "'"), ("\u201c", "\u201d")
    ):
        text = text[1:-1]
    match = COORDINATES.fullmatch(text) or PLAIN_COORDINATES.fullmatch(text)
    if not match:
        raise ValueError("Enter coordinates like x80.27, y82.27.")
    coordinates = tuple(float(value) for value in match.groups())
    if any(not math.isfinite(value) or not 0 <= value <= MAX_COORDINATE
           for value in coordinates):
        raise ValueError("X and Y must each be between 0 and 164.")
    return coordinates


def distance_metres(current, destination):
    """Euclidean distance multiplied by the map's metres-per-unit scale."""
    return math.hypot(destination[0] - current[0],
                      destination[1] - current[1]) * METRES_PER_UNIT


def bearing_degrees(current, destination):
    """Clockwise bearing from north, or None when both positions coincide."""
    dx = destination[0] - current[0]
    dy = destination[1] - current[1]
    if dx == 0 and dy == 0:
        return None
    return math.degrees(math.atan2(dx, dy)) % 360.0


class DistanceApp:
    def __init__(self, root):
        self.root = root
        root.title("WARDOGS Range Finder")
        root.minsize(490, 400)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TLabel", font=("Segoe UI", 10))

        panel = ttk.Frame(root, padding=16)
        panel.grid(sticky="nsew")
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="WARDOGS Range Finder", font=("Segoe UI", 17, "bold")).grid(
            row=0, column=0, sticky="w", pady=(0, 10))

        self.current = tk.StringVar(root)
        self.destination = tk.StringVar(root)
        self.result = tk.StringVar(root, "Distance: \u2014")
        self.bearing = tk.StringVar(root, "Bearing: \u2014")
        self.equation = tk.StringVar(root)
        self.status = tk.StringVar(root)
        self.entries = []
        for row, (label, variable) in enumerate((
            ("Current position", self.current),
            ("Destination", self.destination),
        )):
            ttk.Label(panel, text=label).grid(row=1 + row * 2, column=0, sticky="w")
            entry = ttk.Entry(panel, textvariable=variable, font=("Segoe UI", 12))
            entry.grid(row=2 + row * 2, column=0, sticky="ew", pady=(3, 8), ipady=3)
            self.entries.append(entry)
            variable.trace_add("write", self.calculate)

        ttk.Label(panel, textvariable=self.result, font=("Segoe UI", 20, "bold")).grid(
            row=5, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.bearing, font=("Segoe UI", 16, "bold")).grid(
            row=6, column=0, sticky="w", pady=(2, 0))
        ttk.Label(panel, textvariable=self.equation, wraplength=450).grid(
            row=7, column=0, sticky="w", pady=(4, 0))
        self.add_message(panel, self.status, row=8, foreground="#b42318")

        keys = load_hotkeys()
        self.key_variables = [tk.StringVar(root, value) for value in keys]
        self.key_displays = [tk.StringVar(root, value or "Not assigned") for value in keys]
        self.key_entries = []
        self.key_buttons = []
        self.capture_index = None
        self.capture_ready = False
        self.config_pending = False
        self.get_key_state = None
        if sys.platform == "win32":
            self.get_key_state = ctypes.WinDLL("user32").GetKeyState
            self.get_key_state.argtypes = [ctypes.c_int]
            self.get_key_state.restype = ctypes.c_short
        self.hotkey_status = tk.StringVar(root, "Starting clipboard shortcuts…")
        self.clipboard_status = tk.StringVar(root)
        self.active_keys = ("", "")
        self.hotkeys = None
        self.poll_id = None
        self.save_pending = False
        shortcuts = ttk.LabelFrame(panel, text="Clipboard keybinds", padding=10)
        shortcuts.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        shortcuts.columnconfigure(1, weight=1)
        for row, label in enumerate(("Current position", "Destination")):
            ttk.Label(shortcuts, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            entry = ttk.Entry(shortcuts, textvariable=self.key_displays[row],
                              width=22, state="readonly", cursor="hand2")
            entry.grid(row=row, column=1, sticky="ew", pady=4)
            entry.bind("<Button-1>", lambda event, index=row: self.begin_capture(index))
            entry.bind("<Button>", lambda event: "break")
            entry.bind("<KeyPress>", lambda event, index=row: self.capture_key(event, index))
            entry.bind("<FocusOut>", lambda event, index=row: self.root.after_idle(
                lambda: self.check_capture_focus(index)))
            self.key_entries.append(entry)
            for column, (text, value) in enumerate((("Restore", DEFAULT_HOTKEYS[row]),
                                                   ("Remove", "")), 2):
                button = ttk.Button(shortcuts, text=text, width=8,
                                    command=lambda index=row, key=value: self.set_keybind(index, key))
                button.grid(row=row, column=column, padx=(6, 0), pady=4)
                self.key_buttons.append(button)
        ttk.Label(shortcuts, text="Click a box, then press a key combination.\n"
                  "Esc cancels · Backspace removes · Changes save automatically.",
                  wraplength=500).grid(
            row=2, column=0, columnspan=4, sticky="w", pady=(6, 0))
        self.add_message(panel, self.hotkey_status, row=10)
        self.add_message(panel, self.clipboard_status, row=11)
        if sys.platform == "win32":
            self.hotkeys = WindowsHotkeys()
            self.hotkeys.start()
            self.set_key_controls_pending(True)
            self.hotkeys.commands.put(("configure", keys))
            self.poll_id = root.after(50, self.poll_hotkeys)
        else:
            self.hotkey_status.set("Global clipboard shortcuts require Windows. Manual entry still works.")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.entries[0].focus_set()

    @staticmethod
    def add_message(parent, variable, row, **options):
        """Collapse unused message rows to keep the window compact."""
        label = ttk.Label(parent, textvariable=variable, wraplength=450, **options)
        label.grid(row=row, column=0, sticky="w", pady=(6, 0))

        def update_visibility(*_):
            if variable.get():
                label.grid()
            else:
                label.grid_remove()

        variable.trace_add("write", update_visibility)
        update_visibility()

    def refresh_key_displays(self):
        for index, (display, variable) in enumerate(zip(self.key_displays, self.key_variables)):
            if index == self.capture_index:
                display.set("Press a key…" if self.capture_ready else "Preparing…")
            else:
                display.set(variable.get() or "Not assigned")

    def set_key_controls_pending(self, pending):
        self.config_pending = pending
        for control in self.key_entries + self.key_buttons:
            control.state(["disabled"] if pending else ["!disabled"])

    def begin_capture(self, index):
        if self.config_pending:
            return "break"
        if self.hotkeys is not None and not self.hotkeys.is_alive():
            self.hotkey_status.set("Global shortcuts are unavailable. Restart the app to try again.")
            return "break"
        already_capturing = self.capture_index is not None
        self.capture_index = index
        if not already_capturing:
            self.capture_ready = self.hotkeys is None
            if self.hotkeys is not None:
                self.hotkeys.commands.put(("capture", None))
        self.key_entries[index].focus_set()
        self.hotkey_status.set("Press a key with optional Ctrl, Shift or Alt. Esc cancels; Backspace removes.")
        self.refresh_key_displays()
        return "break"

    def cancel_capture(self, index=None):
        if self.capture_index is None or (index is not None and index != self.capture_index):
            return "break"
        self.capture_index = None
        self.capture_ready = False
        self.refresh_key_displays()
        # Re-register the unchanged keys after leaving capture mode.
        if self.hotkeys is not None:
            self.apply_hotkeys(save=False)
        else:
            self.hotkey_status.set("")
        return "break"

    def check_capture_focus(self, index):
        # Let Restore/Remove handle their click before cancelling capture.
        if self.root.focus_get() not in self.key_entries + self.key_buttons:
            self.cancel_capture(index)

    def capture_key(self, event, index):
        if self.capture_index != index:
            if event.keysym in ("Return", "space"):
                return self.begin_capture(index)
            return "break"
        if event.keysym == "Escape":
            return self.cancel_capture(index)
        if event.keysym == "BackSpace":
            self.set_keybind(index, "")
            return "break"
        if not self.capture_ready:
            return "break"
        if self.get_key_state is not None:
            if any(self.get_key_state(code) & 0x8000 for code in (0x5B, 0x5C)):
                self.hotkey_status.set("Use Ctrl, Shift or Alt modifiers; Windows-key combinations are unsupported.")
                return "break"
            modifiers = [name for name, code in (("Ctrl", 0x11), ("Alt", 0x12), ("Shift", 0x10))
                         if self.get_key_state(code) & 0x8000]
        else:
            modifiers = [name for name, mask in (("Ctrl", 4), ("Alt", 8), ("Shift", 1))
                         if event.state & mask]
        try:
            key = captured_hotkey(event, modifiers, windows=self.get_key_state is not None)
        except ValueError as error:
            self.hotkey_status.set(str(error))
            return "break"
        if key is not None:
            self.set_keybind(index, key)
        return "break"

    def set_keybind(self, index, key):
        if self.config_pending:
            return
        keys = [variable.get() for variable in self.key_variables]
        keys[index] = key
        try:
            keys = normalise_hotkeys(keys)
        except ValueError as error:
            self.hotkey_status.set(str(error))
            return
        self.capture_index = None
        self.capture_ready = False
        for variable, value in zip(self.key_variables, keys):
            variable.set(value)
        self.refresh_key_displays()
        self.apply_hotkeys()

    def apply_hotkeys(self, save=True):
        keys = normalise_hotkeys(variable.get() for variable in self.key_variables)
        if self.hotkeys is None:
            try:
                if save:
                    save_hotkeys(keys)
                self.hotkey_status.set("Settings saved. Global clipboard shortcuts require Windows.")
            except OSError:
                self.hotkey_status.set("Settings could not be saved.")
            return
        if not self.hotkeys.is_alive():
            self.hotkey_status.set("Global shortcuts are unavailable. Restart the app to try again.")
            return
        self.save_pending = save
        self.set_key_controls_pending(True)
        self.hotkeys.commands.put(("configure", keys))

    def poll_hotkeys(self):
        try:
            while True:
                event, payload = self.hotkeys.events.get_nowait()
                if event == "paste":
                    if self.capture_index is None and not self.config_pending:
                        self.paste_clipboard(payload)
                elif event == "capture_ready":
                    if self.capture_index is not None:
                        self.capture_ready = True
                        self.refresh_key_displays()
                elif event == "configured":
                    success, self.active_keys, detail = payload
                    self.set_key_controls_pending(False)
                    for variable, key in zip(self.key_variables, self.active_keys):
                        variable.set(key)
                    self.refresh_key_displays()
                    if success:
                        if self.save_pending:
                            try:
                                save_hotkeys(self.active_keys)
                            except OSError:
                                detail = "Keys work this session, but settings could not be saved."
                    self.save_pending = False
                    if not any(self.active_keys):
                        detail = f"{detail} No clipboard shortcuts are active.".strip()
                    self.hotkey_status.set(detail)
                elif event == "error":
                    self.active_keys = ("", "")
                    self.capture_index = None
                    self.capture_ready = False
                    self.set_key_controls_pending(False)
                    self.refresh_key_displays()
                    self.hotkey_status.set(payload)
        except queue.Empty:
            pass
        self.poll_id = self.root.after(50, self.poll_hotkeys)

    def paste_clipboard(self, index):
        label = ("Current position", "Destination")[index]
        try:
            text = self.root.clipboard_get().strip()
        except tk.TclError:
            self.clipboard_status.set("Clipboard text is unavailable. Copy coordinates and try again.")
            return
        try:
            parse_coordinates(text)
        except ValueError as error:
            self.clipboard_status.set(f"{label} unchanged: {error}")
            return
        (self.current, self.destination)[index].set(text)
        self.clipboard_status.set("Copies current coordinates from clipboard")

    def close(self):
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
        if self.hotkeys is not None:
            self.hotkeys.commands.put(("stop", None))
            self.hotkeys.join(timeout=0.5)
        self.root.destroy()

    def clear_result(self, *_):
        # Do not leave an old result visible after either position changes.
        self.result.set("Distance: \u2014")
        self.bearing.set("Bearing: \u2014")
        self.equation.set("")
        self.status.set("")

    def calculate(self, *_):
        self.clear_result()
        if not self.current.get().strip() or not self.destination.get().strip():
            return
        points = []
        for label, variable in (
            ("Current position", self.current), ("Destination", self.destination)
        ):
            try:
                points.append(parse_coordinates(variable.get()))
            except ValueError as error:
                self.status.set(f"{label}: {error}")
                return
        current, destination = points
        distance = distance_metres(current, destination)
        self.result.set(f"{distance:,.2f} metres")
        bearing = bearing_degrees(current, destination)
        if bearing is None:
            self.bearing.set("Bearing: \u2014 (same position)")
        else:
            # Keep a rounded value near north from displaying as 360 degrees.
            self.bearing.set(f"{round(bearing, 2) % 360:.2f}\u00b0")
        dx = destination[0] - current[0]
        dy = destination[1] - current[1]
        self.equation.set(f"\u221a[({dx:.6g})\u00b2 + ({dy:.6g})\u00b2] \u00d7 100 = {distance:,.2f} m")


def main():
    root = tk.Tk()
    DistanceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
