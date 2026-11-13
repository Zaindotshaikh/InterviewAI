"""HMAC-authenticated client for Express /api/v2/internal endpoints.

Writes (transcript, event, controller, complete) are never dropped:
  - sent in order; once one fails, later writes queue behind it so the transcript stays in order;
  - controller patches are latest-wins (only the newest flow state matters for resume);
  - whatever is still queued when the job ends is spooled to disk and replayed by the next job.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger("interview-v2.backend")

_DEFAULT_SPOOL = Path(__file__).resolve().parent / ".spool"
_STALE_CLAIM_S = 600.0


class _ClientError(Exception):
    """4xx other than 408/429: retrying cannot succeed."""


def spool_dir() -> Path:
    raw = (getattr(get_settings(), "backend_spool_dir", "") or "").strip()
    return Path(raw) if raw else _DEFAULT_SPOOL


class BackendClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.backend_url.rstrip("/")
        self.secret = settings.v2_internal_secret
        # (method, path, body, latest-wins key or None)
        self._queue: list[tuple[str, str, dict[str, Any], str | None]] = []
        self._flush_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(timeout=15.0)

    def _headers(self, body: dict[str, Any] | None = None) -> dict[str, str]:
        payload = json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False)
        ts = str(int(time.time() * 1000))
        sig = hmac.new(
            self.secret.encode("utf-8"),
            f"{ts}.{payload}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "x-v2-timestamp": ts,
            "x-v2-signature": sig,
            "Authorization": f"Bearer {self.secret}",
        }

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        url = f"{self.base}{path}"
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                headers = self._headers(body if method.upper() != "GET" else None)
                if method.upper() == "GET":
                    resp = await self._client.get(url, headers=headers)
                else:
                    resp = await self._client.request(
                        method,
                        url,
                        headers=headers,
                        content=json.dumps(body or {}, ensure_ascii=False).encode("utf-8"),
                    )
                if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                    raise _ClientError(f"{resp.status_code} for {path}")
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                if not resp.content:
                    return {}
                return resp.json()
            except _ClientError:
                raise
            except Exception as err:  # noqa: BLE001
                last_err = err
                if attempt + 1 < retries:
                    await asyncio.sleep(0.4 * (attempt + 1))
        assert last_err is not None
        raise last_err

    # ------------------------------------------------------------------------------------- write path

    def _enqueue(self, method: str, path: str, body: dict[str, Any], key: str | None) -> None:
        if key is not None:
            self._queue = [item for item in self._queue if item[3] != key]
        self._queue.append((method, path, body, key))

    async def _send(self, method: str, path: str, body: dict[str, Any], *, key: str | None = None) -> bool:
        """Send now, or queue behind earlier failures. True when this write reached the server."""
        if self._queue:
            self._enqueue(method, path, body, key)
            await self.flush(retries=1)
            return not self._queue
        try:
            await self._request(method, path, body)
            return True
        except _ClientError as err:
            logger.error("backend rejected %s: %s", path, err)
            return False
        except Exception as err:  # noqa: BLE001
            logger.warning("backend write failed, queued: %s (%s)", path, type(err).__name__)
            self._enqueue(method, path, body, key)
            return False

    async def flush(self, retries: int = 3) -> None:
        """Send queued writes in order. Stops at the first failure so nothing overtakes it."""
        async with self._flush_lock:
            while self._queue:
                method, path, body, _key = self._queue[0]
                try:
                    await self._request(method, path, body, retries=retries)
                except _ClientError as err:
                    logger.error("backend rejected queued %s: %s; dropped", path, err)
                except Exception as err:  # noqa: BLE001
                    logger.warning("flush stopped at %s (%s); %d queued", path, type(err).__name__, len(self._queue))
                    return
                self._queue.pop(0)

    # ------------------------------------------------------------------------------------- endpoints

    async def fetch_plan(self, interview_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/v2/internal/interviews/{interview_id}/plan")

    async def post_transcript(
        self,
        interview_id: str,
        *,
        role: str,
        text: str,
        turn_index: int | None = None,
        timestamp: str | None = None,
        llm_text: str | None = None,
        interrupted: bool | None = None,
        move: str | None = None,
    ) -> None:
        body: dict[str, Any] = {"role": role, "text": text}
        if turn_index is not None:
            body["turnIndex"] = turn_index
        if timestamp:
            body["timestamp"] = timestamp
        if llm_text is not None:
            body["llmText"] = llm_text
        if interrupted is not None:
            body["interrupted"] = bool(interrupted)
        if move:
            body["move"] = move
        await self._send("POST", f"/api/v2/internal/interviews/{interview_id}/transcript", body)

    async def post_trace(self, interview_id: str, body: dict[str, Any]) -> None:
        """Best-effort private case file. A failure here must not block the transcript queue."""
        path = f"/api/v2/internal/interviews/{interview_id}/trace"
        try:
            await self._request("POST", path, body, retries=2)
        except Exception as err:  # noqa: BLE001
            logger.warning("trace write skipped (%s)", type(err).__name__)

    async def post_event(self, interview_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
        body = {"type": event_type, "data": data or {}}
        await self._send("POST", f"/api/v2/internal/interviews/{interview_id}/event", body)

    async def update_controller(self, interview_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        path = f"/api/v2/internal/interviews/{interview_id}/controller"
        if not self._queue:
            try:
                return await self._request("POST", path, patch)
            except _ClientError as err:
                logger.error("backend rejected %s: %s", path, err)
                return {}
            except Exception as err:  # noqa: BLE001
                logger.warning("controller update failed, queued: %s", type(err).__name__)
                self._enqueue("POST", path, patch, f"controller:{interview_id}")
                return {}
        await self._send("POST", path, patch, key=f"controller:{interview_id}")
        return {}

    async def complete(self, interview_id: str, data: dict[str, Any] | None = None) -> None:
        await self._send(
            "POST",
            f"/api/v2/internal/interviews/{interview_id}/complete",
            {"data": data or {}},
            key=f"complete:{interview_id}",
        )

    # ------------------------------------------------------------------------------------- disk spool

    def _spool_remaining(self) -> None:
        if not self._queue:
            return
        by_interview: dict[str, list[dict[str, Any]]] = {}
        for method, path, body, key in self._queue:
            parts = path.split("/")
            interview_id = parts[5] if len(parts) > 5 else "unknown"
            by_interview.setdefault(interview_id, []).append(
                {"method": method, "path": path, "body": body, "key": key}
            )
        folder = spool_dir()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for interview_id, items in by_interview.items():
                with (folder / f"{interview_id}.jsonl").open("a", encoding="utf-8") as fh:
                    for item in items:
                        fh.write(json.dumps(item, ensure_ascii=False) + "\n")
            logger.error("backend unreachable; spooled %d writes to %s", len(self._queue), folder)
            self._queue.clear()
        except OSError:
            logger.exception("could not spool %d backend writes", len(self._queue))

    async def replay_spool(self) -> None:
        """Send writes spooled by earlier jobs. Each file is claimed by rename so two jobs never replay it twice."""
        folder = spool_dir()
        if not folder.is_dir():
            return
        now = time.time()
        # A claim left by a job that died mid-replay is taken over after a while.
        stale = [p for p in folder.glob("*.replay-*") if now - p.stat().st_mtime > _STALE_CLAIM_S]
        for path in sorted([*folder.glob("*.jsonl"), *stale]):
            claimed = path.with_name(f"{path.name.split('.')[0]}.replay-{os.getpid()}")
            try:
                path.rename(claimed)
            except OSError:
                continue
            try:
                lines = [json.loads(line) for line in claimed.read_text(encoding="utf-8").splitlines() if line.strip()]
            except (OSError, ValueError):
                logger.exception("unreadable spool file %s", claimed.name)
                continue
            for item in lines:
                self._enqueue(item["method"], item["path"], item["body"], item.get("key"))
            await self.flush(retries=1)
            stopped = bool(self._queue)
            self._spool_remaining()
            claimed.unlink(missing_ok=True)
            if stopped:
                return
            logger.info("replayed %d spooled writes for %s", len(lines), claimed.name.split(".")[0])

    async def aclose(self) -> None:
        await self.flush()
        self._spool_remaining()
        await self._client.aclose()
