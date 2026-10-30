"""Integration: real TCP server, scripted Session, subscriber receives pushes."""

import asyncio
import json

import taskviewer_protocol as p
from taskviewer_app.server import Server
from taskviewer_app.state import State
from taskviewer_app.storage import Storage


class Client:
    def __init__(self, reader, writer):
        self.r, self.w, self.n = reader, writer, 0

    async def call(self, op: str, **kw) -> dict:
        self.n += 1
        self.w.write(json.dumps({"op": op, "id": self.n, **kw}).encode() + b"\n")
        await self.w.drain()
        reply = json.loads(await self.r.readline())
        assert reply["id"] == self.n
        return reply

    async def next(self) -> dict:
        return json.loads(await asyncio.wait_for(self.r.readline(), 2))


async def connect(port: int) -> Client:
    return Client(*await asyncio.open_connection("127.0.0.1", port))


def test_end_to_end(tmp_path):
    async def go():
        server = Server(State(), Storage(tmp_path), alive=lambda pid, s: True, sweep_secs=0.05)
        port = await server.start()
        assert Storage(tmp_path).read_port() == port

        sub = await connect(port)
        assert (await sub.call("subscribe", topics=["glance"]))["ok"]
        first = await sub.next()
        assert first == {"event": "glance", "glance": {"live": 0, "awaiting": 0, "blocked": 0}}

        c = await connect(port)
        assert (await c.call("register_session", session_id="s1", pid=1, pid_start=0.0, project="/p"))["ok"]
        assert (await sub.next())["glance"]["live"] == 1

        tree = (await c.call("create_tree", session_id="s1", goal="Create task app"))["result"]["tree_id"]
        await sub.next()
        t2 = (await c.call("add_task", parent_id=tree, goal="App display", status="blocked"))["result"]["task_id"]
        assert (await sub.next())["glance"]["blocked"] == 1

        r = await c.call("set_status", task_id=t2, status="done")
        assert r["ok"] and any("still active" in w for w in r["warnings"])
        await sub.next()

        r = await c.call("get_tree", session_id="s1")
        assert r["result"]["root"]["children"][0] == {"id": t2, "goal": "App display", "status": "done", "children": []}

        r = await c.call("set_status", task_id="t999", status="done")
        assert not r["ok"] and "unknown task" in r["error"]

        r = await c.call("bogus")
        assert not r["ok"]

        # reads don't push
        await c.call("snapshot")
        await c.call("set_activity", session_id="s1", activity="awaiting")
        assert (await sub.next())["glance"]["awaiting"] == 1

        assert (tmp_path / "trees" / f"{tree}.json").exists()
        await server.stop()

    asyncio.run(go())


def test_sweep_pushes_dead_session(tmp_path):
    async def go():
        alive = {"ok": True}
        server = Server(State(), Storage(tmp_path), alive=lambda pid, s: alive["ok"], sweep_secs=0.05)
        port = await server.start()
        c = await connect(port)
        await c.call("register_session", session_id="s1", pid=1, pid_start=0.0, project="/p")
        sub = await connect(port)
        await sub.call("subscribe", topics=["state"])
        assert len((await sub.next())["snapshot"]["sessions"]) == 1
        alive["ok"] = False
        ev = await sub.next()
        assert ev["event"] == "state" and ev["snapshot"]["sessions"] == []
        await server.stop()

    asyncio.run(go())


def test_sweep_persists_transcript_progress_without_title_change(tmp_path):
    async def go():
        state = State()
        transcript = tmp_path / "titles.jsonl"
        transcript.write_text(json.dumps({"type": "ai-title", "aiTitle": "Host title"}) + "\n")
        server = Server(state, Storage(tmp_path), alive=lambda pid, s: True, sweep_secs=0.01)
        await server.start()
        try:
            state.apply(p.RegisterSession(session_id="s1", pid=1, pid_start=0.0,
                                          project="/p", transcript_path=str(transcript)))
            state.apply(p.SetTitle(session_id="s1", title="User title"))
            server.storage.flush(state)

            async def persisted():
                while True:
                    fresh = State()
                    server.storage.load(fresh)
                    if fresh.sessions["s1"].title_offset == transcript.stat().st_size:
                        assert fresh.sessions["s1"].title == "User title"
                        return
                    await asyncio.sleep(0.01)

            await asyncio.wait_for(persisted(), 2)
        finally:
            await server.stop()

    asyncio.run(go())


def test_explicit_title_wins_over_unread_transcript_title(tmp_path):
    transcript = tmp_path / "titles.jsonl"
    transcript.write_text(json.dumps({"type": "custom-title", "customTitle": "Old title"}) + "\n")
    state = State()
    state.apply(p.RegisterSession(session_id="s1", pid=1, pid_start=0.0,
                                  project="/p", transcript_path=str(transcript)))
    server = Server(state, Storage(tmp_path))
    reply = server.handle_line(p.encode(p.SetTitle(session_id="s1", title="New title")))
    assert reply.ok
    assert state.sessions["s1"].title == "New title"
    assert not server.titles.poll(state)
    fresh = State()
    server.storage.load(fresh)
    assert fresh.sessions["s1"].title == "New title"


def test_one_app_per_state_dir(tmp_path):
    """Many launches at once (login) leave exactly one App running."""
    import subprocess
    import sys
    import time

    cmd = [sys.executable, "-c", "import sys; from taskviewer_app.main import main; sys.argv[1:] = "
           f"['--state-dir', {str(tmp_path)!r}]; main()"]
    procs = [subprocess.Popen(cmd, stdout=subprocess.DEVNULL) for _ in range(6)]
    try:
        time.sleep(3)
        assert sum(p.poll() is None for p in procs) == 1
    finally:
        for p in procs:
            p.kill()
