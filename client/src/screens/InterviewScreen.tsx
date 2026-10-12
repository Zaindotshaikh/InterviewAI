import { useEffect, useMemo, useState } from "react";
import { COMPANY_NAME } from "../config/brand";
import IntegrityWarningBanner from "../components/IntegrityWarningBanner";
import LiveCaptions from "../components/LiveCaptions";
import PresenceOrb, { type PresenceMode } from "../components/PresenceOrb";
import ThemeToggle from "../components/ThemeToggle";
import { useIntegrityMonitor } from "../hooks/useIntegrityMonitor";
import { useRealtimeSession } from "../hooks/useRealtimeSession";
import type { IntegrityEvent, IntegrityReport } from "../lib/integrity";
import type { InterviewSession } from "../types/session";

type Props = {
  session: InterviewSession;
  onEnded: (integrity: IntegrityReport) => void | Promise<void>;
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

export default function InterviewScreen({ session, onEnded }: Props) {
  const {
    connectionState,
    error,
    activeSpeaker,
    isThinking,
    captions,
    remoteStream,
    localStream,
    disconnect,
  } = useRealtimeSession({
    instructions: session.instructions,
    interviewId: session.id,
    candidateName: session.candidateName,
    interviewerName: session.interviewerName,
    demo: session.demo,
    transcriptionContext: {
      roleTitle: session.roleTitle,
    },
    resumeText: session.candidateContext?.resumeText ?? "",
    autoStart: true,
  });

  const integrityEnabled = connectionState === "live" || connectionState === "connecting";
  const { videoRef, available, status, liveWarnings, getEvents } = useIntegrityMonitor({
    enabled: integrityEnabled,
  });

  const [elapsedSec, setElapsedSec] = useState(0);
  const [ending, setEnding] = useState(false);

  useEffect(() => {
    if (connectionState !== "live") return;
    const id = window.setInterval(() => setElapsedSec((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [connectionState]);

  const presenceMode: PresenceMode = useMemo(() => {
    if (connectionState === "connecting" || connectionState === "reconnecting") {
      return "connecting";
    }
    if (connectionState === "idle" || connectionState === "error") return "idle";
    if (activeSpeaker === "assistant") return "speaking";
    if (isThinking) return "thinking";
    if (activeSpeaker === "user" || connectionState === "live") {
      return "listening";
    }
    return "idle";
  }, [connectionState, activeSpeaker, isThinking]);

  const live = connectionState === "live";
  const interviewer = session.interviewerName ?? "Interviewer";

  async function endInterview() {
    if (ending) return;
    setEnding(true);
    const events: IntegrityEvent[] = getEvents();
    const integrity: IntegrityReport = {
      available: available || status === "active",
      events,
    };
    disconnect();
    await onEnded(integrity);
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
              : connectionState === "connecting" || connectionState === "reconnecting"
                ? "Linking"
                : connectionState}
          </span>
          <span className="hidden tabular-nums text-sm tracking-wider text-[var(--color-fg)]/85 sm:inline">
            {formatTime(elapsedSec)}
          </span>
          <ThemeToggle className="border-[var(--color-accent)]/20 bg-black/40" />
        </div>
      </header>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col gap-3 p-3 sm:p-4 md:flex-row">
        <section className="relative flex min-h-0 min-w-0 flex-1 overflow-hidden rounded-2xl bg-black shadow-[0_0_80px_rgba(107,184,47,0.08)] ring-1 ring-[var(--color-accent)]/25">
          <div className="flex h-full w-full flex-col items-center justify-center gap-4 bg-black/50 px-4">
            <PresenceOrb
              mode={presenceMode}
              localStream={localStream}
              remoteStream={remoteStream}
            />
          </div>
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/35 via-transparent to-black/40" />
          <HudCorners />
          <div className="absolute inset-x-0 top-0 px-5 py-4">
            <p className="text-[10px] font-semibold tracking-[0.22em] text-[var(--color-accent)] uppercase">
              Interviewer
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
              captions={captions}
              variant="hud"
              interviewerName={session.interviewerName}
              resumeText={session.candidateContext?.resumeText}
            />
            <p className="mt-1.5 text-[9px] tracking-[0.16em] text-white/35 uppercase">
              On-device presence · encrypted channel
            </p>
          </div>
        </section>
      </div>

      {error && !error.trim().startsWith("{") && !error.includes("invalid_request") && (
        <p className="relative z-10 px-4 pb-1 text-center text-sm text-[var(--color-danger)]">
          {error}
        </p>
      )}

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
