import type { ConnectionState } from "../hooks/useRealtimeSession";

type Props = {
  connectionState: ConnectionState;
  elapsedSec: number;
  questionNumber: number;
  totalQuestions: number;
  candidateName: string;
  roleTitle: string;
};

function formatTime(sec: number) {
  const m = Math.floor(sec / 60)
    .toString()
    .padStart(2, "0");
  const s = (sec % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

const stateLabel: Record<ConnectionState, string> = {
  idle: "Idle",
  connecting: "Connecting",
  live: "Live",
  reconnecting: "Reconnecting",
  ended: "Ended",
  error: "Error",
};

export default function StatusBar({
  connectionState,
  elapsedSec,
  questionNumber,
  totalQuestions,
  candidateName,
  roleTitle,
}: Props) {
  const live = connectionState === "live";

  return (
    <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] pb-4">
      <div>
        <p className="text-sm font-medium text-[var(--color-fg)]">{candidateName}</p>
        <p className="text-xs text-[var(--color-muted)]">{roleTitle}</p>
      </div>
      <div className="flex items-center gap-4 text-xs text-[var(--color-muted)]">
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${
              live
                ? "bg-[var(--color-accent)]"
                : connectionState === "error"
                  ? "bg-[var(--color-danger)]"
                  : "bg-[var(--color-warn)] animate-pulse"
            }`}
          />
          {stateLabel[connectionState]}
        </span>
        <span className="tabular-nums">{formatTime(elapsedSec)}</span>
        <span>
          Question {questionNumber} of {totalQuestions}
        </span>
      </div>
    </header>
  );
}
