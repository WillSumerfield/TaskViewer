"""Exercise real font measurements in a separate Qt GUI process."""
import os
import subprocess
import sys


def test_narrow_session_titles_use_full_width_and_two_lines():
    script = """
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontMetrics
from taskviewer_board.window import Rows
from taskviewer_board.layout import layout
import taskviewer_protocol as p
app = QApplication([])
rows = Rows(12)
rows.avail = 240
snap = p.SnapshotView(trees=[], sessions=[p.SessionView(
    id='s', project='/projects/CuttlefishCloudCluster', title='A very long Session title ' * 12,
    activity='awaiting', tree_id=None)])
rows.set_rows(layout(snap, False))
assert rows.rows[1].text == 'CuttlefishCloudCluster'
assert rows.rows[2].tag == ''
assert len(rows.lines[2]) == 2
assert rows.lines[2][-1].endswith('…'), rows.lines
fm = QFontMetrics(rows._font(rows.rows[2]))
_, width = rows._text_box(rows.rows[2], fm)
assert width > 120, width
assert all(fm.horizontalAdvance(line) <= width for line in rows.lines[2])
assert rows.rows[2].style == 'awaiting'
rows.wrap = False
rows.relayout()
assert len(rows.lines[2]) == 1
assert rows.lines[2][0].endswith('…')
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env={**os.environ, "QT_QPA_PLATFORM": "offscreen"}, timeout=15)
    assert result.returncode == 0, result.stderr
