"""Provider key check before a call starts.

A revoked or wrong key otherwise shows up mid-interview as dead air (TTS 1008 invalid_api_key loops).
Only a definite rejection refuses the call; a network error or provider outage does not.
Results are cached per worker process so later jobs do not pay the round-trip.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import httpx

logger = logging.getLogger("interview-v2.health")

KeyStatus = Literal["ok", "invalid", "missing", "unknown"]

_TTL_S = 600.0
_TIMEOUT = httpx.Timeout(4.0, connect=3.0)
_cache: dict[str, tuple[float, KeyStatus]] = {}

_PROBES: dict[str, tuple[str, str]] = {
    # provider: (url, header name)
    "openai": ("https://api.openai.com/v1/models", "authorization"),
    "elevenlabs": ("https://api.elevenlabs.io/v1/models", "xi-api-key"),
}


def _status_from_response(provider: str, code: int, body: str) -> KeyStatus:
    if code < 300 or code == 429:
        return "ok"
    if code in (401, 403):
        # A scoped ElevenLabs key may lack read access to this endpoint; the key itself is valid.
        if provider == "elevenlabs" and "missing_permissions" in body:
            return "ok"
        return "invalid"
    return "unknown"


async def _probe(client: httpx.AsyncClient, provider: str, key: str | None) -> KeyStatus:
    if not key:
        return "missing"
    url, header = _PROBES[provider]
    value = f"Bearer {key}" if header == "authorization" else key
    try:
        resp = await client.get(url, headers={header: value})
    except httpx.HTTPError as err:
        logger.warning("key check %s unreachable: %s", provider, type(err).__name__)
        return "unknown"
    return _status_from_response(provider, resp.status_code, resp.text[:400])


async def check_keys(
    keys: dict[str, str | None],
    *,
    use_cache: bool = True,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, KeyStatus]:
    """Status per provider. `keys` maps a provider in _PROBES to its key (values are never logged)."""
    now = time.monotonic()
    out: dict[str, KeyStatus] = {}
    todo: list[str] = []
    for provider in keys:
        cached = _cache.get(provider)
        if use_cache and cached and now - cached[0] < _TTL_S:
            out[provider] = cached[1]
        else:
            todo.append(provider)
    if todo:
        async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
            results = await asyncio.gather(*(_probe(client, p, keys[p]) for p in todo))
        for provider, status in zip(todo, results):
            out[provider] = status
            # Do not cache "unknown": the next job should try again.
            if status != "unknown":
                _cache[provider] = (now, status)
    return out


def blocking_problems(statuses: dict[str, KeyStatus]) -> list[str]:
    """Providers whose key is definitely unusable: a call must not start on them."""
    return sorted(p for p, s in statuses.items() if s in ("invalid", "missing"))
