import csv
import json
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QPushButton, QLineEdit, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView,
    QSplitter, QAbstractItemView, QSlider, QInputDialog, QTabWidget
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import Qt, QUrl, Slot, Signal, QEvent, QTimer, QSignalBlocker
from PySide6.QtGui import QAction, QColor, QKeySequence

from src.core.app_settings import AppSettings
from src.version import __version__
from src.ui.settings_dialog import SettingsDialog
from src.ui.research_workflow import ResearchWorkflow
from src.core.research import ROLES, STATES, review_state, ensure_character_ids, now, normalize_annotation, missing_roles, CodingHistory
from copy import deepcopy
from src.core.parsers import parse_srt, milliseconds_to_srt_time
from src.core.characters import get_base_dir, read_characters, save_characters, validate_character_name
from src.core.csv_utils import write_rows_to_csv_atomic
from src.core.project import (
    AUTOSAVE_OF_KEY, autosave_is_recoverable, autosave_path_for, read_project_file, recovery_target,
    remove_file_quietly, write_project_file,
)

class VideoAnnotator(ResearchWorkflow, QMainWindow):
    request_new_project = Signal()
    request_open_project = Signal(str)

    def __init__(self, video_file, srt_file, char_file, vat_file=""):
        super().__init__()
        self.ready = False
        self.setWindowTitle("CIGA Annotator")
        
        self.app_settings = AppSettings()

        self.current_subtitle_index = 0
        self.paused_at_subtitle_end = False
        
        self.vat_file = vat_file
        self.is_dirty = False
        self._recovered_from_autosave = False
        self.annotations = {}
        self.custom_columns = ['Note']
        project_data = {}

        if self.vat_file:
            # Load project details from .vat JSON
            try:
                project_data = read_project_file(self.vat_file)
                video_file = project_data.get('video_file', '')
                srt_file = project_data.get('srt_file', '')
                self.char_file = project_data.get('char_file', '')
                self.characters = project_data.get('characters', [])
                
                # Convert string keys to int indices
                loaded_ann = project_data.get('annotations', {})
                self.annotations = {int(k): v for k, v in loaded_ann.items()}
                
                self.custom_columns = project_data.get('custom_columns', ['Note'])

                # Make paths absolute relative to the vat file folder if they are relative
                vat_dir = Path(self.vat_file).parent
                if not Path(video_file).is_absolute():
                    video_file = str(vat_dir / video_file)
                if not Path(srt_file).is_absolute():
                    srt_file = str(vat_dir / srt_file)
                if self.char_file and not Path(self.char_file).is_absolute():
                    self.char_file = str(vat_dir / self.char_file)
                    
                # Ensure files exist, prompt if they don't
                is_file_updated = False
                if video_file and not Path(video_file).exists():
                    QMessageBox.warning(self, "Missing File", f"Cannot find video file:\n{video_file}\nPlease select its new location.")
                    new_video, _ = QFileDialog.getOpenFileName(self, "Locate Video File", str(vat_dir), "Video Files (*.mp4 *.mkv *.avi);;All Files (*)")
                    if new_video:
                        video_file = new_video
                        is_file_updated = True
                    else:
                        raise FileNotFoundError("Video file not found and user canceled selection.")

                if srt_file and not Path(srt_file).exists():
                    QMessageBox.warning(self, "Missing File", f"Cannot find subtitle file:\n{srt_file}\nPlease select its new location.")
                    new_srt, _ = QFileDialog.getOpenFileName(self, "Locate Subtitle File", str(vat_dir), "Subtitle Files (*.srt);;All Files (*)")
                    if new_srt:
                        srt_file = new_srt
                        is_file_updated = True
                    else:
                        raise FileNotFoundError("Subtitle file not found and user canceled selection.")

                if self.char_file and not Path(self.char_file).exists():
                    QMessageBox.warning(self, "Missing File", f"Cannot find character file:\n{self.char_file}\nPlease select its new location (optional).")
                    new_char, _ = QFileDialog.getOpenFileName(self, "Locate Character File", str(vat_dir), "Text Files (*.txt);;All Files (*)")
                    if new_char:
                        self.char_file = new_char
                        is_file_updated = True
                    else:
                        self.char_file = "" # Optional, so just clear it if canceled
                        is_file_updated = True

                if is_file_updated:
                    # Update paths back to being relative to the vat file dir. 
                    # If they are on a different drive, they'll remain absolute, which is acceptable
                    try:
                        project_data['video_file'] = str(Path(video_file).relative_to(vat_dir))
                    except ValueError:
                        project_data['video_file'] = video_file

                    try:
                        project_data['srt_file'] = str(Path(srt_file).relative_to(vat_dir))
                    except ValueError:
                        project_data['srt_file'] = srt_file

                    if self.char_file:
                        try:
                            project_data['char_file'] = str(Path(self.char_file).relative_to(vat_dir))
                        except ValueError:
                            project_data['char_file'] = self.char_file
                    else:
                        project_data['char_file'] = ""

                    self.is_dirty = True

                if AUTOSAVE_OF_KEY in project_data:
                    # Recovered from an autosave: keep working on the project it belongs
                    # to, never on the hidden autosave file. If its recorded owner does
                    # not match where it lives (a copied folder), continue as an unsaved
                    # session so Save asks for a location instead of overwriting another
                    # project.
                    target = recovery_target(self.vat_file, project_data, srt_file)
                    self.vat_file = target or ""
                    self.is_dirty = True
                    self._recovered_from_autosave = True
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load project file: {e}")
                return
        else:
            if not char_file:
                char_file = str(get_base_dir() / "characters.txt")
            self.char_file = char_file
            self.characters = read_characters(self.char_file)

        self.video_file = video_file
        self.srt_file = srt_file

        self.update_window_title()

        self.subtitles = parse_srt(self.srt_file)
        if not self.subtitles:
            QMessageBox.critical(self, "Error", "No subtitles found or failed to parse the SRT file.")
            return

        try:
            self.init_research(project_data)
        except (ValueError, TypeError, KeyError) as error:
            QMessageBox.critical(self, 'Material mismatch', str(error))
            return

        self.current_speakers = []
        self.current_listeners = []
        self.current_targets = []
        self.active_role = 'speakers'
        self._updating_table = False
        self.slider_is_dragging = False
        # Autosave files this session wrote or recovered from; all are removed once the
        # work is saved or explicitly discarded (the location moves on "Save As").
        self._autosave_files = {self.autosave_path}

        # Video Section first to ensure seek_slider exists before duration_changed triggers
        self.play_pause_btn = QPushButton("Pause")
        self.play_pause_btn.clicked.connect(self.handle_spacebar)
        self.seek_slider = QSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderPressed.connect(self.on_seek_slider_pressed)
        self.seek_slider.sliderReleased.connect(self.on_seek_slider_released)
        self.seek_slider.sliderMoved.connect(self.on_seek_slider_moved)
        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setMinimumWidth(110)

        # Media Player
        self.mediaPlayer = QMediaPlayer(self)

        self.videoWidget = QVideoWidget()
        # Clicking the video ends character editing and restores coding hotkeys.
        self.videoWidget.setFocusPolicy(Qt.StrongFocus)
        self.audioOutput = QAudioOutput(self)
        self.mediaPlayer.setAudioOutput(self.audioOutput)
        self.mediaPlayer.setVideoOutput(self.videoWidget)
        self.mediaPlayer.setSource(QUrl.fromLocalFile(video_file))

        self.mediaPlayer.positionChanged.connect(self.position_changed)
        self.mediaPlayer.durationChanged.connect(self.duration_changed)
        self.mediaPlayer.mediaStatusChanged.connect(self.media_status_changed)
        self.mediaPlayer.errorOccurred.connect(self.handle_error)
        self.mediaPlayer.playbackStateChanged.connect(self.update_play_button_text)

        # UI Subtitle Overlay
        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 5px;")

        # Controls UI
        self.character_table = QTableWidget()
        self.character_table.itemChanged.connect(self.on_character_table_item_changed)
        
        # Override table key press for delete handling
        original_key_press = self.character_table.keyPressEvent
        def table_key_press(event):
            if event.key() == Qt.Key_Escape:
                self.character_table.clearFocus()
                self.setFocus()
            elif event.key() == Qt.Key_Delete:
                self.delete_selected_character()
            else:
                original_key_press(event)
        self.character_table.keyPressEvent = table_key_press
        
        self.setup_character_table(self.character_table)

        # Global shortcut for adding new character
        from PySide6.QtGui import QShortcut, QKeySequence
        self.new_char_shortcut = QShortcut(QKeySequence("Ctrl+N"), self)
        self.new_char_shortcut.activated.connect(self.focus_new_character_row)

        self.speaker_summary = QLineEdit()
        self.speaker_summary.setReadOnly(True)
        self.listener_summary = QLineEdit()
        self.listener_summary.setReadOnly(True)
        self.target_summary = QLineEdit()
        self.target_summary.setReadOnly(True)
        self.active_role_label = QLabel("")
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Optional note for current subtitle line")
        self.note_edit.textChanged.connect(self.on_note_text_changed)

        management_layout = QVBoxLayout()
        self.add_character_controls(management_layout)
        management_layout.addWidget(self.character_table)
        management_widget = QWidget()
        management_widget.setLayout(management_layout)

        coding_layout = QVBoxLayout()
        coding_layout.setSpacing(4)
        self.unit_label = QLabel()
        self.unit_label.setStyleSheet("font-weight: bold;")
        coding_layout.addWidget(self.unit_label)
        self.study_label = QLabel()
        self.study_label.setTextFormat(Qt.PlainText)
        coding_layout.addWidget(self.study_label)
        self.add_coding_controls(coding_layout)
        
        self.speaker_label = QLabel("Speaker:")
        speaker_row = QHBoxLayout()
        self.speaker_label.setMinimumWidth(65)
        speaker_row.addWidget(self.speaker_label)
        speaker_row.addWidget(self.speaker_summary, 1)
        coding_layout.addLayout(speaker_row)
        
        self.listener_label = QLabel("Listener:")
        listener_row = QHBoxLayout()
        self.listener_label.setMinimumWidth(65)
        listener_row.addWidget(self.listener_label)
        listener_row.addWidget(self.listener_summary, 1)
        coding_layout.addLayout(listener_row)
        
        self.target_label = QLabel("Target:")
        target_row = QHBoxLayout()
        self.target_label.setMinimumWidth(65)
        target_row.addWidget(self.target_label)
        target_row.addWidget(self.target_summary, 1)
        coding_layout.addLayout(target_row)
        
        coding_layout.addWidget(QLabel("Note:"))
        coding_layout.addWidget(self.note_edit)
        self.add_review_controls(coding_layout)
        coding_widget = QWidget()
        coding_widget.setLayout(coding_layout)

        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(coding_widget, 'Current coding')
        self.right_tabs.addTab(management_widget, 'Characters')
        controls_widget = self.right_tabs
        controls_widget.setMinimumWidth(390)

        # Video Layout
        player_controls_layout = QHBoxLayout()
        previous_btn = QPushButton('Previous unit')
        previous_btn.clicked.connect(self.go_to_previous_subtitle)
        next_btn = QPushButton('Next unit')
        next_btn.clicked.connect(self.go_to_next_subtitle)
        player_controls_layout.addWidget(previous_btn)
        player_controls_layout.addWidget(self.play_pause_btn)
        player_controls_layout.addWidget(next_btn)
        player_controls_layout.addWidget(self.seek_slider, 1)
        player_controls_layout.addWidget(self.time_label)

        video_layout = QVBoxLayout()
        video_layout.addWidget(self.videoWidget)
        video_layout.addWidget(self.subtitle_label)
        video_layout.addLayout(player_controls_layout)
        video_layout.setStretch(0, 1)
        video_layout.setStretch(1, 0)
        video_layout.setStretch(2, 0)
        video_container = QWidget()
        video_container.setLayout(video_layout)

        # Top Splitter (Video vs Controls)
        top_splitter = QSplitter(Qt.Horizontal)
        top_splitter.addWidget(video_container)
        top_splitter.addWidget(controls_widget)
        top_splitter.setStretchFactor(0, 4)
        top_splitter.setStretchFactor(1, 1)

        # Bottom Subtitle List
        self.subtitle_list = QTableWidget()
        self.subtitle_list.setAlternatingRowColors(True)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search subtitle text...")
        self.search_edit.textChanged.connect(self.apply_subtitle_filters)
        
        self.add_column_btn = QPushButton("+ Column")
        self.add_column_btn.clicked.connect(self.add_custom_column)
        self.add_column_btn.setMaximumWidth(80)
        
        self.next_uncoded_btn = QPushButton("Next Unfinished")
        self.next_uncoded_btn.clicked.connect(self.jump_to_next_uncoded)
        self.next_uncoded_btn.setMaximumWidth(120)
        self.clear_filters_btn = QPushButton("Clear")
        self.clear_filters_btn.clicked.connect(self.clear_subtitle_filters)
        self.clear_filters_btn.setMaximumWidth(80)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(self.search_edit, 1)
        self.add_review_filter(filter_bar)
        filter_bar.addWidget(self.add_column_btn)
        filter_bar.addWidget(self.next_uncoded_btn)
        filter_bar.addWidget(self.clear_filters_btn)

        subtitle_panel = QWidget()
        subtitle_panel_layout = QVBoxLayout()
        subtitle_panel_layout.addLayout(filter_bar)
        subtitle_panel_layout.addWidget(self.subtitle_list)
        subtitle_panel.setLayout(subtitle_panel_layout)

        self.setup_subtitle_list()
        self.subtitle_list.itemClicked.connect(self.on_subtitle_clicked)
        self.subtitle_list.itemChanged.connect(self.on_subtitle_item_changed)

        # Main Splitter (Top vs Bottom)
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.addWidget(top_splitter)
        main_splitter.addWidget(subtitle_panel)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setSizes([540, 260])
        subtitle_panel.setMinimumHeight(180)

        main_layout = QVBoxLayout()
        main_layout.addWidget(main_splitter)
        
        widget = QWidget()
        widget.setLayout(main_layout)
        self.setCentralWidget(widget)

        self.create_menu_bar()
        self.installEventFilter(self)
        available = self.screen().availableGeometry()
        self.resize(min(1250, int(available.width() * 0.95)), min(900, int(available.height() * 0.9)))

        # Status bar with live progress and shortcut hints.
        self.progress_label = QLabel("")
        self.hint_label = QLabel("Active role coding enabled")
        self.statusBar().addPermanentWidget(self.progress_label, 1)
        self.statusBar().addPermanentWidget(self.hint_label, 2)
        self.update_active_role_ui()

        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(15000)
        self.autosave_timer.timeout.connect(self.autosave_annotations)
        self.autosave_timer.start()

        QTimer.singleShot(0, self.try_restore_autosave)

        self.ready = True
        self.mediaPlayer.play()
        self.jump_to_subtitle(self.current_subtitle_index)

    @property
    def autosave_path(self):
        return autosave_path_for(self.vat_file, self.srt_file)

    def update_window_title(self):
        name = Path(self.vat_file).name if self.vat_file else Path(self.srt_file).name
        self.setWindowTitle(f"CIGA Annotator - {name}" + (" *" if self.is_dirty else ""))

    def create_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        self.undo_action = QAction("Undo Coding", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self.undo_coding)
        edit_menu.addAction(self.undo_action)
        self.redo_action = QAction("Redo Coding", self)
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        self.redo_action.triggered.connect(self.redo_coding)
        edit_menu.addAction(self.redo_action)
        tools_menu = menu_bar.addMenu("Tools")
        rules_action = QAction("Project Coding Rules…", self)
        rules_action.triggered.connect(self.show_research_settings)
        tools_menu.addAction(rules_action)
        comparison_action = QAction("Compare Another Coder’s Project…", self)
        comparison_action.triggered.connect(self.compare_project_dialog)
        tools_menu.addAction(comparison_action)
        history_action = QAction('Material and Coding History…', self)
        history_action.triggered.connect(self.show_project_history)
        tools_menu.addAction(history_action)
        help_menu = menu_bar.addMenu("Help")
        
        new_action = QAction("New Project", self)
        new_action.triggered.connect(self.request_new_project.emit)
        file_menu.addAction(new_action)

        open_action = QAction("Open Project (.vat)", self)
        open_action.triggered.connect(self.open_project_dialog)
        file_menu.addAction(open_action)

        file_menu.addSeparator()

        save_action = QAction("Save Project", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_project)
        file_menu.addAction(save_action)

        export_characters = QAction('Export Character Template…', self)
        export_characters.triggered.connect(self.export_characters_dialog)
        file_menu.addAction(export_characters)
        save_as_action = QAction("Save Project As...", self)
        save_as_action.triggered.connect(self.save_project_as_dialog)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        export_csv_action = QAction("Export All Coding to CSV…", self)
        export_csv_action.triggered.connect(self.export_csv_dialog)
        file_menu.addAction(export_csv_action)
        analysis_action = QAction("Export Confirmed Coding for Analysis…", self)
        analysis_action.triggered.connect(self.export_analysis_dialog)
        file_menu.addAction(analysis_action)

        import_csv_action = QAction("Import from CSV", self)
        import_csv_action.triggered.connect(self.import_csv_dialog)
        file_menu.addAction(import_csv_action)
        
        file_menu.addSeparator()

        preferences_action = QAction("Preferences", self)
        preferences_action.triggered.connect(self.show_preferences)
        file_menu.addAction(preferences_action)

        self.next_uncoded_action = QAction("Jump to Next Unfinished", self)
        self.next_uncoded_action.setShortcut(self.app_settings.get_hotkey("next_uncoded"))
        self.next_uncoded_action.triggered.connect(self.jump_to_next_uncoded)
        tools_menu.addAction(self.next_uncoded_action)

        self.shortcuts_help_action = QAction("Shortcuts", self)
        self.shortcuts_help_action.setShortcut(self.app_settings.get_hotkey("shortcuts_help"))
        self.shortcuts_help_action.triggered.connect(self.show_shortcuts_help)
        help_menu.addAction(self.shortcuts_help_action)

        help_menu.addSeparator()
        self.about_action = QAction("About CIGA", self)
        self.about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(self.about_action)

    def show_about_dialog(self):
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("About CIGA Annotator")
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(
            "<h3>CIGA: Character Interaction and Graph Analysis</h3>"
            "<p><b>CIGA Annotator</b></p>"
            f"<p><b>Version: {__version__}</b></p>"
            "<p>A annotation tool for character interaction graph analysis.</p>"
            "<p><i>Developed by: <a href='http://mediacomplab.com'>Media Comprehension Lab</a></i></p>"
            "<p>For more information, visit our <a href='https://github.com/MediaComprehensionLab/CIGA'>GitHub Repository</a>.</p>"
            "<p>If you find CIGA useful, please consider citing our work:"
            "<pre>@article{mcl2025ciga,\n  title={CIGA: Character Interaction and Graph Analysis for Video},\n  author={Media Comprehension Lab},\n  year={2025}\n}</pre></p>"
        )
        msg_box.exec()

    def setup_character_table(self, table):
        self._updating_table = True
        num_characters = len(self.characters)
        table.setRowCount(num_characters + 1)
        table.setColumnCount(2)
        table.setHorizontalHeaderLabels(["Name", "Key"])
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        for row, char_info in enumerate(self.characters):
            name_item = QTableWidgetItem(char_info['name'])
            key_item = QTableWidgetItem(char_info.get('key', ''))
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, key_item)

        # Empty row for new character
        empty_name_item = QTableWidgetItem()
        empty_name_item.setToolTip("Type new character name and press Enter")
        empty_name_item.setText("")
        empty_name_item.setForeground(QColor("gray"))
        
        empty_key_item = QTableWidgetItem()
        
        table.setItem(num_characters, 0, empty_name_item)
        table.setItem(num_characters, 1, empty_key_item)
        
        self._updating_table = False

    def refresh_role_summary(self):
        self.speaker_summary.setText(', '.join(self.current_speakers))
        self.listener_summary.setText(', '.join(self.current_listeners))
        self.target_summary.setText(', '.join(self.current_targets))
        self.sync_research_controls()

    def update_active_role_ui(self):
        role_name = {
            'speakers': 'Speaker',
            'listeners': 'Listener',
            'targets': 'Target'
        }.get(self.active_role, 'Speaker')
        self.active_role_label.setText(role_name)
        self.sync_research_controls()
        next_key = self.app_settings.get_hotkey('next_uncoded')
        self.hint_label.setText(
            f"Active: {role_name} · Alt+[character key]: code · {next_key}: next unfinished · Ctrl+S: save project"
        )

        active_style = "font-weight: bold; color: #4DA6FF;" # Bright blue
        active_edit_style = "font-weight: bold; color: #4DA6FF; border: 1px solid #4DA6FF;"
        inactive_style = "font-weight: normal;"
        inactive_edit_style = "font-weight: normal;"
        
        # Reset all labels
        self.speaker_label.setStyleSheet(inactive_style)
        self.listener_label.setStyleSheet(inactive_style)
        self.target_label.setStyleSheet(inactive_style)
        
        self.speaker_summary.setStyleSheet(inactive_edit_style)
        self.listener_summary.setStyleSheet(inactive_edit_style)
        self.target_summary.setStyleSheet(inactive_edit_style)
        
        # Apply active label style
        if self.active_role == 'speakers':
            self.speaker_label.setStyleSheet(active_style)
            self.speaker_summary.setStyleSheet(active_edit_style)
        elif self.active_role == 'listeners':
            self.listener_label.setStyleSheet(active_style)
            self.listener_summary.setStyleSheet(active_edit_style)
        elif self.active_role == 'targets':
            self.target_label.setStyleSheet(active_style)
            self.target_summary.setStyleSheet(active_edit_style)

    def set_active_role(self, role):
        if role in ['speakers', 'listeners', 'targets']:
            self.active_role = role
            self.right_tabs.setCurrentIndex(0)
            self.update_active_role_ui()

    def cycle_active_role(self):
        roles = ['speakers', 'listeners', 'targets']
        idx = roles.index(self.active_role)
        self.set_active_role(roles[(idx + 1) % len(roles)])

    def sanitize_role_values(self):
        valid_names = {char['name'] for char in self.characters}
        self.current_speakers = [name for name in self.current_speakers if name in valid_names]
        self.current_listeners = [name for name in self.current_listeners if name in valid_names]
        self.current_targets = [name for name in self.current_targets if name in valid_names]
        self.refresh_role_summary()

    def delete_selected_character(self):
        selected = self.character_table.selectedItems()
        if not selected:
            return
        
        row = selected[0].row()
        if row >= len(self.characters):
            return  # Can't delete the new character placeholder row
        
        name = self.characters[row]['name']
        referenced = sum(any(name in annotation.get(role, []) for role in ROLES) for annotation in self.annotations.values())
        if referenced:
            QMessageBox.information(self, 'Character is in use',
                                    f"'{name}' is referenced by {referenced} coding units. Remove those selections before deleting it. Renaming preserves its identity.")
            return
        reply = QMessageBox.question(self, 'Delete Character', f"Delete unused character '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.audit('Delete unused character', before=self.characters[row])
            del self.characters[row]
            self.history = CodingHistory()
            self.setup_character_table(self.character_table)
            self.sanitize_role_values()
            self.is_dirty = True
            self.update_progress_status()

    def on_character_table_item_changed(self, item):
        if hasattr(self, '_updating_table') and self._updating_table:
            return

        row = item.row()
        col = item.column()
        text = item.text().strip()
        
        is_new_row = (row == len(self.characters))
        
        if is_new_row:
            if not text:
                return
            
            # If they typed in Name col for new character
            if col == 0:
                error = validate_character_name(text)
                if text.casefold() in {character['name'].casefold() for character in self.characters}:
                    error = 'A character with this name already exists.'
                if error:
                    QMessageBox.warning(self, "Invalid Name", error)
                    self._updating_table = True
                    item.setText("")
                    self._updating_table = False
                    return
                name = text
                # auto-assign shortcut
                used_keys = {str(c.get('key', '')).upper() for c in self.characters if c.get('key')}
                assigned_key = None
                for i in range(1, 10):
                    if str(i) not in used_keys:
                        assigned_key = str(i)
                        break
                
                self.characters.append({'name': name, 'key': assigned_key})
                ensure_character_ids(self.characters)
                self.audit('Add character', after=self.characters[-1])
                self.setup_character_table(self.character_table)
                self.sanitize_role_values()
                self.is_dirty = True
                self.update_progress_status()
                
                # Automatically focus the newly created placeholder row
                QTimer.singleShot(0, self._continue_character_entry)
        else:
            # Editing existing
            if col == 0:
                error = validate_character_name(text)
                if any(index != row and character['name'].casefold() == text.casefold() for index, character in enumerate(self.characters)):
                    error = 'A character with this name already exists.'
                if error:
                    # Emptied or invalid: restore the previous name.
                    if text:
                        QMessageBox.warning(self, "Invalid Name", error)
                    self._updating_table = True
                    item.setText(self.characters[row]['name'])
                    self._updating_table = False
                    return
                previous_name = self.characters[row]['name']
                if text != previous_name:
                    self.characters[row]['aliases'].append(previous_name)
                    self.audit('Rename character', before={'name': previous_name, 'id': self.characters[row]['id']}, after={'name': text, 'id': self.characters[row]['id']})
                self.characters[row]['name'] = text
                if previous_name != text:
                    for annotation in self.annotations.values():
                        for role in ('speakers', 'listeners', 'targets'):
                            annotation[role] = [text if name == previous_name else name
                                                for name in annotation.get(role, [])]
                    for names in (self.current_speakers, self.current_listeners, self.current_targets):
                        names[:] = [text if name == previous_name else name for name in names]
                    for index in self.annotations:
                        self.refresh_subtitle_row(index)
            elif col == 1:
                k = text.upper()
                if k and (len(k) != 1 or not k.isprintable() or k == ' '):
                    QMessageBox.warning(self, "Invalid Shortcut", "Shortcut must be a single printable key.")
                    self._updating_table = True
                    item.setText(self.characters[row].get('key', '') or '')
                    self._updating_table = False
                    return
                
                if k:
                    # Check duplicates
                    used_keys = {str(c.get('key', '')).upper(): idx for idx, c in enumerate(self.characters) if c.get('key')}
                    if k in used_keys and used_keys[k] != row:
                        QMessageBox.warning(self, "Duplicate Shortcut", f"Shortcut '{k}' is already used.")
                        self._updating_table = True
                        item.setText(self.characters[row].get('key', '') or '')
                        self._updating_table = False
                        return
                    self.characters[row]['key'] = k
                else:
                    self.characters[row]['key'] = None
                    
            self.history = CodingHistory()  # Old patches contain previous display names.
            self.setup_character_table(self.character_table) # Re-render to ensure styling and proper state
            self.sanitize_role_values()
            self.is_dirty = True
            self.update_progress_status()

    def focus_new_character_row(self):
        self.right_tabs.setCurrentIndex(1)
        self.character_table.setFocus()
        new_row = len(self.characters)
        item = self.character_table.item(new_row, 0)
        self.character_table.setCurrentItem(item)
        self.character_table.editItem(item)

    def _continue_character_entry(self):
        """Continue after Enter, without stealing focus back after a video click."""
        focused = QApplication.focusWidget()
        if focused is self.character_table or (
            focused is not None and self.character_table.isAncestorOf(focused)
        ):
            self.focus_new_character_row()

    def setup_subtitle_list(self):
        base_cols = ["#", "Start", "End", "Text", "Speaker", "Listener", "Target"]
        total_cols = len(base_cols) + len(self.custom_columns) + 1
        self.subtitle_list.setColumnCount(total_cols)
        self.subtitle_list.setHorizontalHeaderLabels(base_cols + self.custom_columns + ["Review"])
        self.subtitle_list.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.subtitle_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.subtitle_list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.subtitle_list.setFocusPolicy(Qt.NoFocus) # Keeps playback/navigation shortcuts available.

        self.subtitle_list.setRowCount(len(self.subtitles))
        for i, sub in enumerate(self.subtitles):
            self.subtitle_list.setItem(i, 0, self._make_readonly_item(str(sub['index'])))
            self.subtitle_list.setItem(i, 1, self._make_readonly_item(milliseconds_to_srt_time(sub['start_time'])))
            self.subtitle_list.setItem(i, 2, self._make_readonly_item(milliseconds_to_srt_time(sub['end_time'])))
            self.subtitle_list.setItem(i, 3, self._make_readonly_item(sub['text']))
            self.subtitle_list.setItem(i, 4, self._make_readonly_item(""))
            self.subtitle_list.setItem(i, 5, self._make_readonly_item(""))
            self.subtitle_list.setItem(i, 6, self._make_readonly_item(""))
            
            for j, c in enumerate(self.custom_columns):
                val = self.annotations.get(i, {}).get(c, "")
                if not val and c == "Note":
                    val = self.annotations.get(i, {}).get("note", "")
                self.subtitle_list.setItem(i, 7 + j, QTableWidgetItem(val))

        self.subtitle_list.setColumnWidth(0, 45)
        self.subtitle_list.setColumnWidth(1, 90)
        self.subtitle_list.setColumnWidth(2, 90)
        self.subtitle_list.setColumnWidth(4, 140)
        self.subtitle_list.setColumnWidth(5, 140)
        self.subtitle_list.setColumnWidth(6, 140)
        for j in range(len(self.custom_columns)):
            self.subtitle_list.setColumnWidth(7 + j, 220)
            
        for index in range(len(self.subtitles)):
            self.refresh_subtitle_row(index)
        self.subtitle_list.setColumnWidth(7 + len(self.custom_columns), 120)
        self.apply_subtitle_filters()

    def _make_readonly_item(self, text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def clear_subtitle_filters(self):
        self.search_edit.clear()
        self.review_filter.setCurrentIndex(0)
        self.app_settings.set("only_uncoded", False)
        self.apply_subtitle_filters()

    def add_custom_column(self):
        name, ok = QInputDialog.getText(self, 'Add Custom Column', 'Column name:')
        if not ok or not name.strip():
            return
        name = name.strip()
        reserved = {'line', 'position', 'start_time', 'end_time', *ROLES, 'note', 'unit_id',
                    'subtitle_sha256', 'review_state', 'not_applicable', 'coder_id',
                    'codebook_version', 'confirmation', 'exclusion_reason', 'study_rules'}
        if name in reserved or name in self.custom_columns:
            QMessageBox.warning(self, 'Reserved column', 'Choose a unique name that is not a built-in coding field.')
            return
        self.custom_columns.append(name)
        with QSignalBlocker(self.subtitle_list):
            self.setup_subtitle_list()
        self.audit('Add custom column', after=name)
        self.is_dirty = True
        self.update_progress_status()

    def apply_subtitle_filters(self):
        query = self.search_edit.text().strip().lower()
        only_uncoded = self.app_settings.get("only_uncoded", False)
        for i, sub in enumerate(self.subtitles):
            status = self.get_annotation_status(i)
            match_text = query in sub['text'].lower() if query else True
            state = review_state(self.annotations.get(i, {}))
            match_coded = state not in ('confirmed', 'excluded') if only_uncoded else True
            selected = self.review_filter.currentData()
            match_review = (selected == 'all' or selected == state or
                            (selected == 'unfinished' and state not in ('confirmed', 'excluded')))
            match_coded = match_coded and match_review
            self.subtitle_list.setRowHidden(i, not (match_text and match_coded))

    def apply_inheritance_to_current(self):
        if self.current_subtitle_index <= 0:
            return
        if self.current_subtitle_index in self.annotations:
            return
        prev_ann = self.annotations.get(self.current_subtitle_index - 1, {})
        if self.app_settings.get("inherit_listener", False):
            self.current_listeners = list(prev_ann.get('listeners', []))        
        if self.app_settings.get("inherit_target", False):
            self.current_targets = list(prev_ann.get('targets', []))
        if self.current_listeners or self.current_targets:
            self.commit_annotation(self.current_subtitle_index, {
                'speakers': self.current_speakers, 'listeners': self.current_listeners,
                'targets': self.current_targets, 'note': '',
                'inherited_from': self.material['unit_ids'][self.current_subtitle_index - 1],
            }, 'Inherit previous roles')
        self.refresh_role_summary()

    def _extract_shortcut(self, event):
        key = event.key()
        if Qt.Key_0 <= key <= Qt.Key_9:
            return chr(ord('0') + (key - Qt.Key_0))
        if Qt.Key_A <= key <= Qt.Key_Z:
            return chr(ord('A') + (key - Qt.Key_A))
        text = event.text().upper()
        if len(text) == 1 and text.isprintable():
            return text
        return ""

    def _toggle_role_name(self, role, name):
        if role == 'speakers':
            target_list = self.current_speakers
        elif role == 'listeners':
            target_list = self.current_listeners
        else:
            target_list = self.current_targets

        if name in target_list:
            target_list.remove(name)
        else:
            target_list.append(name)
        self.refresh_role_summary()

    def on_note_text_changed(self, text):
        if self._updating_table:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False, action="Edit note")

    def on_subtitle_item_changed(self, item):
        if self._updating_table:
            return
        col = item.column()
        if col < 7 or col >= 7 + len(self.custom_columns):
            return
        row = item.row()
        ann = deepcopy(self.annotations.get(row, {'speakers': [], 'listeners': [], 'targets': []}))
        
        col_idx = col - 7
        if col_idx < len(self.custom_columns):
            col_name = self.custom_columns[col_idx]
            ann[col_name] = item.text().strip()
            if col_name == "Note":
                ann["note"] = item.text().strip()
                
        self.commit_annotation(row, ann, "Edit note" if col_name == "Note" else "Edit custom field")
        if row == self.current_subtitle_index:
            self._updating_table = True
            if "Note" in self.custom_columns and col_idx < len(self.custom_columns) and self.custom_columns[col_idx] == "Note":
                self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self.refresh_role_summary()
        self.is_dirty = True
        self.refresh_subtitle_row(row)
        self.apply_subtitle_filters()
        self.update_progress_status()
        
    def on_subtitle_clicked(self, item):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        row = item.row()
        self.jump_to_subtitle(row)

    def jump_to_subtitle(self, index, inherit=True):
        if 0 <= index < len(self.subtitles):
            if index != self.current_subtitle_index:
                self.break_note_edit()
            if self.subtitle_list.isRowHidden(index):
                self.clear_subtitle_filters()
                self.statusBar().showMessage('Filters cleared to show the selected coding unit.', 5000)
            self.current_subtitle_index = index
            subtitle = self.subtitles[self.current_subtitle_index]
            self.mediaPlayer.setPosition(subtitle['start_time'])
            self.paused_at_subtitle_end = False
            self.subtitle_label.setText(subtitle['text'])
            self.subtitle_list.selectRow(index)
            self.subtitle_list.scrollToItem(self.subtitle_list.item(index, 0), QAbstractItemView.PositionAtCenter)
            
            # Restore panel selections
            ann = self.annotations.get(index, {})
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self._updating_table = True
            self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            if inherit:
                self.apply_inheritance_to_current()
            self.refresh_role_summary()
            self.update_progress_status()
            
            self.mediaPlayer.play()

    def get_annotation_status(self, index):
        return STATES[review_state(self.annotations.get(index, {}))]

    def refresh_subtitle_row(self, index):
        if index < 0 or index >= len(self.subtitles):
            return
        ann = self.annotations.get(index, {})
        speakers = ann.get('speakers', [])
        listeners = ann.get('listeners', [])
        targets = ann.get('targets', [])
        status = self.get_annotation_status(index)

        self._updating_table = True
        self.subtitle_list.setItem(index, 4, self._make_readonly_item(', '.join(speakers)))
        self.subtitle_list.setItem(index, 5, self._make_readonly_item(', '.join(listeners)))
        self.subtitle_list.setItem(index, 6, self._make_readonly_item(', '.join(targets)))
        
        for j, c in enumerate(self.custom_columns):
            val = ann.get(c, "")
            if not val and c == "Note":
                val = ann.get("note", "")
            self.subtitle_list.setItem(index, 7 + j, QTableWidgetItem(val))

        self.subtitle_list.setItem(index, 7 + len(self.custom_columns), self._make_readonly_item(status))
        if status == "Confirmed":
            status_color = QColor(40, 167, 69, 50)
        elif status in ("In progress", "Needs review"):
            status_color = QColor(255, 193, 7, 50)
        else:
            status_color = None

        col_count = self.subtitle_list.columnCount()
        for col in range(col_count):
            if self.subtitle_list.item(index, col):
                if col == 0 and status_color:
                    self.subtitle_list.item(index, col).setBackground(status_color)
                else:
                    self.subtitle_list.item(index, col).setData(Qt.BackgroundRole, None)
        self._updating_table = False

    def jump_to_next_uncoded(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        start = self.current_subtitle_index + 1
        for i in range(start, len(self.subtitles)):
            if self.get_annotation_status(i) not in ("Confirmed", "Excluded"):
                self.record_annotation(self.current_subtitle_index, clear_selections=False)
                self.jump_to_subtitle(i)
                return
        for i in range(0, start):
            if self.get_annotation_status(i) not in ("Confirmed", "Excluded"):
                self.record_annotation(self.current_subtitle_index, clear_selections=False)
                self.jump_to_subtitle(i)
                return
        self.statusBar().showMessage('Every unit is confirmed or explicitly excluded.', 10000)

    def show_shortcuts_help(self):
        descriptions = {'play_pause': 'Play/pause', 'prev_subtitle': 'Previous unit',
                        'next_subtitle': 'Next unit', 'seek_back': 'Rewind 2 seconds',
                        'seek_forward': 'Forward 2 seconds', 'next_uncoded': 'Next unfinished unit',
                        'focus_search': 'Search', 'shortcuts_help': 'Help',
                        'role_speakers': 'Speaker', 'role_listeners': 'Listener',
                        'role_targets': 'Target', 'cycle_role': 'Cycle coding roles'}
        lines = [f'{self.app_settings.get_hotkey(action) or "Unassigned"}: {label}' for action, label in descriptions.items()]
        lines += ['Alt+[character key]: toggle character', 'Ctrl+N: add character', 'Ctrl+S: save project',
                  'Ctrl+Z: undo coding', 'Ctrl+Shift+Z: redo coding',
                  '', 'While typing in a text field, text-editing keys remain available.',
                  'Click the video or a role button to resume coding shortcuts.']
        QMessageBox.information(self, 'Keyboard Shortcuts', '\n'.join(lines))

    def show_preferences(self):
        dialog = SettingsDialog(self, self.app_settings)
        if dialog.exec():
            # Apply changes
            self.apply_subtitle_filters()
            self.next_uncoded_action.setShortcut(self.app_settings.get_hotkey("next_uncoded"))
            self.shortcuts_help_action.setShortcut(self.app_settings.get_hotkey("shortcuts_help"))
            self.update_active_role_ui()

    def record_annotation(self, index, clear_selections=True, action="Edit coding"):
        if index >= len(self.subtitles): return
        
        speakers = list(self.current_speakers)
        listeners = list(self.current_listeners)
        targets = list(self.current_targets)
        note = self.note_edit.text().strip()
        
        if not speakers and not listeners and not targets and not note and index not in self.annotations:
            return # nothing to record
            
        previous = self.annotations.get(index, {})
        ann = dict(previous)
        ann['speakers'] = speakers
        ann['listeners'] = listeners
        ann['targets'] = targets
        ann['note'] = note
        if 'Note' in self.custom_columns:
            ann['Note'] = note
        
        self.commit_annotation(index, ann, action)

        if clear_selections:
            self.current_speakers = []
            self.current_listeners = []
            self.current_targets = []
        self.refresh_role_summary()
        self.apply_subtitle_filters()
        self.update_progress_status()

    def _is_hotkey(self, event, action_name):
        hotkey_str = self.app_settings.get_hotkey(action_name)
        if not hotkey_str: return False
        seq = QKeySequence(hotkey_str)
        if not seq.count(): return False
        
        # In PySide6, QKeySequence can be matched against an event's key combination
        event_key_combination = event.keyCombination()
        return seq.matches(QKeySequence(event_key_combination)) == QKeySequence.ExactMatch

    def eventFilter(self, source, event):
        if event.type() == QEvent.FocusIn and source is getattr(self, 'videoWidget', None):
            self.right_tabs.setCurrentIndex(0)
        if event.type() == QEvent.KeyPress:
            active_modal = QApplication.activeModalWidget()
            if active_modal and active_modal is not self:
                return False
            
            if self._is_hotkey(event, "focus_search"):
                self.search_edit.setFocus()
                self.search_edit.selectAll()
                return True
            if self._is_hotkey(event, "shortcuts_help"):
                self.show_shortcuts_help()
                return True
                
            focused = QApplication.focusWidget()
            if (isinstance(focused, QLineEdit) and not focused.isReadOnly()) or focused is self.character_table:
                return False
            if event.isAutoRepeat():
                return True
                
            if self._is_hotkey(event, "next_uncoded"):
                self.jump_to_next_uncoded()
                return True
            if self._is_hotkey(event, "play_pause"):
                self.handle_spacebar()
                return True
                
            key_text = self._extract_shortcut(event)
            if self._is_hotkey(event, "prev_subtitle"):
                self.go_to_previous_subtitle()
                return True
            if self._is_hotkey(event, "next_subtitle"):
                self.go_to_next_subtitle()
                return True
            if self._is_hotkey(event, "seek_back"):
                self.seek_relative(-2000)
                return True
            if self._is_hotkey(event, "seek_forward"):
                self.seek_relative(2000)
                return True

            if self._is_hotkey(event, "role_speakers"):
                self.set_active_role('speakers')
                return True
            if self._is_hotkey(event, "role_listeners"):
                self.set_active_role('listeners')
                return True
            if self._is_hotkey(event, "role_targets"):
                self.set_active_role('targets')
                return True
            if self._is_hotkey(event, "cycle_role"):
                self.cycle_active_role()
                return True

            modifiers = event.modifiers()
            is_alt = bool(modifiers & Qt.AltModifier)

            if is_alt and key_text:
                for char_info in self.characters:
                    if char_info.get('key') and char_info['key'] == key_text:
                        self._toggle_role_name(self.active_role, char_info["name"])
                        self.record_annotation(self.current_subtitle_index, clear_selections=False)
                        return True

        return False

    def go_to_previous_subtitle(self):
        if self.current_subtitle_index <= 0:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        self.jump_to_subtitle(self.current_subtitle_index - 1)
            
    def go_to_next_subtitle(self):
        if self.current_subtitle_index >= len(self.subtitles) - 1:
            return
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        self.jump_to_subtitle(self.current_subtitle_index + 1)

    def seek_relative(self, delta_ms):
        new_pos = self.mediaPlayer.position() + delta_ms
        new_pos = max(0, min(self.mediaPlayer.duration(), new_pos))
        self.mediaPlayer.setPosition(new_pos)
        self.paused_at_subtitle_end = False
        self.sync_subtitle_index_from_position(new_pos)

    def on_seek_slider_pressed(self):
        self.slider_is_dragging = True

    def on_seek_slider_released(self):
        self.slider_is_dragging = False
        pos = self.seek_slider.value()
        self.mediaPlayer.setPosition(pos)
        self.paused_at_subtitle_end = False
        self.sync_subtitle_index_from_position(pos)

    def on_seek_slider_moved(self, value):
        self.time_label.setText(f"{self.format_time(value)} / {self.format_time(self.mediaPlayer.duration())}")

    def duration_changed(self, duration):
        self.seek_slider.setRange(0, max(0, duration))
        self.time_label.setText(f"{self.format_time(self.mediaPlayer.position())} / {self.format_time(duration)}")

    def update_play_button_text(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.play_pause_btn.setText("Pause")
        else:
            self.play_pause_btn.setText("Play")

    def format_time(self, milliseconds):
        seconds = max(0, milliseconds) // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02}:{seconds:02}"

    def sync_subtitle_index_from_position(self, position):
        if not self.subtitles:
            return
        chosen = self.current_subtitle_index
        for i, subtitle in enumerate(self.subtitles):
            if subtitle['start_time'] <= position <= subtitle['end_time']:
                chosen = i
                break
            if subtitle['start_time'] <= position:
                chosen = i
        if chosen != self.current_subtitle_index:
            self.record_annotation(self.current_subtitle_index, clear_selections=False)
            self.current_subtitle_index = chosen
            self.subtitle_label.setText(self.subtitles[chosen]['text'])
            self.subtitle_list.selectRow(chosen)
            self.subtitle_list.scrollToItem(self.subtitle_list.item(chosen, 0), QAbstractItemView.PositionAtCenter)
            ann = self.annotations.get(chosen, {})
            self.current_speakers = list(ann.get('speakers', []))
            self.current_listeners = list(ann.get('listeners', []))
            self.current_targets = list(ann.get('targets', []))
            self._updating_table = True
            self.note_edit.setText(ann.get('note', ''))
            self._updating_table = False
            self.apply_inheritance_to_current()
            self.refresh_role_summary()
        self.update_progress_status()

    def handle_spacebar(self):
        if self.mediaPlayer.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.mediaPlayer.pause()
        else:
            if self.paused_at_subtitle_end:
                self.record_annotation(self.current_subtitle_index, clear_selections=False)
                if self.current_subtitle_index < len(self.subtitles) - 1:
                    self.jump_to_subtitle(self.current_subtitle_index + 1)
                else:
                    self.statusBar().showMessage('End of subtitle material. Current coding is preserved.', 8000)
            else:
                self.mediaPlayer.play()
        self.update_play_button_text()

    @Slot(QMediaPlayer.MediaStatus)
    def media_status_changed(self, status):
        pass

    @Slot(int)
    def position_changed(self, position):
        if not self.slider_is_dragging:
            self.seek_slider.setValue(position)
        self.time_label.setText(f"{self.format_time(position)} / {self.format_time(self.mediaPlayer.duration())}")
        if self.current_subtitle_index < len(self.subtitles):
            subtitle = self.subtitles[self.current_subtitle_index]
            end_time = subtitle['end_time']

            if position > end_time and not self.paused_at_subtitle_end:
                if self.app_settings.get("auto_pause", True):
                    self.mediaPlayer.pause()
                    self.update_play_button_text()
                    self.paused_at_subtitle_end = True
                else:
                    self.sync_subtitle_index_from_position(position)
                    self.paused_at_subtitle_end = False
                self.update_progress_status()
        else:
            self.subtitle_label.setText("")

    def open_project_dialog(self):
        vat_file, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "VAT Projects (*.vat)")
        if vat_file:
            self.request_open_project.emit(vat_file)

    def save_project(self):
        """Save to the current project, asking for a location first if there is none.

        Returns True only if the project was written.
        """
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        if not self.vat_file:
            return self.save_project_as_dialog()
        return self._save_to(self.vat_file)

    def save_project_as_dialog(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        save_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "project.vat", "VAT Projects (*.vat)")
        if not save_path:
            return False
        return self._save_to(save_path)

    def _save_to(self, file_path):
        try:
            write_project_file(file_path, self._project_data(file_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save project: {e}")
            return False
        self.vat_file = file_path
        self.is_dirty = False
        self.break_note_edit()
        self.discard_autosave()
        self.update_window_title()
        self.update_progress_status()
        return True

    def _project_data(self, file_path):
        # Paths are stored relative to the project file where possible, so a project
        # folder can be moved; files on another drive stay absolute.
        vat_dir = Path(file_path).parent

        def rel_path(p):
            if not p: return ""
            try:
                return str(Path(p).relative_to(vat_dir))
            except ValueError:
                return str(Path(p).absolute())

        return {
            "video_file": rel_path(self.video_file),
            "srt_file": rel_path(self.srt_file),
            "char_file": rel_path(self.char_file),
            "characters": self.characters,
            "custom_columns": getattr(self, 'custom_columns', ['Note']),
            "schema_version": 2,
            "study": self.study,
            "material": self.material,
            "audit_log": self.audit_log,
            "annotations": self.annotations
        }

    def export_csv_dialog(self):
        self.record_annotation(self.current_subtitle_index, clear_selections=False)
        if not self.annotations:
            reply = QMessageBox.question(self, "No Annotations", "No annotations recorded. Export anyway?", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return

        save_path, _ = QFileDialog.getSaveFileName(self, "Export to CSV", "annotations.csv", "CSV Files (*.csv)")
        if save_path:
            self.export_csv(save_path, include_metadata=True)

    def export_csv(self, file_path, confirmed_only=False, include_metadata=False):
        try:
            rows = []
            for i, sub in enumerate(self.subtitles):
                ann = self.annotations.get(i, {})
                if confirmed_only and review_state(ann) != 'confirmed':
                    continue
                spk = ', '.join(ann.get('speakers', []))
                lst = ', '.join(ann.get('listeners', []))
                tgt = ', '.join(ann.get('targets', []))
                has_custom = False
                
                row_data = {
                    'line': sub['text'],
                    'position': i + 1,
                    'start_time': milliseconds_to_srt_time(sub['start_time']),
                    'end_time': milliseconds_to_srt_time(sub['end_time']),
                    'speakers': spk,
                    'listeners': lst,
                    'targets': tgt
                }
                
                for c in getattr(self, 'custom_columns', ['Note']):
                    if c == 'position':
                        continue  # Reserved numeric subtitle order for CIGA.
                    val = ann.get(c, "")
                    if not val and c == "Note":
                        val = ann.get('note', '')
                    row_data[c] = val
                    if val.strip():
                        has_custom = True
                        
                if include_metadata:
                    row_data.update({
                        'unit_id': self.material['unit_ids'][i],
                        'subtitle_sha256': self.material['subtitle_sha256'],
                        'review_state': review_state(ann),
                        'not_applicable': json.dumps(ann.get('not_applicable', [])),
                        'coder_id': self.study['coder_id'],
                        'codebook_version': self.study['codebook_version'],
                        'confirmation': json.dumps(ann.get('confirmation', {})),
                        'exclusion_reason': ann.get('exclusion_reason', ''),
                        'study_rules': json.dumps({key: value for key, value in self.study.items() if key != 'coder_id'}),
                    })
                if confirmed_only or include_metadata or spk or lst or tgt or has_custom:
                    rows.append(row_data)

            fieldnames = ['line', 'position', 'start_time', 'end_time', 'speakers', 'listeners', 'targets']
            fieldnames += [c for c in getattr(self, 'custom_columns', ['Note']) if c != 'position']
            if include_metadata:
                fieldnames += ['unit_id', 'subtitle_sha256', 'review_state', 'not_applicable', 'coder_id',
                               'codebook_version', 'confirmation', 'exclusion_reason', 'study_rules']
            write_rows_to_csv_atomic(file_path, rows, fieldnames=fieldnames)
            self.update_progress_status()
            self.statusBar().showMessage(f"CSV exported to {file_path}. Save Project keeps your project changes.", 10000)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV: {e}")

    def import_csv_dialog(self):
        load_path, _ = QFileDialog.getOpenFileName(self, "Import from CSV", "", "CSV Files (*.csv)")
        if load_path:
            if self.annotations and QMessageBox.question(self, 'Replace current coding?',
                    'Import replaces the coding in this project. Save a project copy first if you need to keep both versions.',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            self.import_csv(load_path)

    def import_csv(self, file_path):
        # Validate everything before replacing project data; failed imports preserve work.
        try:
            with open(file_path, 'r', newline='', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)
                fields = reader.fieldnames or []
                if not {'start_time', 'end_time'}.issubset(fields):
                    raise ValueError('CSV requires start_time and end_time columns.')
                loaded = list(reader)
            reserved = {'line', 'position', 'start_time', 'end_time', *ROLES, 'note',
                        'unit_id', 'subtitle_sha256', 'review_state', 'not_applicable', 'coder_id',
                        'codebook_version', 'confirmation', 'exclusion_reason', 'study_rules'}
            columns = list(self.custom_columns)
            columns.extend(field for field in fields if field not in reserved and field not in columns)
            units = {}
            for index, sub in enumerate(self.subtitles):
                times = (milliseconds_to_srt_time(sub['start_time']), milliseconds_to_srt_time(sub['end_time']))
                units.setdefault(times, []).append(index)
            annotations = {}
            for row in loaded:
                candidates = units.get((row.get('start_time'), row.get('end_time')), [])
                position = row.get('position')
                if position:
                    index = int(position) - 1
                    if index not in candidates:
                        raise ValueError('CSV position and timestamps refer to different coding units.')
                elif len(candidates) == 1:
                    index = candidates[0]
                elif len(candidates) > 1:
                    raise ValueError('Multiple units share these timestamps. Include the original numeric position column.')
                else:
                    raise ValueError('CSV contains a unit whose timestamps do not match these subtitles.')
                if row.get('line') and row['line'] != self.subtitles[index]['text']:
                    raise ValueError('CSV subtitle text differs from this coding material.')
                if index in annotations:
                    raise ValueError('CSV contains duplicate coding units.')
                if row.get('subtitle_sha256') and row['subtitle_sha256'] != self.material['subtitle_sha256']:
                    raise ValueError('CSV was exported from different subtitle material.')
                if row.get('unit_id') and row['unit_id'] != self.material['unit_ids'][index]:
                    raise ValueError('CSV coding-unit identity does not match these subtitles.')
                annotation = {role: [name.strip() for name in row.get(role, '').split(',') if name.strip()]
                              for role in ROLES}
                for column in columns:
                    annotation[column] = row.get(column, '').strip()
                annotation['note'] = row.get('note', row.get('Note', '')).strip()
                annotation['not_applicable'] = json.loads(row.get('not_applicable') or '[]')
                if not isinstance(annotation['not_applicable'], list) or any(role not in ROLES for role in annotation['not_applicable']):
                    raise ValueError('Invalid N/A role metadata.')
                if any(annotation[role] and role in annotation['not_applicable'] for role in ROLES):
                    raise ValueError('A role cannot contain characters and also be N/A.')
                annotation['review_state'] = row.get('review_state') or review_state(annotation)
                if annotation['review_state'] not in STATES:
                    raise ValueError('Unknown review state in CSV.')
                annotation['exclusion_reason'] = row.get('exclusion_reason', '')
                if annotation['review_state'] == 'confirmed':
                    rules = json.loads(row.get('study_rules') or '{}')
                    matching = all(rules.get(key) == self.study[key] for key in ('required_roles', 'definitions', 'codebook_version'))
                    confirmation = json.loads(row.get('confirmation') or '{}')
                    if row.get('unit_id') and matching and confirmation and not missing_roles(annotation, self.study):
                        annotation['confirmation'] = confirmation
                    else:
                        annotation['review_state'] = 'needs_review'
                annotations[index] = annotation
            old = deepcopy(self.annotations)
            characters = deepcopy(self.characters)
            names = {character['name'] for character in characters}
            for annotation in annotations.values():
                for role in ROLES:
                    for name in annotation[role]:
                        if name not in names:
                            error = validate_character_name(name)
                            if error:
                                raise ValueError(error)
                            characters.append({'name': name, 'key': None})
                            names.add(name)
            ensure_character_ids(characters)
            imported = {index: normalize_annotation(annotation, characters)
                                for index, annotation in annotations.items()}
            self.characters = characters
            self.annotations = imported
            self.custom_columns = columns
            self.history = CodingHistory()
            self.audit('Import CSV', before=old, after=self.annotations, source_file=str(file_path))
            with QSignalBlocker(self.subtitle_list):
                self.setup_subtitle_list()
            self.setup_character_table(self.character_table)
            self.is_dirty = True
            self.jump_to_subtitle(self.current_subtitle_index)
            self.apply_subtitle_filters()
            self.update_progress_status()
            self.statusBar().showMessage(f'Imported {len(annotations)} units. Save Project to keep them.', 8000)
            return True
        except Exception as error:
            QMessageBox.critical(self, 'CSV import failed', str(error))
            return False

    def update_progress_status(self):
        total = len(self.subtitles)
        counts = {state: 0 for state in STATES}
        for annotation_index in range(total):
            counts[review_state(self.annotations.get(annotation_index, {}))] += 1
        saved = 'Unsaved changes' if self.is_dirty else ('Project saved' if self.vat_file else 'Project not saved yet')
        recovery = f' · Recovery: {self.last_autosave}' if self.last_autosave else ''
        self.progress_label.setText(
            f"Unit {self.current_subtitle_index + 1}/{total} · Confirmed {counts['confirmed']} · Review {counts['needs_review']} · In progress {counts['in_progress']} · Excluded {counts['excluded']} · {saved}{recovery}")
        self.update_window_title()
        self.sync_research_controls()

    def autosave_annotations(self):
        """Write a crash-recovery copy; the user's project file is only written on save."""
        if not self.is_dirty:
            return
        path = self.autosave_path
        try:
            self.record_annotation(self.current_subtitle_index, clear_selections=False)
            project_data = self._project_data(path)
            project_data[AUTOSAVE_OF_KEY] = str(Path(self.vat_file).absolute()) if self.vat_file else ""
            write_project_file(path, project_data)
            self._autosave_files.add(path)
            self.last_autosave = now()[11:19]
            self.update_progress_status()
        except Exception as e:
            # Autosave must never interrupt annotation, but a failure should be visible.
            self.statusBar().showMessage(f"Autosave failed: {e}", 10000)

    def discard_autosave(self):
        """Remove the crash-recovery copies once the work is saved or discarded."""
        for path in getattr(self, '_autosave_files', set()):
            try:
                remove_file_quietly(path)
            except OSError as e:
                self.statusBar().showMessage(f"Could not remove autosave {path}: {e}", 10000)
        if hasattr(self, '_autosave_files'):
            self._autosave_files.clear()
        self.last_autosave = ''

    def try_restore_autosave(self):
        if self._recovered_from_autosave:
            return
        path = self.autosave_path
        if not autosave_is_recoverable(path, self.vat_file):
            return
        # Offer only an autosave recorded for this very project (or unsaved session);
        # one carried in by copying a project folder names the original project.
        try:
            owner = recovery_target(path, read_project_file(path), self.srt_file)
        except (OSError, ValueError):
            owner = None  # unreadable or malformed: nothing trustworthy to restore
        if owner is None:
            return
        reply = QMessageBox.question(
            self,
            "Restore Autosave",
            f"Found unsaved work from a previous session:\n{path}\n\nRestore it now?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # This window is closed to open the recovered one; keep the file it reads.
            self._autosave_files.discard(path)
            self.request_open_project.emit(path)

    def closeEvent(self, event):
        if not self.ready:
            event.accept()
            return
        if self.is_dirty:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Save before exit?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes and not self.save_project():
                event.ignore()
                return
        # Saved, discarded, or nothing to save: the recovery copy is no longer needed.
        self.discard_autosave()
        if hasattr(self, 'autosave_timer'):
            self.autosave_timer.stop()
        self.mediaPlayer.stop()
        event.accept()

    @Slot(str)
    def handle_error(self, error):
        print(f"Error occurred: {error}")
        QMessageBox.critical(self, "Media Error", f"Error occurred: {error}")

