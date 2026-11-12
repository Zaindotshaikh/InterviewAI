"""Print the per-turn latency table for one interview.

Usage (from the repo root):
    python agent/scripts/latency_report.py <interview-id> [path-to-server-data-dir]

Reads `server/data/<id>.v2.json` and the `turn.latency` events the agent posted.
Headline number: reply_from_vad_ms (candidate stops -> first audio of the real reply, fillers excluded).
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

COLUMNS = (
    ("turn_index", "turn"),
    ("reply_from_vad_ms", "reply_vad"),
    ("reply_from_confirm_ms", "reply_conf"),
    ("stt_final_from_vad_ms", "stt_final"),
    ("director_ms", "director"),
    ("early_analysis", "early"),
    ("analyst_tokens", "tokens"),
    ("tts_text_after_director_ms", "text_after_dir"),
    ("llm_ttft_ms", "llm_ttft"),
    ("tts_ttfb_ms", "tts_ttfb"),
    ("filler_from_vad_ms", "filler_vad"),
)
SUMMARY_KEYS = (
    "reply_from_vad_ms",
    "reply_from_confirm_ms",
    "stt_final_from_vad_ms",
    "director_ms",
    "analyst_tokens",
    "tts_text_after_director_ms",
    "llm_ttft_ms",
    "tts_ttfb_ms",
)


def load_turns(record: dict[str, Any]) -> list[dict[str, Any]]:
    turns = [e.get("data") or {} for e in record.get("events", []) if e.get("type") == "turn.latency"]
    return [t for t in turns if isinstance(t, dict)]


def _percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = max(0, min(len(ordered) - 1, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[k]


def summarize(turns: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for key in SUMMARY_KEYS:
        vals = [float(t[key]) for t in turns if isinstance(t.get(key), (int, float))]
        if vals:
            out[key] = {
                "n": float(len(vals)),
                "p50": round(_percentile(vals, 50), 1),
                "p95": round(_percentile(vals, 95), 1),
                "max": round(max(vals), 1),
                "mean": round(statistics.fmean(vals), 1),
            }
    hits = [t.get("early_analysis") for t in turns if t.get("early_analysis")]
    if hits:
        out["early_hit_rate"] = {"n": float(len(hits)), "p50": round(hits.count("hit") / len(hits), 2)}
    return out


def render(turns: list[dict[str, Any]]) -> str:
    lines = ["  ".join(f"{label:>14}" for _, label in COLUMNS)]
    for t in turns:
        lines.append("  ".join(f"{'-' if t.get(key) is None else t.get(key)!s:>14}" for key, _ in COLUMNS))
    lines.append("")
    for key, stats in summarize(turns).items():
        lines.append(f"{key:>28}: " + "  ".join(f"{k}={v}" for k, v in stats.items()))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    interview_id = argv[1]
    data_dir = Path(argv[2]) if len(argv) > 2 else Path(__file__).resolve().parents[2] / "server" / "data"
    path = data_dir / f"{interview_id}.v2.json"
    if not path.exists():
        print(f"not found: {path}")
        return 1
    turns = load_turns(json.loads(path.read_text(encoding="utf-8")))
    if not turns:
        print("no turn.latency events in this record")
        return 1
    print(render(turns))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
