"""HMAC-authenticated client for Express /api/v2/internal endpoints."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Any

import httpx

from config import get_settings

logger = logging.getLogger("interview-v2.backend")


class BackendClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base = settings.backend_url.rstrip("/")
        self.secret = settings.v2_internal_secret
        self._queue: list[tuple[str, str, dict[str, Any]]] = []
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
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError("server error", request=resp.request, response=resp)
                resp.raise_for_status()
                if not resp.content:
                    return {}
                return resp.json()
            except Exception as err:  # noqa: BLE001
                last_err = err
                await asyncio.sleep(0.4 * (attempt + 1))
        assert last_err is not None
        raise last_err

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
    ) -> None:
        body: dict[str, Any] = {"role": role, "text": text}
        if turn_index is not None:
            body["turnIndex"] = turn_index
        if timestamp:
            body["timestamp"] = timestamp
        try:
            await self._request("POST", f"/api/v2/internal/interviews/{interview_id}/transcript", body)
        except Exception as err:  # noqa: BLE001
            logger.warning("transcript post failed, queued: %s", err)
            self._queue.append(("POST", f"/api/v2/internal/interviews/{interview_id}/transcript", body))

    async def post_event(self, interview_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
        body = {"type": event_type, "data": data or {}}
        try:
            await self._request("POST", f"/api/v2/internal/interviews/{interview_id}/event", body)
        except Exception as err:  # noqa: BLE001
            logger.warning("event post failed, queued: %s", err)
            self._queue.append(("POST", f"/api/v2/internal/interviews/{interview_id}/event", body))

    async def update_controller(self, interview_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", f"/api/v2/internal/interviews/{interview_id}/controller", patch)

    async def complete(self, interview_id: str, data: dict[str, Any] | None = None) -> None:
        await self._request(
            "POST",
            f"/api/v2/internal/interviews/{interview_id}/complete",
            {"data": data or {}},
        )

    async def flush(self) -> None:
        pending = list(self._queue)
        self._queue.clear()
        for method, path, body in pending:
            try:
                await self._request(method, path, body)
            except Exception as err:  # noqa: BLE001
                logger.error("flush failed for %s: %s", path, err)
                self._queue.append((method, path, body))

    async def aclose(self) -> None:
        await self.flush()
        await self._client.aclose()
