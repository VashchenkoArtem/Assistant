import sys

from PyQt6.QtWidgets import QApplication

from .main_window import MainWindow


class AssistantApp:
    """Application bootstrap for the PyQt6 interface."""

    def __init__(self, argv: list[str] | None = None) -> None:
        self.qt_app = QApplication.instance() or QApplication(argv or sys.argv)
        self.window = MainWindow()

    def run(self) -> int:
        self.window.show()
        return self.qt_app.exec()


def main() -> int:
    app = AssistantApp()
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())
