"""Report internal silent gaps (> 120 ms) in rendered WAVs: python -m eval.gap_stats eval/samples/pause_*.wav"""

import sys
import wave

import numpy as np

FRAME_MS = 10
GAP_MIN_MS = 120


def gaps(path: str) -> tuple[float, list[int]]:
    with wave.open(path, "rb") as w:
        rate, data = w.getframerate(), np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    step = rate * FRAME_MS // 1000
    n = len(data) // step
    rms = np.sqrt((data[: n * step].astype(np.float32).reshape(n, step) ** 2).mean(axis=1))
    voiced = rms > max(150.0, rms.max() * 0.02)
    idx = np.flatnonzero(voiced)
    if idx.size == 0:
        return len(data) / rate, []
    body = voiced[idx[0] : idx[-1] + 1]
    out, run = [], 0
    for v in body:
        if v:
            if run * FRAME_MS >= GAP_MIN_MS:
                out.append(run * FRAME_MS)
            run = 0
        else:
            run += 1
    return len(data) / rate, out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        total, g = gaps(p)
        print(f"{p.split(chr(92))[-1]}: {total:.1f}s, {len(g)} gaps, total gap {sum(g)/1000:.1f}s, gaps(ms)={g}")
