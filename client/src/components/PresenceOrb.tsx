import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

export type PresenceMode = "idle" | "connecting" | "listening" | "speaking" | "thinking";

type Props = {
  mode: PresenceMode;
  /** Local mic: drives listening amplitude */
  localStream: MediaStream | null;
  /** Remote AI audio: drives speaking amplitude */
  remoteStream: MediaStream | null;
  compact?: boolean;
};

function useAmplitude(stream: MediaStream | null, enabled: boolean) {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!stream || !enabled) {
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
      for (let i = 0; i < data.length; i++) sum += data[i]!;
      const avg = sum / data.length / 255;
      setLevel(avg);
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
  }, [stream, enabled]);

  return level;
}

const labels: Record<PresenceMode, string> = {
  idle: "Ready",
  connecting: "Connecting",
  listening: "Listening",
  speaking: "Speaking",
  thinking: "Thinking",
};

const accent: Record<PresenceMode, string> = {
  idle: "rgba(107, 184, 47, 0.35)",
  connecting: "rgba(148, 163, 184, 0.4)",
  listening: "rgba(107, 184, 47, 0.55)",
  speaking: "rgba(155, 227, 70, 0.65)",
  thinking: "rgba(251, 191, 36, 0.5)",
};

export default function PresenceOrb({ mode, localStream, remoteStream, compact }: Props) {
  const listenLevel = useAmplitude(localStream, mode === "listening");
  const speakLevel = useAmplitude(remoteStream, mode === "speaking");
  const level = mode === "listening" ? listenLevel : mode === "speaking" ? speakLevel : 0;
  const reactive = mode === "listening" || mode === "speaking";

  const scale = 1 + Math.min(level, 0.85) * 0.18;
  const glow = reactive ? 36 + level * 48 : mode === "thinking" ? 28 : mode === "connecting" ? 22 : 18;
  const ring = accent[mode];
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const size = compact ? "h-44 w-44" : "h-56 w-56";
  const core = compact ? "h-32 w-32" : "h-40 w-40";

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    if (!reactive) {
      // Soft idle baseline — a thin breathing line
      ctx.strokeStyle = "rgba(107, 184, 47, 0.25)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(w * 0.18, h / 2);
      ctx.lineTo(w * 0.82, h / 2);
      ctx.stroke();
      return;
    }

    const bars = 36;
    const mid = h / 2;
    const amp = Math.max(0.1, level);
    for (let i = 0; i < bars; i++) {
      const t = i / (bars - 1);
      const envelope = Math.sin(t * Math.PI);
      const jitter = 0.65 + 0.35 * Math.sin(i * 1.7 + amp * 12);
      const bh = Math.max(2, envelope * amp * jitter * h * 0.9);
      const bw = w / bars - 1.5;
      const x = i * (bw + 1.5);
      const grad = ctx.createLinearGradient(0, mid - bh / 2, 0, mid + bh / 2);
      if (mode === "speaking") {
        grad.addColorStop(0, "rgba(200, 245, 120, 0.15)");
        grad.addColorStop(0.5, "rgba(155, 227, 70, 0.95)");
        grad.addColorStop(1, "rgba(200, 245, 120, 0.15)");
      } else {
        grad.addColorStop(0, "rgba(107, 184, 47, 0.12)");
        grad.addColorStop(0.5, "rgba(107, 184, 47, 0.85)");
        grad.addColorStop(1, "rgba(107, 184, 47, 0.12)");
      }
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.roundRect(x, mid - bh / 2, bw, bh, 2);
      ctx.fill();
    }
  }, [level, mode, reactive]);

  return (
    <div className="flex flex-col items-center gap-5">
      <div className={`relative grid place-items-center ${size}`}>
        {/* Soft aura */}
        <motion.div
          className="absolute inset-[-8%] rounded-full"
          animate={{
            opacity: reactive ? 0.55 + level * 0.35 : mode === "thinking" ? [0.3, 0.5, 0.3] : [0.22, 0.34, 0.22],
            scale: reactive ? scale * 1.05 : mode === "thinking" ? [1, 1.06, 1] : [1, 1.04, 1],
          }}
          transition={
            reactive
              ? { type: "spring", stiffness: 140, damping: 18 }
              : { duration: mode === "thinking" ? 2 : 3.4, repeat: Infinity, ease: "easeInOut" }
          }
          style={{
            background: `radial-gradient(circle at 50% 45%, ${ring} 0%, transparent 68%)`,
            filter: `blur(${reactive ? 18 : 22}px)`,
          }}
        />

        {/* Expanding pulse rings when active */}
        {(reactive || mode === "connecting") &&
          [0, 1].map((i) => (
            <motion.div
              key={i}
              className="absolute rounded-full border"
              style={{
                inset: compact ? "10%" : "8%",
                borderColor: ring,
              }}
              initial={{ scale: 0.85, opacity: 0 }}
              animate={{ scale: [0.92, 1.28], opacity: [0.45, 0] }}
              transition={{
                duration: reactive ? 1.6 - Math.min(level, 0.5) * 0.4 : 2.4,
                repeat: Infinity,
                delay: i * 0.7,
                ease: "easeOut",
              }}
            />
          ))}

        {/* Core — fully filled sphere, no crescent */}
        <motion.div
          className={`relative ${core} overflow-hidden rounded-full`}
          animate={{ scale }}
          transition={{ type: "spring", stiffness: 160, damping: 16 }}
          style={{
            background:
              mode === "thinking"
                ? "radial-gradient(circle at 38% 32%, #f5e08a 0%, #d4a017 38%, #8a6a12 100%)"
                : mode === "speaking"
                  ? "radial-gradient(circle at 38% 32%, #c8f06a 0%, #7ec32e 38%, #3d7a14 100%)"
                  : "radial-gradient(circle at 38% 32%, #b4e05a 0%, #6bb82f 40%, #2f6410 100%)",
            boxShadow: `0 0 ${glow}px ${ring}`,
          }}
        >
          {/* Soft top-left sheen — stays inside the green fill */}
          <div
            className="pointer-events-none absolute inset-0 rounded-full"
            style={{
              background:
                "radial-gradient(circle at 34% 30%, rgba(255,255,255,0.38) 0%, rgba(255,255,255,0.08) 28%, transparent 52%)",
            }}
          />

          {mode === "thinking" && (
            <div className="absolute inset-0 flex items-center justify-center gap-1.5">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="h-1.5 w-1.5 rounded-full bg-amber-100/90"
                  animate={{ opacity: [0.25, 1, 0.25], y: [0, -5, 0] }}
                  transition={{ duration: 1.05, repeat: Infinity, delay: i * 0.16 }}
                />
              ))}
            </div>
          )}
        </motion.div>
      </div>

      <canvas
        ref={canvasRef}
        width={280}
        height={36}
        className={`opacity-95 ${compact ? "h-7 w-48" : "h-8 w-64"}`}
        aria-hidden
      />

      <p
        className={`text-[11px] font-medium tracking-[0.22em] uppercase ${
          reactive ? "text-[var(--color-accent)]" : "text-[var(--color-muted)]"
        }`}
      >
        {labels[mode]}
      </p>
    </div>
  );
}
