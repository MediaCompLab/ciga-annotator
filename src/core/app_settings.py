import json
import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt

def get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent.parent.parent

SETTINGS_FILE = str(get_base_dir() / "settings.json")

DEFAULT_SETTINGS = {
    "auto_pause": True,
    "inherit_listener": False,
    "inherit_target": False,
    "only_uncoded": False,
    "hotkeys": {
        "play_pause": "Space",
        "next_uncoded": "N",
        "prev_subtitle": "Up",
        "next_subtitle": "Down",
        "seek_back": "Left",
        "seek_forward": "Right",
        "role_speakers": "Ctrl+1",
        "role_listeners": "Ctrl+2",
        "role_targets": "Ctrl+3",
        "cycle_role": "Ctrl+Q",
        "focus_search": "Ctrl+F",
        "shortcuts_help": "F1"
    }
}

class AppSettings:
    def __init__(self):
        self.settings = DEFAULT_SETTINGS.copy()
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge loaded into default to preserve missing keys
                    self.settings.update(loaded)
                    if "hotkeys" in loaded:
                        for k, v in loaded["hotkeys"].items():
                            self.settings["hotkeys"][k] = v
            except Exception as e:
                print(f"Failed to load settings: {e}")

    def save(self):
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

    def get_hotkey(self, action_name):
        return self.settings.get("hotkeys", {}).get(action_name, "")
        
    def set_hotkey(self, action_name, key_sequence):
        if "hotkeys" not in self.settings:
            self.settings["hotkeys"] = {}
        self.settings["hotkeys"][action_name] = key_sequence
        self.save()

