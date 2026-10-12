"""STT bake-off harness (offline).

Usage:
  python -m eval.bakeoff --clips-dir ./eval/clips --out ./eval/results.json

Place WAV clips as: {lang}__{condition}__{id}.wav
  e.g. ta-IN__quiet__001.wav, hi-IN__ward__002.wav

Optional: mix ward noise at given SNR if --noise-file provided.
Requires SARVAM_API_KEY and/or OPENAI_API_KEY depending on --providers.
"""

from __future__ import annotations

import argparse
import json
import os
import wave
from pathlib import Path


def list_clips(clips_dir: Path) -> list[Path]:
    return sorted(clips_dir.glob("*.wav"))


def parse_name(path: Path) -> dict[str, str]:
    parts = path.stem.split("__")
    return {
        "lang": parts[0] if parts else "unknown",
        "condition": parts[1] if len(parts) > 1 else "unknown",
        "id": parts[2] if len(parts) > 2 else path.stem,
        "path": str(path),
    }


def wer(ref: str, hyp: str) -> float:
    """Simple word error rate."""
    r = ref.lower().split()
    h = hyp.lower().split()
    if not r:
        return 0.0 if not h else 1.0
    # Levenshtein
    dp = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        dp[i][0] = i
    for j in range(len(h) + 1):
        dp[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            dp[i][j] = min(dp[i - 1][j] + 1, dp[i][j - 1] + 1, dp[i - 1][j - 1] + cost)
    return dp[-1][-1] / len(r)


def stub_transcribe(path: Path, provider: str) -> str:
    """Placeholder: real calls should use Sarvam/OpenAI REST on the clip."""
    # Keep harness runnable without keys — returns empty to signal pending integration
    if provider == "sarvam" and not os.getenv("SARVAM_API_KEY"):
        return ""
    if provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        return ""
    # Without wiring full SDKs here, mark as not_run
    return ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips-dir", type=Path, default=Path("eval/clips"))
    parser.add_argument("--refs", type=Path, default=Path("eval/refs.json"))
    parser.add_argument("--out", type=Path, default=Path("eval/results.json"))
    parser.add_argument("--providers", default="sarvam,openai")
    args = parser.parse_args()

    refs = {}
    if args.refs.exists():
        refs = json.loads(args.refs.read_text(encoding="utf-8"))

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    clips = list_clips(args.clips_dir)
    results = []

    go_thresholds = {"p50_wer_max": 0.25, "meaning_survival_min": 0.8}

    for clip in clips:
        meta = parse_name(clip)
        ref = refs.get(clip.name) or refs.get(meta["id"]) or ""
        row = {**meta, "providers": {}}
        for provider in providers:
            hyp = stub_transcribe(clip, provider)
            row["providers"][provider] = {
                "hypothesis": hyp,
                "wer": wer(ref, hyp) if ref and hyp else None,
                "status": "ok" if hyp else "skipped_no_key_or_stub",
            }
        results.append(row)

    payload = {
        "clips": len(clips),
        "go_thresholds": go_thresholds,
        "latency_slos": {"e2e_p50_ms": 1400, "e2e_p95_ms": 2500},
        "results": results,
        "notes": (
            "Fill eval/refs.json with reference transcripts. "
            "Wire Sarvam REST / OpenAI transcription in stub_transcribe for live bake-off."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.out} ({len(clips)} clips)")


if __name__ == "__main__":
    main()
