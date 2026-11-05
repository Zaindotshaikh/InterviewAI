"""Accuracy check: labeled utterances against the full and lean analyst schemas.

Runs each row in tests/fixtures/analyst_eval.jsonl through ANALYST_SCHEMA=full and lean,
on gpt-4o-mini and gpt-4.1-mini. Prints per-field agreement with the labels and every
disagreement. Rows with needs_review are still scored; the flag is printed beside them.

Does not write API output back into the repo.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from interview.analysis import TurnAnalyzer, build_user_payload, heuristic_analysis  # noqa: E402
from interview.blueprint import Blueprint  # noqa: E402

MODELS = ("gpt-4o-mini", "gpt-4.1-mini")
SCHEMAS = ("full", "lean")
FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "analyst_eval.jsonl"
BLUEPRINT_PATH = Path(__file__).resolve().parents[2] / "server" / "v2" / "lib" / "blueprints" / "nursing.json"
FIELDS = ("intent", "slot_updates", "care_stance", "clinical_quality")


def _redact(text: str) -> str:
    for name in ("OPENAI_API_KEY", "ELEVENLABS_API_KEY", "ELEVEN_API_KEY"):
        secret = os.environ.get(name) or ""
        if secret and secret in text:
            text = text.replace(secret, "[redacted]")
    return text


def load_rows() -> list[dict]:
    rows = []
    for line in FIXTURE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _norm_value(field: str, value: object) -> str:
    text = " ".join(str(value or "").split())
    if field == "phone":
        return "".join(ch for ch in text if ch.isdigit())
    return text.casefold()


def _slots(updates: list[dict] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in updates or []:
        field = str(item.get("field") or "")
        if field:
            out[field] = _norm_value(field, item.get("value"))
    return out


def _payload(row: dict) -> str:
    return build_user_payload(
        stage=row["stage"],
        utterance=row["utterance"],
        last_agent_text=row["last_question"],
        recent_turns=[],
        fields_needed=list(row.get("fields") or []),
        care_focus=list(row.get("care_focus") or []),
        pending_confirmation=None,
        clinical_context=row.get("clinical_context"),
        known_facts={},
        known_claims=[],
        resume_summary="",
        language=row["language"],
    )


def _actual(analysis) -> dict[str, object]:
    care = None
    if analysis.care_updates:
        care = analysis.care_updates[0].stance
    quality = None
    if analysis.clinical is not None:
        quality = analysis.clinical.quality
    return {
        "intent": analysis.intent,
        "slot_updates": _slots(
            [{"field": u.field, "value": u.value} for u in analysis.slot_updates]
        ),
        "care_stance": care,
        "clinical_quality": quality,
        "source": analysis.source,
    }


def _expected(row: dict) -> dict[str, object]:
    quality = row.get("expected_clinical_quality")
    return {
        "intent": row["expected_intent"],
        "slot_updates": _slots(row.get("expected_slot_updates")),
        "care_stance": row.get("expected_care_stance"),
        "clinical_quality": quality,
    }


def _agree(field: str, expected: object, actual: object) -> bool:
    if field == "clinical_quality" and expected is None:
        return actual in (None, "", "none")
    if field == "care_stance":
        return (expected or None) == (actual or None)
    return expected == actual


async def _one(analyzer: TurnAnalyzer, row: dict) -> dict[str, object]:
    try:
        analysis = await analyzer.analyze(
            _payload(row),
            clinical=row["stage"] == "clinical",
            fallback=heuristic_analysis(row["utterance"]),
        )
    except Exception as err:  # noqa: BLE001
        return {"error": _redact(str(err))}
    got = _actual(analysis)
    if analysis.source == "heuristic":
        got["error"] = "heuristic"
    return got


async def main() -> None:
    from dotenv import load_dotenv

    agent_dir = Path(__file__).resolve().parents[1]
    load_dotenv(agent_dir / ".env", override=True)
    key = os.environ.get("OPENAI_API_KEY") or ""
    if not key:
        print("OPENAI_API_KEY is not set; accuracy check skipped")
        return

    # One request per row. A hedge would double the calls and blur agreement.
    os.environ["ANALYST_HEDGE_AFTER_SECS"] = "60"
    blueprint = Blueprint.from_api(json.loads(BLUEPRINT_PATH.read_text(encoding="utf-8")))
    rows = load_rows()
    print(f"rows={len(rows)} fixture={FIXTURE.name}")

    disagreements: list[str] = []
    for schema in SCHEMAS:
        os.environ["ANALYST_SCHEMA"] = schema
        for model in MODELS:
            analyzer = TurnAnalyzer(
                blueprint,
                api_key=key,
                model=model,
                clinical_model=model,
                timeout_s=25.0,
            )
            hits = {name: 0 for name in FIELDS}
            print(f"\nschema={schema} model={model}", flush=True)
            for row in rows:
                got = await _one(analyzer, row)
                expect = _expected(row)
                review = " needs_review" if row.get("needs_review") else ""
                if "intent" not in got:
                    for name in FIELDS:
                        disagreements.append(
                            f"{row['id']} schema={schema} model={model} {name} "
                            f"expected={expect[name]!r} got={got.get('error')}{review}"
                        )
                    continue
                for name in FIELDS:
                    if _agree(name, expect[name], got.get(name)):
                        hits[name] += 1
                    else:
                        disagreements.append(
                            f"{row['id']} schema={schema} model={model} {name} "
                            f"expected={expect[name]!r} got={got.get(name)!r}{review}"
                        )
            total = len(rows)
            for name in FIELDS:
                print(f"  {name} {hits[name]}/{total}")

    print("\ndisagreements")
    if not disagreements:
        print("  none")
    else:
        for line in disagreements:
            print(f"  {line}")


if __name__ == "__main__":
    asyncio.run(main())
