import os
import subprocess
import sys

from taskviewer_board.glance import DOWN, line


def g(live=0, awaiting=0, blocked=0):
    return {"live": live, "awaiting": awaiting, "blocked": blocked}


def test_line_counts_and_hidden_zeros():
    blue = "%{F#6fa8dc}●%{F-}%{O3}"
    assert line(g(5)) == f"Tasks: {blue}5 live"
    am = lambda t: f"%{{F#e5b55c}}{t}%{{F-}}"
    assert line(g(5, blocked=1)) == am("Tasks: ") + blue + am("5 live") + am("  ") + am("⧖") + "%{O3}" + am("1 blocked")


def test_line_awaiting_colour_wins():
    out = line(g(5, 1, 2))
    assert "%{F#f0d040}1 awaiting" in out and "%{F#f0d040}2 blocked" in out and "#e5b55c" not in out


def test_line_empty_without_sessions():
    assert line(g()) == ""


def test_glance_stream(state_dir):
    from taskviewer_client import call

    proc = subprocess.Popen([sys.executable, "-c", "from taskviewer_board.glance import main; main()"],
                            stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().rstrip("\n") == DOWN  # starts the App
        assert proc.stdout.readline() == "\n"  # App up, no Sessions: module hidden
        call({"op": "register_session", "session_id": "s1", "pid": os.getpid(), "project": "/tmp"})
        assert proc.stdout.readline() == "Tasks: %{F#6fa8dc}●%{F-}%{O3}1 live\n"
    finally:
        proc.kill()

