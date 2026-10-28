"""Speech arbiter: one in-flight agent utterance; fillers yield to Director."""

import asyncio
import logging

from interview.speech import SpeechArbiter, interrupt_handle, source_for_move


class FakeHandle:
    def __init__(self) -> None:
        self.interrupt_calls = 0
        self.interrupted = False
        self._done = asyncio.Event()

    def interrupt(self, force: bool = False) -> FakeHandle:
        self.interrupt_calls += 1
        self.interrupted = True
        self._done.set()
        return self

    async def wait_for_playout(self) -> None:
        await self._done.wait()

    def finish(self) -> None:
        self._done.set()


def test_source_for_move_maps_silence_kinds():
    assert source_for_move("silence_nudge") == "silence"
    assert source_for_move("silence_end") == "silence"
    assert source_for_move("opening") == "director"
    assert source_for_move("ask") == "director"


def test_interrupt_handle_uses_force_then_plain():
    class ForceOnly:
        def __init__(self) -> None:
            self.calls = []

        def interrupt(self, force: bool = False) -> None:
            self.calls.append(force)

    h = ForceOnly()
    interrupt_handle(h)
    assert h.calls == [True]

    class Plain:
        def __init__(self) -> None:
            self.n = 0

        def interrupt(self) -> None:
            self.n += 1

    p = Plain()
    interrupt_handle(p)
    assert p.n == 1
    interrupt_handle(None)


def test_filler_rejected_while_director_plays():
    async def run():
        arb = SpeechArbiter()
        director = FakeHandle()
        filler = FakeHandle()
        assert await arb.play("director", lambda: director, wait=False) is True
        assert arb.current_source == "director"
        assert await arb.play("filler", lambda: filler, wait=False) is False
        assert filler.interrupt_calls == 0
        director.finish()
        await asyncio.sleep(0.02)
        assert arb.busy() is False

    asyncio.run(run())


def test_watchdog_rejected_while_director_plays():
    async def run():
        arb = SpeechArbiter()
        director = FakeHandle()
        assert await arb.play("director", lambda: director, wait=False) is True
        starts = []
        assert await arb.play("watchdog", lambda: starts.append("wd") or FakeHandle(), wait=False) is False
        assert starts == []
        director.finish()
        await asyncio.sleep(0.02)

    asyncio.run(run())


def test_director_preempts_filler(caplog):
    async def run():
        arb = SpeechArbiter()
        filler = FakeHandle()
        director = FakeHandle()
        caplog.set_level(logging.INFO, logger="interview-v2.speech")
        assert await arb.play("filler", lambda: filler, wait=False, detail="ack") is True
        assert await arb.play("director", lambda: director, wait=False, detail="ask") is True
        assert filler.interrupted is True
        assert arb.current_source == "director"
        text = caplog.text
        assert "speech.start source=filler" in text
        assert "speech.preempted current=filler by=director" in text
        assert "speech.start source=director" in text
        director.finish()
        await asyncio.sleep(0.02)
        assert arb.busy() is False

    asyncio.run(run())


def test_silence_queues_behind_director():
    async def run():
        arb = SpeechArbiter()
        director = FakeHandle()
        silence = FakeHandle()
        order: list[str] = []
        assert await arb.play("director", lambda: director, wait=False) is True

        async def _silence():
            order.append("silence-enter")
            ok = await arb.play("silence", lambda: silence, wait=False)
            order.append("silence-ok" if ok else "silence-no")

        task = asyncio.create_task(_silence())
        await asyncio.sleep(0.02)
        assert "silence-ok" not in order
        assert arb.current_source == "director"
        director.finish()
        await task
        assert order[-1] == "silence-ok"
        assert arb.current_source == "silence"
        silence.finish()
        await asyncio.sleep(0.02)
        assert arb.busy() is False

    asyncio.run(run())


def test_second_filler_does_not_overlap_first():
    async def run():
        arb = SpeechArbiter()
        first = FakeHandle()
        second = FakeHandle()
        assert await arb.play("filler", lambda: first, wait=False) is True
        assert await arb.play("filler", lambda: second, wait=False) is False
        assert second.interrupt_calls == 0
        first.finish()
        await asyncio.sleep(0.02)

    asyncio.run(run())


def test_verbatim_preempts_filler_like_director():
    async def run():
        arb = SpeechArbiter()
        filler = FakeHandle()
        verbatim = FakeHandle()
        await arb.play("filler", lambda: filler, wait=False)
        await arb.play("verbatim", lambda: verbatim, wait=False)
        assert filler.interrupted is True
        assert arb.current_source == "verbatim"
        verbatim.finish()
        await asyncio.sleep(0.02)

    asyncio.run(run())
