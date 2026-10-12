import { useEffect, useMemo, useRef, useState } from "react";
import { COMPANY_NAME } from "../../config/brand";
import IntegrityWarningBanner from "../../components/IntegrityWarningBanner";
import LiveCaptions from "../../components/LiveCaptions";
import PresenceOrb, { type PresenceMode } from "../../components/PresenceOrb";
import ThemeToggle from "../../components/ThemeToggle";
import { useIntegrityMonitor } from "../../hooks/useIntegrityMonitor";
import type { IntegrityEvent, IntegrityReport } from "../../lib/integrity";
import type { useLiveKitInterview } from "../hooks/useLiveKitInterview";

type Hook = ReturnType<typeof useLiveKitInterview>;

type Props = {
  session: {
    id: string;
    candidateName: string;
    roleTitle: string;
    interviewerName: string;
    interviewerTitle?: string;
    language: string;
    livekit: { url: string; token: string } | null;
  };
  lk: Hook;
  onEnded: (integrity: IntegrityReport) => void;
  showAvatar?: boolean;
};

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
    .toString()
    .padStart(2, "0");
  const s = (sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function HudCorners() {
  const arm = "h-5 w-5 border-[var(--color-accent)]";
  return (
    <>
      <span className={`pointer-events-none absolute top-3 left-3 border-t-2 border-l-2 ${arm}`} />
      <span className={`pointer-events-none absolute top-3 right-3 border-t-2 border-r-2 ${arm}`} />
      <span className={`pointer-events-none absolute bottom-3 left-3 border-b-2 border-l-2 ${arm}`} />
      <span className={`pointer-events-none absolute right-3 bottom-3 border-r-2 border-b-2 ${arm}`} />
    </>
  );
}

export default function LiveInterview({ session, lk, onEnded, showAvatar = false }: Props) {
  const started = useRef(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const avatarVideoRef = useRef<HTMLVideoElement | null>(null);
  const [ending, setEnding] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [agentSpeaking, setAgentSpeaking] = useState(false);

  const integrityEnabled = lk.phase === "live" || lk.phase === "connecting" || lk.phase === "reconnecting";
  const { videoRef, available, status, liveWarnings, getEvents } = useIntegrityMonitor({
    enabled: integrityEnabled,
  });

  useEffect(() => {
    if (started.current) return;
    if (!session.livekit) return;
    started.current = true;
    void lk.connect({
      url: session.livekit.url,
      token: session.livekit.token,
      unlockAudio: true,
    });
  }, [session.livekit, lk]);

  useEffect(() => {
    if (lk.remoteStream && audioRef.current) {
      audioRef.current.srcObject = lk.remoteStream;
      void audioRef.current.play().catch(() => undefined);
    }
  }, [lk.remoteStream]);

  useEffect(() => {
    const el = avatarVideoRef.current;
    if (!el) return;
    el.srcObject = lk.remoteVideoStream;
    if (lk.remoteVideoStream) {
      void el.play().catch(() => undefined);
    }
  }, [lk.remoteVideoStream]);

  // Drive the presence orb from remote audio level when the agent is talking.
  useEffect(() => {
    const stream = lk.remoteStream;
    if (!stream || lk.phase !== "live") {
      setAgentSpeaking(false);
      return;
    }
    const ctx = new AudioContext();
    const source = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
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
      setAgentSpeaking(sum / data.length / 255 > 0.04);
      raf = requestAnimationFrame(tick);
    };
    void ctx.resume();
    tick();
    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      source.disconnect();
      void ctx.close();
    };
  }, [lk.remoteStream, lk.phase]);

  useEffect(() => {
    if (lk.phase !== "live") return;
    const id = window.setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [lk.phase]);

  const presenceMode: PresenceMode = useMemo(() => {
    if (lk.phase === "connecting" || lk.phase === "reconnecting") return "connecting";
    if (lk.phase === "idle" || lk.phase === "error" || lk.phase === "ended") return "idle";
    if (agentSpeaking) return "speaking";
    if (lk.phase === "live") return "listening";
    return "idle";
  }, [lk.phase, agentSpeaking]);

  const live = lk.phase === "live";
  const interviewer = session.interviewerName ?? "Interviewer";

  async function endInterview() {
    if (ending) return;
    setEnding(true);
    const events: IntegrityEvent[] = getEvents();
    const integrity: IntegrityReport = {
      available: available || status === "active",
      events,
    };
    await lk.disconnect();
    onEnded(integrity);
  }

  return (
    <div className="relative flex h-dvh max-h-dvh flex-col overflow-hidden bg-[#070908]">
      <IntegrityWarningBanner warnings={liveWarnings} />

      <div className="hud-grid pointer-events-none absolute inset-0 opacity-70" />
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            presenceMode === "speaking"
              ? "radial-gradient(ellipse 55% 45% at 18% 42%, rgba(155,227,70,0.18), transparent 62%)"
              : presenceMode === "listening"
                ? "radial-gradient(ellipse 70% 55% at 72% 45%, rgba(107,184,47,0.14), transparent 60%)"
                : "radial-gradient(ellipse 50% 40% at 50% 0%, rgba(107,184,47,0.1), transparent 55%)",
        }}
      />

      <header className="relative z-10 flex shrink-0 items-center justify-between gap-3 border-b border-[var(--color-accent)]/15 bg-black/35 px-4 py-2.5 backdrop-blur-md sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-8 w-8 place-items-center rounded-md border border-[var(--color-accent)]/40 bg-[var(--color-accent)]/15 text-[11px] font-bold tracking-wider text-[var(--color-accent)]">
            K
          </div>
          <div className="min-w-0">
            <p className="truncate text-[10px] font-semibold tracking-[0.22em] text-[var(--color-accent)] uppercase">
              {COMPANY_NAME} · live link
            </p>
            <p className="truncate text-sm text-[var(--color-fg)]">{session.roleTitle}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-accent)]/30 bg-black/40 px-2.5 py-1 text-[10px] font-semibold tracking-[0.18em] text-[var(--color-accent)] uppercase">
            <span
              className={`h-1.5 w-1.5 rounded-full bg-[var(--color-accent)] ${live ? "hud-rec" : ""}`}
            />
            {live
              ? "Live"
              : lk.phase === "connecting" || lk.phase === "reconnecting"
                ? "Linking"
                : lk.phase}
          </span>
          <span className="hidden tabular-nums text-sm tracking-wider text-[var(--color-fg)]/85 sm:inline">
            {formatTime(elapsedSec)}
          </span>
          <ThemeToggle className="border-[var(--color-accent)]/20 bg-black/40" />
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-4 md:flex-row">
        <section className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-2xl bg-black shadow-[0_0_80px_rgba(107,184,47,0.08)] ring-1 ring-[var(--color-accent)]/25">
          {showAvatar ? (
            <video
              ref={avatarVideoRef}
              className="h-full w-full bg-black object-cover"
              playsInline
              muted
              autoPlay
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-black/50 px-4">
              <PresenceOrb
                mode={presenceMode}
                localStream={lk.localStream}
                remoteStream={lk.remoteStream}
              />
              {lk.connectionQuality !== "unknown" && (
                <p className="text-[10px] tracking-[0.16em] text-[var(--color-muted)] uppercase">
                  Network {lk.connectionQuality}
                </p>
              )}
            </div>
          )}

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-black/40" />
          <HudCorners />

          {showAvatar && !lk.remoteVideoStream && (
            <div className="absolute inset-0 z-10 grid place-items-center bg-black/55 px-6 text-center text-sm text-white/80">
              {elapsedSec > 20
                ? "Tavus video did not join this room. End and retry after the agent reloads — check the agent terminal for a Tavus error."
                : "Connecting Tavus avatar…"}
            </div>
          )}

          <div className="absolute inset-x-0 top-0 px-5 py-4">
            <p className="text-[10px] font-semibold tracking-[0.22em] text-[var(--color-accent)] uppercase">
              {showAvatar ? "Interviewer avatar" : "Interviewer"}
            </p>
            <p className="mt-0.5 text-base font-medium text-white">{interviewer}</p>
            {session.interviewerTitle ? (
              <p className="text-[11px] text-white/55">{session.interviewerTitle}</p>
            ) : null}
          </div>
        </section>

        <section
          className={`relative flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-2xl bg-black shadow-[0_0_80px_rgba(107,184,47,0.08)] ${
            liveWarnings.length
              ? "ring-2 ring-[var(--color-danger)]"
              : "ring-1 ring-[var(--color-accent)]/25"
          }`}
        >
          <video
            ref={videoRef}
            className="h-full w-full object-cover scale-x-[-1]"
            playsInline
            muted
            autoPlay
          />

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-black/55" />
          <div className="pointer-events-none absolute inset-0 overflow-hidden opacity-20">
            <div className="hud-scan h-1/3 w-full bg-gradient-to-b from-transparent via-[var(--color-accent)]/40 to-transparent" />
          </div>
          <HudCorners />

          {liveWarnings.length > 0 && (
            <div className="pointer-events-none absolute inset-0 bg-[var(--color-danger)]/20" />
          )}

          <div className="absolute inset-x-0 top-0 flex items-start justify-between px-5 py-4">
            <div>
              <p className="text-[10px] font-semibold tracking-[0.22em] text-[var(--color-accent)] uppercase">
                Candidate feed
              </p>
              <p className="mt-0.5 text-base font-medium text-white">{session.candidateName}</p>
            </div>
            <span
              className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] uppercase ${
                liveWarnings.length
                  ? "border-[var(--color-danger)] bg-[var(--color-danger)] text-[var(--color-on-danger)]"
                  : status === "active"
                    ? "border-[var(--color-accent)]/50 bg-black/50 text-[var(--color-accent)]"
                    : "border-white/20 bg-black/40 text-white/70"
              }`}
            >
              {liveWarnings.length
                ? "Alert"
                : status === "active"
                  ? "Cam lock"
                  : status === "loading"
                    ? "Acquiring…"
                    : status === "unavailable"
                      ? "No cam"
                      : "Idle"}
            </span>
          </div>

          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/45 to-transparent px-4 pt-8 pb-3 sm:px-5">
            <LiveCaptions
              captions={lk.captions.map((c) => ({
                id: c.id,
                role: c.role,
                text: c.text,
                partial: !c.final,
              }))}
              variant="hud"
              interviewerName={session.interviewerName}
            />
            <p className="mt-1.5 text-[9px] tracking-[0.16em] text-white/35 uppercase">
              On-device presence · encrypted channel
            </p>
          </div>
        </section>
      </div>

      {!lk.canPlayAudio && (
        <div className="relative z-10 flex justify-center px-4 pb-1">
          <button
            type="button"
            className="rounded-full border border-amber-400/50 bg-amber-500/20 px-4 py-2 text-[10px] font-semibold tracking-[0.18em] text-amber-200 uppercase"
            onClick={() => void lk.unlockAudio()}
          >
            Tap to enable interviewer audio
          </button>
        </div>
      )}

      {lk.error && !lk.error.trim().startsWith("{") && !lk.error.includes("invalid_request") && (
        <p className="relative z-10 px-4 pb-1 text-center text-sm text-[var(--color-danger)]">
          {lk.error}
        </p>
      )}

      {!session.livekit && (
        <p className="relative z-10 px-4 pb-1 text-center text-sm text-amber-300">
          LiveKit is not configured — session {session.id} was created, but voice cannot connect yet.
        </p>
      )}

      <audio ref={audioRef} autoPlay playsInline className="hidden" />

      <div className="relative z-10 flex shrink-0 justify-center border-t border-[var(--color-accent)]/10 bg-black/40 py-3">
        <button
          type="button"
          disabled={ending}
          onClick={() => void endInterview()}
          className="rounded-full border border-white/15 px-5 py-2 text-[10px] font-semibold tracking-[0.2em] text-white/55 uppercase transition hover:border-[var(--color-danger)]/60 hover:text-white disabled:opacity-50"
        >
          {ending ? "Closing…" : "End session"}
        </button>
      </div>
    </div>
  );
}
