"""Latency bench for the screening analyst. Does not change interview behaviour.

Compares the current screening JSON schema with the lean schema (intelligibility, intent,
nervous, slot_updates, confirmation, care_updates, experience_level, answer_depth).
Five calls per model, schema, and sample utterance. Prints p50/p95 latency and output tokens.

The demo worker is deployed in ap-south (Mumbai). This script runs wherever it is launched
and prints that place so the numbers can be read against the worker region.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

# Allow `python scripts/bench_analyst.py` from agent/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interview.analysis import SYSTEM_PROMPT, build_schema, build_user_payload  # noqa: E402
from interview.blueprint import Blueprint  # noqa: E402
from interview.latency import percentile  # noqa: E402

LEAN_FIELDS = (
    "intelligibility",
    "intent",
    "nervous",
    "slot_updates",
    "confirmation",
    "care_updates",
    "experience_level",
    "answer_depth",
)

UTTERANCES = (
    ("city_hinglish", "main Pune se hoon, wahi city ke liye apply kar rahi hoon"),
    ("phone", "nine eight seven six five four three two one zero"),
    ("clinical_short", "BP check karungi aur doctor ko bula lungi"),
)

MODELS = ("gpt-4o-mini", "gpt-4.1-mini")
REPEATS = 5
BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"


def _redact(text: str) -> str:
    for name in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
        secret = os.environ.get(name) or ""
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def _lean_schema(full: dict) -> dict:
    props = {key: full["properties"][key] for key in LEAN_FIELDS}
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


def _lean_prompt(full: str) -> str:
    head = full.split("\n## Clinical grading", 1)[0].rstrip()
    return (
        head
        + "\n\n## answer_depth\n"
        + "When the interviewer asked an experience or nursing-practice probe (not a one-word screening "
        + "slot), set sufficient if they gave concrete steps, checks, or duties; thin if only a vague yes / "
        + "one short phrase with no detail; none when the question was not that kind of probe.\n\n"
        + 'If a section does not apply, return empty arrays, "none" or false for it.'
    )


def _where() -> str:
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        city = data.get("city") or "?"
        region = data.get("region") or "?"
        country = data.get("country") or "?"
        return f"{city}, {region}, {country}"
    except Exception as err:  # noqa: BLE001
        return f"unknown ({type(err).__name__})"


def _payload(kind: str, text: str) -> str:
    clinical = None
    if kind == "clinical_short":
        clinical = {
            "area_id": "vitals",
            "title": "Vital signs",
            "level": 1,
            "question_seed": "What would you do if blood pressure drops?",
            "key_points": [{"id": "recheck", "text": "recheck the reading"}, {"id": "doctor", "text": "inform the doctor"}],
            "red_flags": ["ignore a low reading"],
        }
    return build_user_payload(
        stage="clinical" if clinical else "screening",
        utterance=text,
        last_agent_text="Which city are you applying from?" if not clinical else "What would you do if BP drops?",
        recent_turns=[],
        fields_needed=[{"id": "city", "label": "City", "kind": "text"}],
        care_focus=[],
        pending_confirmation=None,
        clinical_context=clinical,
        known_facts={},
        known_claims=[],
        resume_summary="",
        language="hi-IN",
    )


async def _once(client, *, model: str, system: str, schema: dict, max_tokens: int, payload: str) -> tuple[float, int]:
    started = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": payload},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "turn_analysis", "strict": True, "schema": schema},
        },
        temperature=0,
        max_tokens=max_tokens,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    usage = getattr(resp, "usage", None)
    tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    return elapsed_ms, tokens


async def main() -> None:
    from dotenv import load_dotenv
    from openai import AsyncOpenAI

    agent_dir = Path(__file__).resolve().parents[1]
    load_dotenv(agent_dir / ".env", override=True)
    load_dotenv(agent_dir.parent / ".env", override=False)
    key = os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        print("OPENAI_API_KEY is not set; benchmark skipped")
        return

    blueprint = Blueprint.from_api(json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")))
    current = build_schema(blueprint)
    lean = _lean_schema(current)
    prompts = {"current": SYSTEM_PROMPT, "lean": _lean_prompt(SYSTEM_PROMPT)}
    schemas = {"current": current, "lean": lean}
    limits = {"current": 900, "lean": 300}
    place = _where()
    print(f"ran_from={place}")
    print("worker_region=ap-south (Mumbai), from agent/DEPLOY.md")
    print(f"repeats={REPEATS}")

    client = AsyncOpenAI(api_key=key, timeout=30.0, max_retries=0)
    try:
        for model in MODELS:
            try:
                await client.models.retrieve(model)
            except Exception as err:  # noqa: BLE001
                print(f"prewarm {model} failed: {_redact(str(err))}")

        rows: list[tuple[str, str, str, float, float, float, float]] = []
        for schema_name in ("current", "lean"):
            for model in MODELS:
                for kind, text in UTTERANCES:
                    latencies: list[float] = []
                    tokens: list[int] = []
                    payload = _payload(kind, text)
                    for _ in range(REPEATS):
                        try:
                            ms, out_tokens = await _once(
                                client,
                                model=model,
                                system=prompts[schema_name],
                                schema=schemas[schema_name],
                                max_tokens=limits[schema_name],
                                payload=payload,
                            )
                        except Exception as err:  # noqa: BLE001
                            print(f"FAIL schema={schema_name} model={model} utterance={kind}: {_redact(str(err))}")
                            break
                        latencies.append(ms)
                        tokens.append(out_tokens)
                    if len(latencies) != REPEATS:
                        continue
                    rows.append(
                        (
                            schema_name,
                            model,
                            kind,
                            percentile(latencies, 50) or 0.0,
                            percentile(latencies, 95) or 0.0,
                            percentile([float(t) for t in tokens], 50) or 0.0,
                            percentile([float(t) for t in tokens], 95) or 0.0,
                        )
                    )
                    print(
                        f"{schema_name:8} {model:14} {kind:16} "
                        f"p50_ms={rows[-1][3]:7.1f} p95_ms={rows[-1][4]:7.1f} "
                        f"out_p50={rows[-1][5]:.0f} out_p95={rows[-1][6]:.0f}"
                    )
        if rows:
            by_model: dict[tuple[str, str], list[float]] = {}
            by_tokens: dict[tuple[str, str], list[float]] = {}
            for schema_name, model, _kind, p50, _p95, tok50, _tok95 in rows:
                by_model.setdefault((schema_name, model), []).append(p50)
                by_tokens.setdefault((schema_name, model), []).append(tok50)
            print("--- rollup mean of per-utterance p50 ---")
            for key, vals in by_model.items():
                print(
                    f"{key[0]:8} {key[1]:14} mean_p50_ms={statistics.fmean(vals):7.1f} "
                    f"mean_out_p50={statistics.fmean(by_tokens[key]):.1f}"
                )
    finally:
        await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:  # noqa: BLE001
        print(_redact(f"benchmark failed: {type(err).__name__}: {err}"))
        sys.exit(1)
