"""WARDOGS map distance calculator. Run with Python 3: python wardogs_distance.py

Uses Python's built-in tkinter (included in the standard Windows installer).
On Windows, copy coordinates and press F9 for current position or F10 for
destination, even with the game focused. Edit shortcuts and click Apply
keybinds to save them in %LOCALAPPDATA%/WardogsDistance/settings.json.
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
    named = {"SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESCAPE": 0x1B,
             "INSERT": 0x2D, "DELETE": 0x2E, "HOME": 0x24, "END": 0x23,
             "PAGEUP": 0x21, "PAGEDOWN": 0x22, "LEFT": 0x25, "UP": 0x26,
             "RIGHT": 0x27, "DOWN": 0x28, "BACKSPACE": 0x08}
    if re.fullmatch(r"F(?:[1-9]|1[0-9]|2[0-4])", key):
        if key == "F12":
            raise ValueError("Windows reserves F12. Choose another key.")
        virtual_key = 0x70 + int(key[1:]) - 1
    elif re.fullmatch(r"[A-Z0-9]", key):
        virtual_key = ord(key)
    elif key in named:
        virtual_key = named[key]
    else:
        raise ValueError("Use F1–F24 (except F12), a letter, number or navigation key.")
    prefix = [label for modifier, label in (("CTRL", "Ctrl"), ("ALT", "Alt"), ("SHIFT", "Shift"))
              if modifier in modifiers]
    return "+".join(prefix + [key]), sum(flags[item] for item in modifiers), virtual_key


def replace_hotkeys(native, previous, requested):
    """Change both keys on their owning thread; restore old keys on conflict."""
    try:
        parsed = tuple(parse_hotkey(key) for key in requested)
        if len(parsed) != 2 or parsed[0][1:] == parsed[1][1:]:
            raise ValueError("Choose two different keybinds.")
    except ValueError as error:
        return False, previous, str(error)
    for identifier in range(1, len(previous) + 1):
        native.UnregisterHotKey(None, identifier)
    for identifier, (name, modifiers, key) in enumerate(parsed, 1):
        if not native.RegisterHotKey(None, identifier, modifiers | 0x4000, key):
            for registered in range(1, identifier):
                native.UnregisterHotKey(None, registered)
            restored = []
            for old_id, old_name in enumerate(previous, 1):
                _, old_modifiers, old_key = parse_hotkey(old_name)
                if native.RegisterHotKey(None, old_id, old_modifiers | 0x4000, old_key):
                    restored.append(old_name)
                else:
                    break
            if len(restored) != len(previous):
                for old_id in range(1, len(restored) + 1):
                    native.UnregisterHotKey(None, old_id)
                return False, (), f"{name} is unavailable; old keys could not be restored. Choose new keys."
            return False, previous, f"{name} is unavailable or already used by another app. Choose another key."
    return True, tuple(item[0] for item in parsed), ""


class WindowsHotkeys(threading.Thread):
    """Own the Windows message queue separately from Tk's event loop."""
    def __init__(self):
        super().__init__(daemon=True)
        self.commands = queue.Queue()
        self.events = queue.Queue()

    def run(self):
        active = ()
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
                if command == "configure":
                    success, active, detail = replace_hotkeys(native, active, payload)
                    # Discard notifications queued under the previous key mapping.
                    while native.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                        pass
                    self.events.put(("configured", (success, active, detail)))
                while native.PeekMessageW(ctypes.byref(message), None, 0x0312, 0x0312, 1):
                    if message.wParam in (1, 2):
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
        keys = tuple(parse_hotkey(data[name])[0] for name in ("current", "destination"))
        if keys[0] == keys[1]:
            raise ValueError("Duplicate shortcuts")
        return keys
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
        self.hotkey_status = tk.StringVar(root, "Starting clipboard shortcuts…")
        self.clipboard_status = tk.StringVar(root)
        self.active_keys = ()
        self.hotkeys = None
        self.poll_id = None
        self.save_pending = False
        shortcuts = ttk.LabelFrame(panel, text="Clipboard keybinds", padding=10)
        shortcuts.grid(row=9, column=0, sticky="ew", pady=(10, 0))
        shortcuts.columnconfigure(1, weight=1)
        for row, label in enumerate(("Current position", "Destination")):
            ttk.Label(shortcuts, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=4)
            ttk.Entry(shortcuts, textvariable=self.key_variables[row], width=20).grid(
                row=row, column=1, sticky="ew", pady=4)
        ttk.Label(shortcuts, text="Paste coordinates in game.").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(6, 8))
        self.apply_button = ttk.Button(shortcuts, text="Apply keybinds", command=self.apply_hotkeys)
        self.apply_button.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.add_message(panel, self.hotkey_status, row=10)
        self.add_message(panel, self.clipboard_status, row=11)
        if sys.platform == "win32":
            self.hotkeys = WindowsHotkeys()
            self.hotkeys.start()
            self.apply_button.state(["disabled"])
            self.hotkeys.commands.put(("configure", keys))
            self.poll_id = root.after(50, self.poll_hotkeys)
        else:
            self.apply_button.state(["disabled"])
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

    def apply_hotkeys(self):
        if self.hotkeys is None or not self.hotkeys.is_alive():
            self.hotkey_status.set("Global shortcuts are unavailable. Restart the app to try again.")
            return
        try:
            keys = tuple(parse_hotkey(variable.get())[0] for variable in self.key_variables)
            if keys[0] == keys[1]:
                raise ValueError("Choose two different keybinds.")
        except ValueError as error:
            self.hotkey_status.set(str(error))
            return
        self.save_pending = True
        self.apply_button.state(["disabled"])
        self.hotkeys.commands.put(("configure", keys))

    def poll_hotkeys(self):
        try:
            while True:
                event, payload = self.hotkeys.events.get_nowait()
                if event == "paste":
                    self.paste_clipboard(payload)
                elif event == "configured":
                    success, self.active_keys, detail = payload
                    self.apply_button.state(["!disabled"])
                    if success:
                        for variable, key in zip(self.key_variables, self.active_keys):
                            variable.set(key)
                        if self.save_pending:
                            try:
                                save_hotkeys(self.active_keys)
                            except OSError:
                                detail = "Keys work this session, but settings could not be saved."
                    self.save_pending = False
                    if not self.active_keys:
                        detail = f"{detail} No clipboard shortcuts are active.".strip()
                    self.hotkey_status.set(detail)
                elif event == "error":
                    self.active_keys = ()
                    self.apply_button.state(["disabled"])
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
