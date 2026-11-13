from typing import NamedTuple


class ExplorerTab(NamedTuple):
    path: str
    name: str
    hwnd: int
    tab_index: int


class ExplorerWindow(NamedTuple):
    hwnd: int
    tabs: tuple[ExplorerTab, ...]
