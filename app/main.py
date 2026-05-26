import sys
import os
from PyQt6.QtWidgets import QApplication
from app.services.storage import init_db


def main():
    os.makedirs("storage", exist_ok=True)
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("Research Map Agent")
    app.setOrganizationName("ResearchMap")
    app.setStyle("Fusion")

    from app.ui.main_window import MainWindow

    window = MainWindow()
    window.resize(1400, 850)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
