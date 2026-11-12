import asyncio

import httpx

from providers import health
from providers.health import blocking_problems, check_keys


def _transport(responses: dict[str, tuple[int, str]], seen: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request.url.host)
        code, body = responses[request.url.host]
        if code == 0:
            raise httpx.ConnectError("down", request=request)
        return httpx.Response(code, text=body)

    return httpx.MockTransport(handler)


def _run(keys, responses, seen=None):
    health._cache.clear()
    return asyncio.run(check_keys(keys, use_cache=False, transport=_transport(responses, seen)))


def test_rejected_key_blocks_the_call():
    out = _run(
        {"openai": "a", "elevenlabs": "b"},
        {"api.openai.com": (200, "{}"), "api.elevenlabs.io": (401, '{"detail":{"status":"invalid_api_key"}}')},
    )
    assert out == {"openai": "ok", "elevenlabs": "invalid"}
    assert blocking_problems(out) == ["elevenlabs"]


def test_scoped_elevenlabs_key_is_not_rejected():
    out = _run({"elevenlabs": "b"}, {"api.elevenlabs.io": (401, '{"detail":{"status":"missing_permissions"}}')})
    assert out == {"elevenlabs": "ok"}


def test_outage_or_rate_limit_does_not_refuse():
    out = _run(
        {"openai": "a", "elevenlabs": "b"},
        {"api.openai.com": (429, ""), "api.elevenlabs.io": (0, "")},
    )
    assert out == {"openai": "ok", "elevenlabs": "unknown"}
    assert blocking_problems(out) == []


def test_missing_key_blocks_without_a_request():
    seen: list[str] = []
    out = _run({"openai": None}, {}, seen)
    assert out == {"openai": "missing"}
    assert seen == []
    assert blocking_problems(out) == ["openai"]


def test_result_is_cached_but_unknown_is_retried():
    health._cache.clear()
    seen: list[str] = []
    responses = {"api.openai.com": (200, ""), "api.elevenlabs.io": (500, "")}
    keys = {"openai": "a", "elevenlabs": "b"}
    asyncio.run(check_keys(keys, transport=_transport(responses, seen)))
    asyncio.run(check_keys(keys, transport=_transport(responses, seen)))
    assert seen.count("api.openai.com") == 1
    assert seen.count("api.elevenlabs.io") == 2
