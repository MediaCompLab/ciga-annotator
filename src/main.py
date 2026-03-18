import sys
from PySide6.QtWidgets import QApplication

from src.ui.setup_window import MainWindow
from src.ui.annotator_window import VideoAnnotator

def main():
    app = QApplication(sys.argv)
    app.main_window = MainWindow()
    app.main_window.show()

    def start_annotation(video_file, srt_file, char_file, vat_file):
        if hasattr(app, 'video_annotator') and app.video_annotator:
            app.removeEventFilter(app.video_annotator)
            app.video_annotator.close()
            
        app.video_annotator = VideoAnnotator(video_file, srt_file, char_file, vat_file)
        # Hook up "New Project" signal from main window to reset
        app.video_annotator.request_new_project.connect(reset_to_main_window)
        app.video_annotator.request_open_project.connect(lambda f: start_annotation("", "", "", f))
        app.video_annotator.show()
        app.main_window.hide()
        app.installEventFilter(app.video_annotator)

    def reset_to_main_window():
        app.removeEventFilter(app.video_annotator)
        app.video_annotator.close()
        app.video_annotator = None
        app.main_window.show()

    app.main_window.start_annotation.connect(start_annotation)
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
