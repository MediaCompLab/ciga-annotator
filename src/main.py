import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from src.ui.setup_window import MainWindow
from src.ui.annotator_window import VideoAnnotator

def get_resource_path(filename):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(repo_root, "assets", filename)

def main():
    app = QApplication(sys.argv)

    # Set Logo based on dark/light mode
    is_dark = app.palette().window().color().lightness() < 128
    logo_filename = "logo_white.png" if is_dark else "logo_black.png"
    logo_path = get_resource_path(logo_filename)
    
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    app.main_window = MainWindow()
    app.main_window.show()

    def close_annotator():
        """Close the current annotator; False if the user cancelled at the save prompt."""
        annotator = getattr(app, 'video_annotator', None)
        if annotator is None:
            return True
        if not annotator.close():
            return False
        app.removeEventFilter(annotator)
        app.video_annotator = None
        return True

    def start_annotation(video_file, srt_file, char_file, vat_file):
        if not close_annotator():
            return

        app.video_annotator = VideoAnnotator(video_file, srt_file, char_file, vat_file)
        # Hook up "New Project" signal from main window to reset
        app.video_annotator.request_new_project.connect(reset_to_main_window)
        app.video_annotator.request_open_project.connect(lambda f: start_annotation("", "", "", f))
        app.video_annotator.show()
        app.main_window.hide()
        app.installEventFilter(app.video_annotator)

    def reset_to_main_window():
        if close_annotator():
            app.main_window.show()

    app.main_window.start_annotation.connect(start_annotation)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
