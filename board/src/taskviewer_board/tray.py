"""Tray Glance (Windows): a painted dot with the Session count; tooltip = Glance text."""

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .glance import DIM, LIVE, colour, plain

SIZE = 64


def icon(fill: str, count: str) -> QIcon:
    pm = QPixmap(SIZE, SIZE)
    pm.fill(Qt.GlobalColor.transparent)
    qp = QPainter(pm)
    qp.setRenderHint(QPainter.RenderHint.Antialiasing)
    qp.setPen(Qt.PenStyle.NoPen)
    qp.setBrush(QColor(fill))
    qp.drawEllipse(2, 2, SIZE - 4, SIZE - 4)
    if count:
        f = QFont("Segoe UI")
        f.setBold(True)
        f.setPixelSize(SIZE * 2 // 3 if len(count) == 1 else SIZE // 2)
        qp.setFont(f)
        qp.setPen(QColor("#1e1f24"))
        qp.drawText(QRect(0, 0, SIZE, SIZE), Qt.AlignmentFlag.AlignCenter, count)
    qp.end()
    return QIcon(pm)


class Tray(QSystemTrayIcon):
    def __init__(self, board, quit_):
        super().__init__()
        self.board = board
        menu = QMenu()
        for label, cmd in (("Collapse/Expand all", "collapse"), ("Reload config", "reload")):
            act = QAction(label, menu)
            act.triggered.connect(lambda _=False, c=cmd: board.command(c))
            menu.addAction(act)
        menu.addSeparator()
        act = QAction("Quit Board", menu)
        act.triggered.connect(quit_)
        menu.addAction(act)
        self.menu = menu  # keep a reference
        self.setContextMenu(menu)
        self.activated.connect(self.on_click)
        self.on_down()
        self.show()

    def on_click(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # left click
            self.board.command("toggle")

    def on_glance(self, g: dict):
        n = g["live"]
        self.setIcon(icon(colour(g) or LIVE, str(n) if n < 100 else "99+"))
        self.setToolTip(plain(g))

    def on_down(self):
        self.setIcon(icon(DIM, ""))
        self.setToolTip("Tasks: App down")
