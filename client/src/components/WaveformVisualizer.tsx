import { useEffect, useRef, useState } from "react";
import { useTheme } from "../context/Theme";

type Props = {
  stream: MediaStream | null;
  active?: boolean;
  height?: number;
};

/**
 * Canvas frequency bars, sized in CSS pixels (fixes DPR overflow).
 */
export default function WaveformVisualizer({ stream, active = true, height = 64 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const { theme } = useTheme();

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let audioCtx: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    let analyser: AnalyserNode | null = null;
    let buffer: Uint8Array<ArrayBuffer> | null = null;
    let raf = 0;
    let cancelled = false;
    let cssW = wrap.clientWidth || 320;

    const resize = () => {
      cssW = wrap.clientWidth || 320;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.floor(cssW * dpr);
      canvas.height = Math.floor(height * dpr);
      canvas.style.width = `${cssW}px`;
      canvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const accent =
      getComputedStyle(document.documentElement).getPropertyValue("--color-accent").trim() ||
      "#6bb82f";

    const drawIdle = () => {
      ctx.clearRect(0, 0, cssW, height);
      const bars = 48;
      const gap = 2;
      const barWidth = (cssW - gap * (bars - 1)) / bars;
      for (let i = 0; i < bars; i++) {
        const barHeight = 3 + Math.sin(i * 0.35) * 2;
        const x = i * (barWidth + gap);
        const y = (height - barHeight) / 2;
        ctx.fillStyle = accent;
        ctx.globalAlpha = 0.22;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, barHeight, 1.5);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
    };

    const draw = () => {
      if (cancelled) return;
      ctx.clearRect(0, 0, cssW, height);

      if (!analyser || !buffer || !active) {
        drawIdle();
        raf = requestAnimationFrame(draw);
        return;
      }

      analyser.getByteFrequencyData(buffer);

      const bars = 48;
      const gap = 2;
      const barWidth = (cssW - gap * (bars - 1)) / bars;
      const step = Math.max(1, Math.floor(buffer.length / bars));

      for (let i = 0; i < bars; i++) {
        // Emphasize mid-band speech frequencies a bit
        const idx = Math.min(buffer.length - 1, Math.floor(i * step * 0.85) + 4);
        const raw = buffer[idx] / 255;
        const value = Math.pow(raw, 0.85);
        const barHeight = Math.max(3, value * (height - 8));
        const x = i * (barWidth + gap);
        const y = (height - barHeight) / 2;

        const grad = ctx.createLinearGradient(0, y, 0, y + barHeight);
        grad.addColorStop(0, accent);
        grad.addColorStop(1, accent);
        ctx.globalAlpha = 0.55 + value * 0.4;
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.roundRect(x, y, Math.max(1.5, barWidth), barHeight, 2);
        ctx.fill();
        ctx.globalAlpha = 1;
      }

      raf = requestAnimationFrame(draw);
    };

    resize();

    if (stream) {
      audioCtx = new AudioContext();
      source = audioCtx.createMediaStreamSource(stream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      analyser.smoothingTimeConstant = 0.72;
      source.connect(analyser);
      buffer = new Uint8Array(analyser.frequencyBinCount) as Uint8Array<ArrayBuffer>;
      void audioCtx.resume();
    }

    const ro = new ResizeObserver(() => resize());
    ro.observe(wrap);
    draw();

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      ro.disconnect();
      source?.disconnect();
      void audioCtx?.close();
    };
  }, [stream, active, height, theme]);

  return (
    <div ref={wrapRef} className="w-full max-w-full overflow-hidden">
      <canvas ref={canvasRef} className="block w-full max-w-full" style={{ height }} aria-hidden />
    </div>
  );
}

type MicTestProps = {
  stream: MediaStream | null;
  error?: string | null;
};

/** Polished mic-check card for setup / invite landing. */
export function MicTestCard({ stream, error }: MicTestProps) {
  const [level, setLevel] = useState(0);
  const ready = Boolean(stream);

  useEffect(() => {
    if (!stream) {
      setLevel(0);
      return;
    }
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaStreamSource(stream);
    const analyser = audioCtx.createAnalyser();
    analyser.fftSize = 256;
    source.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    let raf = 0;
    let cancelled = false;

    const tick = () => {
      if (cancelled) return;
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      setLevel(sum / data.length / 255);
      raf = requestAnimationFrame(tick);
    };
    void audioCtx.resume();
    tick();
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      source.disconnect();
      void audioCtx.close();
    };
  }, [stream]);

  const statusLabel = ready ? "Microphone ready" : error ? error : "Requesting access…";
  const statusTone = ready
    ? "text-[var(--color-accent)]"
    : error
      ? "text-[var(--color-danger)]"
      : "text-[var(--color-warn)]";

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--color-line)] bg-gradient-to-br from-[var(--color-panel)] to-[var(--color-panel-deep)]">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--color-line)]/70 px-4 py-3">
        <div className="flex items-center gap-2.5">
          <span
            className={`relative grid h-8 w-8 place-items-center rounded-full ${
              ready ? "bg-[var(--color-accent)]/15" : "bg-[var(--color-hover)]"
            }`}
          >
            <svg
              viewBox="0 0 24 24"
              className={`h-4 w-4 ${ready ? "text-[var(--color-accent)]" : "text-[var(--color-muted)]"}`}
              fill="currentColor"
              aria-hidden
            >
              <path d="M12 14a3 3 0 0 0 3-3V7a3 3 0 1 0-6 0v4a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z" />
            </svg>
            {ready && (
              <span
                className="absolute inset-0 rounded-full bg-[var(--color-accent)]/25"
                style={{ transform: `scale(${1 + level * 0.55})`, opacity: 0.35 + level * 0.4 }}
              />
            )}
          </span>
          <div>
            <p className="text-sm font-medium text-[var(--color-fg)]">Mic test</p>
            <p className={`text-xs ${statusTone}`}>{statusLabel}</p>
          </div>
        </div>
        {ready && (
          <span className="rounded-full bg-[var(--color-accent)]/12 px-2.5 py-1 text-[10px] font-semibold tracking-wide text-[var(--color-accent)] uppercase">
            Live
          </span>
        )}
      </div>

      <div className="px-4 py-4">
        <div className="rounded-xl bg-[var(--color-well)] px-3 py-3 ring-1 ring-[var(--color-line)]">
          <WaveformVisualizer stream={stream} active={ready} height={56} />
        </div>
        <p className="mt-3 text-xs leading-relaxed text-[var(--color-muted)]">
          {ready
            ? "Speak normally. Bars should move with your voice before you start."
            : "Allow microphone access so we can confirm audio before the interview."}
        </p>
      </div>
    </div>
  );
}
