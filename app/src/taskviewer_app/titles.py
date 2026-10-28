"""Session titles from the Claude transcript: latest /rename (custom-title), else latest ai-title."""

import json

from .state import State


class Titles:
    def __init__(self):
        self.offsets: dict[str, int] = {}  # session id -> bytes read
        self.custom: dict[str, str] = {}
        self.ai: dict[str, str] = {}

    def poll(self, state: State) -> bool:
        """Read new transcript lines of every Session. Returns True if a title changed."""
        changed = False
        for sid in [k for k in self.offsets if k not in state.sessions]:
            del self.offsets[sid]
            self.custom.pop(sid, None)
            self.ai.pop(sid, None)
        for s in state.sessions.values():
            if not s.transcript_path:
                continue
            off = self.offsets.get(s.id, 0)
            try:
                with open(s.transcript_path, "rb") as f:
                    f.seek(off)
                    data = f.read()
            except OSError:
                continue
            end = data.rfind(b"\n") + 1  # complete lines only
            self.offsets[s.id] = off + end
            for line in data[:end].splitlines():
                if b'"custom-title"' in line or b'"ai-title"' in line:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("type") == "custom-title" and e.get("customTitle"):
                        self.custom[s.id] = e["customTitle"]
                    elif e.get("type") == "ai-title" and e.get("aiTitle"):
                        self.ai[s.id] = e["aiTitle"]
            title = self.custom.get(s.id) or self.ai.get(s.id)
            if title and title != s.title:
                s.title = title
                state.sessions_dirty = True
                changed = True
        return changed
