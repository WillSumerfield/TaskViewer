"""The Board window: frameless, on-top, never focused; paints layout() rows."""

import json
import subprocess

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from .layout import ACTIVITY_ICON, AWAIT, STATUS_ICON, Row, layout

WIDTH, PAD, MARGIN, MAX_FRAC, OPACITY, RADIUS = 300, 10, 8, 0.8, 0.9, 10
INDENT = "  "
FONTS = ["JetBrains Mono", "DejaVu Sans Mono", "Noto Sans Math", "monospace"]  # later ones fill missing glyphs
BG = "#1e1f24"
FG = QColor("#d8dee9")
DIM = QColor("#7a8090")
COLOR = {
    "done": QColor("#8fbf7f"), "active": QColor("#6fa8dc"), "blocked": QColor("#e5b55c"),
    "awaiting": QColor("#f0d040"), "dropped": QColor("#6b7080"), "planned": FG,
    "working": DIM, "idle": DIM,
}


def focused_output() -> tuple[str, QRect]:
    """Name + usable rect of the focused i3 workspace; falls back to the cursor's screen."""
    try:
        out = subprocess.run(["i3-msg", "-t", "get_workspaces"], capture_output=True, timeout=1).stdout
        ws = next(w for w in json.loads(out) if w["focused"])
        r = ws["rect"]
        return ws["output"], QRect(r["x"], r["y"], r["width"], r["height"])
    except Exception:
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return screen.name(), screen.availableGeometry()


class Rows(QWidget):
    def __init__(self):
        super().__init__()
        self.rows: list[Row] = []
        self.font_ = QFont()
        self.font_.setFamilies(FONTS)
        self.font_.setPointSize(10)
        self.font_.setStyleHint(QFont.StyleHint.TypeWriter)
        self.italic = QFont(self.font_)
        self.italic.setItalic(True)
        self.bold_italic = QFont(self.italic)
        self.bold_italic.setBold(True)
        fm = QFontMetrics(self.font_)
        self.lh = fm.height() + 3
        self.cw = fm.horizontalAdvance("M")
        bold = QFontMetrics(self.bold_italic)  # fallback glyphs (⚠ ⧖) can be wider than a cell
        icons = [*STATUS_ICON.values(), *ACTIVITY_ICON.values()]
        self.iw = max(max(fm.horizontalAdvance(i), bold.horizontalAdvance(i)) for i in icons) + self.cw // 2
        self._drag: QPoint | None = None

    def set_rows(self, rows: list[Row]):
        self.rows = rows
        self.setFixedHeight(2 * PAD + len(rows) * self.lh)
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        w = self.width() - 2 * PAD
        for i, r in enumerate(self.rows):
            y = PAD + i * self.lh
            box = lambda x, width: QRect(x, y, width, self.lh)
            if r.kind == "project":
                qp.setFont(self.font_)
                qp.setPen(DIM)
                label = f"── {r.text} "
                qp.drawText(box(PAD, w), Qt.AlignmentFlag.AlignVCenter, label + "─" * (w // self.cw))
                continue
            font = self.font_
            pen = COLOR.get(r.style, FG)
            if r.kind == "session":
                font = self.bold_italic if r.style == "awaiting" else self.italic
            elif r.kind == "note":
                pen = DIM
            qp.setFont(font)
            fm = QFontMetrics(font)
            x = PAD + (len(INDENT) * r.indent + 1) * self.cw
            tag_w = fm.horizontalAdvance(r.tag) + self.cw if r.tag else 0
            if r.icon:
                qp.setPen(pen)
                qp.drawText(box(x, self.iw), Qt.AlignmentFlag.AlignVCenter, r.icon)
                x += self.iw
            qp.setPen(pen if r.kind == "session" or r.style == "awaiting" else FG if r.kind == "task" else DIM)
            text = fm.elidedText(r.text, Qt.TextElideMode.ElideRight, PAD + w - tag_w - x)
            qp.drawText(box(x, PAD + w - x), Qt.AlignmentFlag.AlignVCenter, text)
            if r.tag:
                qp.setPen(COLOR["awaiting"] if r.tag == AWAIT else DIM)
                qp.drawText(box(PAD, w), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, r.tag)

    # drag anywhere; the Board keeps the spot per monitor until restart
    def mousePressEvent(self, e):
        self._drag = e.globalPosition().toPoint() - self.window().pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.window().move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.window().remember_position()

    def mouseDoubleClickEvent(self, e):
        self.window().command("collapse")


class Bridge(QObject):
    """Carries feed-thread callbacks onto the Qt thread."""
    snapshot = Signal(object)
    down = Signal()


class Board(QWidget):
    """Rounded dark panel (needs a compositor for clean corners) holding the scrollable rows."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("TaskViewer")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(OPACITY)
        self.setFixedWidth(WIDTH)
        scroll = QScrollArea()
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        self.inner = Rows()
        scroll.setWidget(self.inner)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(scroll)
        self.wanted = False
        self.collapsed = False
        self.snap = None
        self.app_down = False
        self.output = ""
        self.limit = 600
        self.dragged: dict[str, QPoint] = {}
        self.placed = QPoint()

    def paintEvent(self, _):
        qp = QPainter(self)
        qp.setRenderHint(QPainter.RenderHint.Antialiasing)
        qp.setPen(Qt.PenStyle.NoPen)
        qp.setBrush(QColor(BG))
        qp.drawRoundedRect(self.rect(), RADIUS, RADIUS)

    def command(self, cmd: str):
        if cmd == "toggle":
            self.wanted = not self.wanted
            if self.wanted:
                self.place()
        elif cmd == "collapse":
            self.collapsed = not self.collapsed
        self.refresh()

    def on_snapshot(self, snap):
        self.snap, self.app_down = snap, False
        self.refresh()

    def on_down(self):
        self.app_down = True
        self.refresh()

    def rows(self) -> list[Row]:
        if self.app_down:
            return [Row("note", "App not running")]
        return layout(self.snap, self.collapsed) if self.snap else []

    def refresh(self):
        rows = self.rows()
        self.inner.set_rows(rows)
        self.setFixedHeight(min(self.inner.height(), self.limit))
        if self.wanted and rows:
            if not self.isVisible():
                self.show()
                self.move(self.pos())  # some WMs ignore the pre-map position
        else:
            self.hide()

    def place(self):
        self.output, rect = focused_output()
        self.limit = int(rect.height() * MAX_FRAC)
        top_right = QPoint(rect.right() - WIDTH - MARGIN, rect.top() + MARGIN)
        self.move(self.dragged.get(self.output, top_right))
        self.placed = self.pos()

    def remember_position(self):
        if self.pos() != self.placed:  # a plain click isn't a drag
            self.dragged[self.output] = self.pos()
