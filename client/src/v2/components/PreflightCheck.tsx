import { useCallback, useState } from "react";

type Props = {
  onDone: (result: { noisy: boolean; rms: number }) => void;
};

/** 3s ambient measurement — warns but never blocks. */
export default function PreflightCheck({ onDone }: Props) {
  const [status, setStatus] = useState<"idle" | "measuring" | "done" | "error">("idle");
  const [noisy, setNoisy] = useState(false);
  const [rms, setRms] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    setStatus("measuring");
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: false,
          autoGainControl: true,
        },
        video: false,
      });
      const ctx = new AudioContext();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      const data = new Float32Array(analyser.fftSize);

      const samples: number[] = [];
      const start = performance.now();
      await new Promise<void>((resolve) => {
        const tick = () => {
          analyser.getFloatTimeDomainData(data);
          let sum = 0;
          for (let i = 0; i < data.length; i++) sum += data[i]! * data[i]!;
          samples.push(Math.sqrt(sum / data.length));
          if (performance.now() - start >= 3000) resolve();
          else requestAnimationFrame(tick);
        };
        tick();
      });

      stream.getTracks().forEach((t) => t.stop());
      await ctx.close();

      const avg = samples.reduce((a, b) => a + b, 0) / Math.max(samples.length, 1);
      const isNoisy = avg > 0.04;
      setRms(avg);
      setNoisy(isNoisy);
      setStatus("done");
      onDone({ noisy: isNoisy, rms: avg });
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Microphone permission denied");
      onDone({ noisy: false, rms: 0 });
    }
  }, [onDone]);

  return (
    <div className="rounded-xl border border-stone-200 bg-stone-50 p-4">
      <h3 className="text-sm font-semibold text-stone-800">Mic & noise check</h3>
      <p className="mt-1 text-xs text-stone-600">
        We measure ambient noise for 3 seconds. A noisy place is OK — we will warn you, not block you.
      </p>
      {status === "idle" && (
        <button
          type="button"
          onClick={() => void run()}
          className="mt-3 rounded-lg bg-stone-900 px-3 py-2 text-sm text-white"
        >
          Run check
        </button>
      )}
      {status === "measuring" && <p className="mt-3 text-sm text-stone-600">Listening… stay quiet for 3s</p>}
      {status === "done" && (
        <div className="mt-3 text-sm">
          <p>
            Ambient level: <span className="font-mono">{rms.toFixed(3)}</span>{" "}
            {noisy ? (
              <span className="text-amber-700">(noisy environment detected)</span>
            ) : (
              <span className="text-emerald-700">(looks OK)</span>
            )}
          </p>
          {noisy && (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
              <li>Prefer earphones with a mic</li>
              <li>Move away from ward chatter / TV if you can</li>
              <li>We still cancel background voices on the server</li>
            </ul>
          )}
        </div>
      )}
      {status === "error" && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  );
}
