from datetime import datetime

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .chat_widgets import ChatCard
from .icons import icon_path


STYLE = """
#chatScroll, #chatViewport {
    background: #080e1d;
    border: none;
}
QScrollBar:vertical {
    border: none;
    background: #080e1d;
    width: 6px;
}
QScrollBar::handle:vertical {
    background: #1a2340;
    border-radius: 3px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    background: #080e1d;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
ChatCard { border-radius: 7px; }
#assistantCard { background: transparent; }
#userCard { background: #30384b; }
#userCard QLabel, #assistantCard QLabel {
    background: transparent;
    border: none;
}
#cardIcon { color: #9ba5bd; font-size: 15px; }
#messageAuthor { color: #747c96; font-size: 12px; }
#messageBody { color: #788199; font-size: 11px; }
#messageTime { color: #46516b; font-size: 9px; }
#messageStatus { color: #5167c6; font-size: 10px; }
"""


class ChatPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setStyleSheet(STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("chatScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        viewport = QWidget()
        viewport.setObjectName("chatViewport")
        self.chat_layout = QVBoxLayout(viewport)
        self.chat_layout.setContentsMargins(16, 10, 16, 16)
        self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()

        self.scroll.setWidget(viewport)
        layout.addWidget(self.scroll, 1)

    def add_card(
        self,
        author: str,
        body: str,
        is_user: bool = False,
        status: str | None = None,
    ) -> ChatCard:
        icon_name = "user_ico.svg" if is_user else "bot_ico.svg"
        if author == "System":
            icon_name = "info.svg"
        card = ChatCard(
            author,
            body.strip(),
            datetime.now().strftime("%H:%M"),
            str(icon_path(icon_name)),
            is_user=is_user,
            status=status,
            status_icon=str(icon_path("status.svg")) if status else None,
        )
        insert_at = max(0, self.chat_layout.count() - 1)
        self.chat_layout.insertWidget(insert_at, card)
        self.scroll_to_bottom()
        return card

    def scroll_to_bottom(self) -> None:
        self.chat_layout.activate()
        scrollbar = self.scroll.verticalScrollBar()
        if scrollbar is not None:
            scrollbar.setValue(scrollbar.maximum())
            QTimer.singleShot(0, lambda: scrollbar.setValue(scrollbar.maximum()))
            QTimer.singleShot(50, lambda: scrollbar.setValue(scrollbar.maximum()))
            QTimer.singleShot(150, lambda: scrollbar.setValue(scrollbar.maximum()))
