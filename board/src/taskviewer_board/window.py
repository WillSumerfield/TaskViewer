"""The Board window: frameless, on-top, never focused; paints layout() rows."""

import json
import subprocess

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from . import config
from .config import Config, Rect
from .layout import ACTIVITY_ICON, AWAIT, STATUS_ICON, Row, layout

PAD, RADIUS = 10, 10
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


def outputs() -> tuple[dict[str, Rect], str]:
    """Usable rect of each output's visible i3 workspace + the focused output; falls back to Qt screens."""
    try:
        out = subprocess.run(["i3-msg", "-t", "get_workspaces"], capture_output=True, timeout=1).stdout
        ws = [w for w in json.loads(out) if w["visible"]]
        rects = {w["output"]: tuple(w["rect"][k] for k in ("x", "y", "width", "height")) for w in ws}
        return rects, next(w["output"] for w in ws if w["focused"])
    except Exception:
        rects = {sc.name(): sc.availableGeometry().getRect() for sc in QGuiApplication.screens()}
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        return rects, screen.name()


class Rows(QWidget):
    def __init__(self, font_size: int):
        super().__init__()
        self.rows: list[Row] = []
        self.ys: list[int] = []
        self._drag: QPoint | None = None
        self.set_font_size(font_size)

    def set_font_size(self, font_size: int):
        self.font_ = QFont()
        self.font_.setFamilies(FONTS)
        self.font_.setPointSize(font_size)
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

    def set_rows(self, rows: list[Row]):
        self.rows = rows
        self.ys = []  # top of each row; Project headers after the first get a small gap above
        y = PAD
        for i, r in enumerate(rows):
            y += self.lh // 3 if r.kind == "project" and i else 0
            self.ys.append(y)
            y += self.lh
        self.setFixedHeight(y + PAD)
        self.update()

    def paintEvent(self, _):
        qp = QPainter(self)
        w = self.width() - 2 * PAD
        for y, r in zip(self.ys, self.rows):
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

    def __init__(self, cfg: Config):
        super().__init__()
        self.setWindowTitle("TaskViewer")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.WindowDoesNotAcceptFocus | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        scroll = QScrollArea()
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(True)
        self.inner = Rows(cfg.font_size)
        scroll.setWidget(self.inner)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(scroll)
        self.wanted = False
        self.collapsed = False
        self.snap = None
        self.app_down = False
        self.output = ""
        self.out_rect: Rect | None = None
        self.limit = 600
        self.dragged: dict[str, QPoint] = {}
        self.placed = QPoint()
        self.apply(cfg)

    def apply(self, cfg: Config):
        """Use a (re)loaded config; dragged spots are kept."""
        self.cfg = cfg
        self.setWindowOpacity(cfg.opacity)
        self.setFixedWidth(cfg.width)
        self.inner.set_font_size(cfg.font_size)
        if self.out_rect is not None:
            self.place()

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
        elif cmd == "reload":
            self.apply(config.load())
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
        self.reposition()  # bottom/center anchors move as the height changes
        if self.wanted and rows:
            if not self.isVisible():
                self.show()
                self.move(self.pos())  # some WMs ignore the pre-map position
        else:
            self.hide()

    def place(self):
        """Pick the output on each show: the configured one if plugged in, else focused."""
        rects, focused = outputs()
        self.output = config.pick_output(self.cfg.monitor, rects, focused)
        self.out_rect = rects[self.output]
        self.limit = int(self.out_rect[3] * self.cfg.max_height)
        self.reposition()

    def reposition(self):
        if self.out_rect is None or self.inner._drag is not None:
            return
        if self.output in self.dragged:
            self.move(self.dragged[self.output])
        else:
            self.move(*config.place(self.out_rect, (self.width(), self.height()), self.cfg))
        self.placed = self.pos()

    def remember_position(self):
        if self.pos() != self.placed:  # a plain click isn't a drag
            self.dragged[self.output] = self.pos()
