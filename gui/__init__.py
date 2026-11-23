"""PyQt6 graphical user interface for the assistant application."""

__all__ = ["AssistantApp", "MainWindow"]


def __getattr__(name: str):
    if name == "AssistantApp":
        from .app import AssistantApp
        return AssistantApp
    if name == "MainWindow":
        from .main_window import MainWindow
        return MainWindow
    raise AttributeError(name)
