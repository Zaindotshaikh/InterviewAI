"""Print p50/p95 latency from persisted turn.latency events.

Usage (from agent/):
  .\\.venv\\Scripts\\python.exe -m eval.latency_report --interview <uuid> --data ../server/data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python -m eval.latency_report` from agent/
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from interview.latency import summarize_turns  # noqa: E402


def _load_interview(data_dir: Path, interview_id: str) -> dict:
    path = data_dir / f"{interview_id}.v2.json"
    if not path.is_file():
        path = data_dir / f"{interview_id}.json"
    if not path.is_file():
        raise SystemExit(f"Interview file not found under {data_dir}: {interview_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Interview voice latency report (Phase 1)")
    parser.add_argument("--interview", required=True, help="Interview UUID")
    parser.add_argument(
        "--data",
        default=str(Path(__file__).resolve().parents[2] / "server" / "data"),
        help="Directory with *.v2.json interview files",
    )
    args = parser.parse_args()
    data = _load_interview(Path(args.data), args.interview)
    events = data.get("events") or []
    turns = [e.get("data") or {} for e in events if e.get("type") == "turn.latency"]
    session_cfg = next((e.get("data") for e in events if e.get("type") == "voice.session_config"), None)
    stored_summary = next((e.get("data") for e in events if e.get("type") == "turn.latency_summary"), None)

    print(f"interview={args.interview}")
    print(f"ttsProvider={data.get('ttsProvider')!r} language={data.get('language')!r}")
    if session_cfg:
        print(
            "session_config:",
            json.dumps(session_cfg, ensure_ascii=False),
        )
    print(f"turn.latency events: {len(turns)}")
    if not turns and stored_summary:
        print("No per-turn events; using stored turn.latency_summary:")
        print(json.dumps(stored_summary, indent=2, ensure_ascii=False))
        return
    if not turns:
        print("No turn.latency events. Ensure VOICE_LATENCY_LOG=true and restart the agent.")
        return

    summary = summarize_turns(turns)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()
    print("Headline: ttfa_vad_ms (VAD end of speech → first agent audio)")
    print("Also:    ttfa_confirm_ms (turn confirmed / hook start → first audio)")
    if summary.get("ttfa_vad_ms"):
        t = summary["ttfa_vad_ms"]
        print(f"  ttfa_vad_ms   p50={t.get('p50')}  p95={t.get('p95')}  max={t.get('max')}  n={t.get('n')}")
    if summary.get("ttfa_confirm_ms"):
        t = summary["ttfa_confirm_ms"]
        print(f"  ttfa_confirm  p50={t.get('p50')}  p95={t.get('p95')}  max={t.get('max')}  n={t.get('n')}")


if __name__ == "__main__":
    main()
