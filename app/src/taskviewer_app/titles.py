"""Apply new transcript titles: explicit choices precede assistant and host AI titles."""

import json

from .state import State


class Titles:
    def poll(self, state: State) -> bool:
        """Read new transcript lines of every Session. Returns True if a title changed."""
        changed = False
        for s in state.sessions.values():
            if not s.transcript_path:
                continue
            off = s.title_offset
            try:
                with open(s.transcript_path, "rb") as f:
                    f.seek(off)
                    data = f.read()
            except OSError:
                continue
            end = data.rfind(b"\n") + 1  # complete lines only
            if end:
                s.title_offset = off + end
                state.sessions_dirty = True
            ai_title = None
            for line in data[:end].splitlines():
                if b'"custom-title"' in line or b'"ai-title"' in line:
                    try:
                        e = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if e.get("type") == "custom-title" and e.get("customTitle"):
                        s.custom_title = e["customTitle"]
                    elif e.get("type") == "ai-title" and e.get("aiTitle"):
                        ai_title = e["aiTitle"]
            title = s.custom_title or s.assistant_title or ai_title
            if title and title != s.title:
                s.title = title
                state.sessions_dirty = True
                changed = True
        return changed
