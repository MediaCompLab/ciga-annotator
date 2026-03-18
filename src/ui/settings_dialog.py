from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLabel, 
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem, QHeaderView, QKeySequenceEdit
)
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt

class SettingsDialog(QDialog):
    def __init__(self, parent, app_settings):
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.resize(500, 400)
        self.app_settings = app_settings
        
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # General Tab
        self.general_tab = QWidget()
        self.setup_general_tab()
        self.tabs.addTab(self.general_tab, "General")
        
        # Hotkeys Tab
        self.hotkeys_tab = QWidget()
        self.setup_hotkeys_tab()
        self.tabs.addTab(self.hotkeys_tab, "Hotkeys")
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self.reset_to_default)
        
        btn_layout.addWidget(reset_btn)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        
        layout.addLayout(btn_layout)

    def setup_general_tab(self):
        layout = QVBoxLayout(self.general_tab)
        
        self.cb_auto_pause = QCheckBox("Auto-pause at the end of dialog")
        self.cb_auto_pause.setChecked(self.app_settings.get("auto_pause", True))
        
        self.cb_inherit_listener = QCheckBox("Inherit Listener from previous line")
        self.cb_inherit_listener.setChecked(self.app_settings.get("inherit_listener", False))
        
        self.cb_inherit_target = QCheckBox("Inherit Target from previous line")
        self.cb_inherit_target.setChecked(self.app_settings.get("inherit_target", False))
        
        self.cb_only_uncoded = QCheckBox("Only show uncoded")
        self.cb_only_uncoded.setChecked(self.app_settings.get("only_uncoded", False))
        
        layout.addWidget(self.cb_auto_pause)
        layout.addWidget(self.cb_inherit_listener)
        layout.addWidget(self.cb_inherit_target)
        layout.addWidget(self.cb_only_uncoded)
        layout.addStretch()

    def setup_hotkeys_tab(self):
        layout = QVBoxLayout(self.hotkeys_tab)
        
        self.hotkeys_table = QTableWidget()
        self.hotkeys_table.setColumnCount(2)
        self.hotkeys_table.setHorizontalHeaderLabels(["Action", "Shortcut"])
        self.hotkeys_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.hotkeys_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        self.actions_map = {
            "play_pause": "Play / Pause",
            "next_uncoded": "Next Uncoded Line",
            "prev_subtitle": "Previous Subtitle",
            "next_subtitle": "Next Subtitle",
            "seek_back": "Seek Back",
            "seek_forward": "Seek Forward",
            "role_speakers": "Select Speakers Role",
            "role_listeners": "Select Listeners Role",
            "role_targets": "Select Targets Role",
            "cycle_role": "Cycle Roles",
            "focus_search": "Focus Search",
            "shortcuts_help": "Show Shortcuts Help"
        }
        
        self.shortcut_edits = {}
        self.populate_hotkeys_table()
        
        layout.addWidget(QLabel("Click on a shortcut box and press new key combination:"))
        layout.addWidget(self.hotkeys_table)
        
    def populate_hotkeys_table(self):
        self.hotkeys_table.setRowCount(len(self.actions_map))
        
        row = 0
        for code, name in self.actions_map.items():
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.hotkeys_table.setItem(row, 0, name_item)
            
            key_edit = QKeySequenceEdit()
            current_key = self.app_settings.get_hotkey(code)
            if current_key:
                key_edit.setKeySequence(QKeySequence(current_key))
                
            self.hotkeys_table.setCellWidget(row, 1, key_edit)
            self.shortcut_edits[code] = key_edit
            
            row += 1

    def save_settings(self):
        self.app_settings.set("auto_pause", self.cb_auto_pause.isChecked())
        self.app_settings.set("inherit_listener", self.cb_inherit_listener.isChecked())
        self.app_settings.set("inherit_target", self.cb_inherit_target.isChecked())
        self.app_settings.set("only_uncoded", self.cb_only_uncoded.isChecked())
        
        for code, edit in self.shortcut_edits.items():
            seq = edit.keySequence()
            self.app_settings.set_hotkey(code, seq.toString())
            
        self.accept()
        
    def reset_to_default(self):
        from src.core.app_settings import DEFAULT_SETTINGS
        self.cb_auto_pause.setChecked(DEFAULT_SETTINGS["auto_pause"])
        self.cb_inherit_listener.setChecked(DEFAULT_SETTINGS["inherit_listener"])
        self.cb_inherit_target.setChecked(DEFAULT_SETTINGS["inherit_target"])
        self.cb_only_uncoded.setChecked(DEFAULT_SETTINGS["only_uncoded"])
        
        for code, edit in self.shortcut_edits.items():
            default_key = DEFAULT_SETTINGS["hotkeys"].get(code, "")
            edit.setKeySequence(QKeySequence(default_key))
