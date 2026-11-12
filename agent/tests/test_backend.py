"""Backend writes are never dropped: ordered queue, latest-wins controller, disk spool and replay."""

import asyncio
import json

import httpx
import pytest

import backend as backend_mod
from backend import BackendClient


class Server:
    def __init__(self) -> None:
        self.up = True
        self.received: list[tuple[str, dict]] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.up:
            raise httpx.ConnectError("down", request=request)
        if self.status != 200:
            return httpx.Response(self.status)
        kind = request.url.path.rsplit("/", 1)[-1]
        self.received.append((kind, json.loads(request.content or b"{}")))
        return httpx.Response(200, json={})


@pytest.fixture
def spool(tmp_path, monkeypatch):
    monkeypatch.setattr(backend_mod, "spool_dir", lambda: tmp_path)
    return tmp_path


def _client(server: Server) -> BackendClient:
    client = BackendClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(server.handler))
    return client


def _no_sleep(monkeypatch):
    async def fast(_s):
        return None

    monkeypatch.setattr(backend_mod.asyncio, "sleep", fast)


def test_writes_queue_in_order_and_flush_when_back(spool, monkeypatch):
    _no_sleep(monkeypatch)
    server = Server()

    async def run():
        c = _client(server)
        server.up = False
        await c.post_transcript("abc", role="user", text="one")
        server.up = True
        await c.post_transcript("abc", role="assistant", text="two")
        await c.aclose()

    asyncio.run(run())
    assert [b["text"] for _k, b in server.received] == ["one", "two"]
    assert not list(spool.iterdir())


def test_controller_is_latest_wins_and_complete_is_not_lost(spool, monkeypatch):
    _no_sleep(monkeypatch)
    server = Server()

    async def run():
        c = _client(server)
        server.up = False
        await c.update_controller("abc", {"flow": {"step": 1}})
        await c.update_controller("abc", {"flow": {"step": 2}})
        await c.complete("abc", {"reason": "done"})
        server.up = True
        await c.flush()
        await c.aclose()

    asyncio.run(run())
    assert server.received == [("controller", {"flow": {"step": 2}}), ("complete", {"data": {"reason": "done"}})]


def test_unsent_writes_are_spooled_then_replayed_by_the_next_job(spool, monkeypatch):
    _no_sleep(monkeypatch)
    server = Server()

    async def first_job():
        c = _client(server)
        server.up = False
        await c.post_event("abc", "turn.latency", {"turn": 1})
        await c.complete("abc", {"reason": "done"})
        await c.aclose()

    asyncio.run(first_job())
    files = list(spool.glob("*.jsonl"))
    assert [f.name for f in files] == ["abc.jsonl"]
    assert server.received == []

    async def next_job():
        server.up = True
        c = _client(server)
        await c.replay_spool()
        await c.aclose()

    asyncio.run(next_job())
    assert [k for k, _b in server.received] == ["event", "complete"]
    assert not list(spool.iterdir())


def test_client_errors_are_not_retried_or_spooled(spool, monkeypatch):
    _no_sleep(monkeypatch)
    server = Server()
    server.status = 404
    calls: list[int] = []
    original = server.handler

    def counting(request):
        calls.append(1)
        return original(request)

    async def run():
        c = BackendClient()
        c._client = httpx.AsyncClient(transport=httpx.MockTransport(counting))
        await c.post_event("abc", "x", {})
        await c.aclose()

    asyncio.run(run())
    assert len(calls) == 1
    assert not list(spool.iterdir())
