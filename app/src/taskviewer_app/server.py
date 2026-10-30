"""Localhost TCP server: JSON-line requests in, replies + subscribed push events out."""

import asyncio
from collections.abc import Callable

import msgspec

import taskviewer_protocol as p

from .liveness import is_alive
from .state import OpError, State
from .storage import Storage
from .titles import Titles

# Ops that never change state (skip flush + broadcast)
READ_OPS = (p.ListCandidates, p.GetTree, p.Snapshot)


def _raw_id(line: bytes) -> int:
    try:
        rid = msgspec.json.decode(line).get("id", 0)
        return rid if isinstance(rid, int) else 0
    except (msgspec.DecodeError, AttributeError):
        return 0


class Server:
    def __init__(self, state: State, storage: Storage,
                 alive: Callable[[int, float], bool] = is_alive, sweep_secs: float = 3.0):
        self.state = state
        self.storage = storage
        self.alive = alive
        self.sweep_secs = sweep_secs
        self.titles = Titles()
        self.subs: dict[asyncio.StreamWriter, set[str]] = {}
        self._fresh: set[asyncio.StreamWriter] = set()  # subscribed, initial push pending
        self.on_change: list[Callable[[], None]] = []  # in-process listeners (Board, phase 3)
        self._server: asyncio.Server | None = None
        self._sweeper: asyncio.Task | None = None

    async def start(self, port: int = 0) -> int:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
        port = self._server.sockets[0].getsockname()[1]
        self.storage.write_port(port)
        self._sweeper = asyncio.create_task(self._sweep_loop())
        return port

    async def stop(self):
        if self._sweeper:
            self._sweeper.cancel()
        if self._server:
            self._server.close()
        for w in list(self.subs):
            w.close()

    def _changed(self):
        self.storage.flush(self.state)
        for cb in self.on_change:
            cb()
        if not self.subs:
            return
        glance = p.encode(p.GlanceEvent(glance=self.state.glance()))
        snap = p.encode(p.StateEvent(snapshot=self.state.snapshot())) \
            if any("state" in t for t in self.subs.values()) else b""
        for w, topics in list(self.subs.items()):
            if w.is_closing():
                del self.subs[w]
                continue
            if "glance" in topics:
                w.write(glance)
            if "state" in topics:
                w.write(snap)

    async def _sweep_loop(self):
        while True:
            await asyncio.sleep(self.sweep_secs)
            changed = self.state.sweep(self.alive)
            if self.titles.poll(self.state) or changed:
                self._changed()
            elif self.state.sessions_dirty:
                # Transcript progress must survive restart even when the visible title is unchanged.
                self.storage.flush(self.state)

    def handle_line(self, line: bytes, writer: asyncio.StreamWriter | None = None) -> p.Reply:
        try:
            req = p.decode_request(line)
        except msgspec.DecodeError as e:
            return p.Reply(id=_raw_id(line), ok=False, error=f"bad request: {e}")
        if isinstance(req, p.Subscribe):
            if writer is not None:
                self.subs[writer] = set(req.topics)
                self._fresh.add(writer)
            return p.Reply(id=req.id, ok=True)
        if isinstance(req, p.SetTitle):
            # Apply earlier transcript choices before the new title operation.
            self.titles.poll(self.state)
        try:
            result, warnings = self.state.apply(req)
        except OpError as e:
            return p.Reply(id=req.id, ok=False, error=str(e))
        if not isinstance(req, READ_OPS):
            self._changed()
        return p.Reply(id=req.id, ok=True, result=result, warnings=warnings)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while line := await reader.readline():
                reply = self.handle_line(line, writer)
                writer.write(p.encode(reply))
                if writer in self._fresh:  # push current state right after subscribing
                    self._fresh.discard(writer)
                    topics = self.subs[writer]
                    if "glance" in topics:
                        writer.write(p.encode(p.GlanceEvent(glance=self.state.glance())))
                    if "state" in topics:
                        writer.write(p.encode(p.StateEvent(snapshot=self.state.snapshot())))
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            self.subs.pop(writer, None)
            self._fresh.discard(writer)
            writer.close()
