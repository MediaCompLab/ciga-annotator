import re

with open('annotator.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Match VideoAnnotator class until def main()
start = text.find('class VideoAnnotator(')
end = text.find('def main():')

anim_text = text[start:end]

imports = """import csv
import json
import os
import tempfile
from pathlib import Path
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QLabel,
    QFileDialog, QPushButton, QLineEdit, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QSizePolicy, QMessageBox, QHeaderView,
    QSplitter, QAbstractItemView, QSlider
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtCore import Qt, QUrl, Slot, Signal, QEvent, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence

from src.core.app_settings import AppSettings
from src.ui.settings_dialog import SettingsDialog
from src.ui.char_dialog import ManageCharactersDialog
from src.core.parsers import parse_srt, milliseconds_to_srt_time
from src.core.characters import read_characters, save_characters
from src.core.csv_utils import write_rows_to_csv_atomic

"""

with open('src/ui/annotator_window.py', 'w', encoding='utf-8') as f:
    f.write(imports + anim_text)

