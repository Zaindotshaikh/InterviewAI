import { useEffect, useRef, useState } from "react";

const STAGES = [
  "Saving the interview conversation.",
  "Reviewing the screening details.",
  "Scoring the clinical discussion.",
  "Writing the hiring summary.",
];

type Props = {
  ready: boolean;
  onDone: () => void;
};

export default function ScorecardProgress({ ready, onDone }: Props) {
  const [step, setStep] = useState(0);
  const finished = useRef(false);

  useEffect(() => {
    if (step >= STAGES.length - 1) return;
    const timer = window.setTimeout(() => setStep((current) => current + 1), 1100);
    return () => window.clearTimeout(timer);
  }, [step]);

  useEffect(() => {
    if (!ready || step < STAGES.length - 1 || finished.current) return;
    const timer = window.setTimeout(() => {
      if (finished.current) return;
      finished.current = true;
      onDone();
    }, 500);
    return () => window.clearTimeout(timer);
  }, [ready, step, onDone]);

  const complete = ready && step >= STAGES.length - 1;
  const percent = complete ? 100 : Math.round(((step + 0.4) / STAGES.length) * 100);

  return (
    <div className="rounded-2xl border border-stone-200 bg-white p-6 shadow-sm">
      <p className="text-sm font-medium text-stone-900">Preparing the hiring scorecard</p>
      <p className="mt-1 text-sm text-stone-600" aria-live="polite">
        {STAGES[step]}
      </p>

      <div
        className="relative mt-5 h-2 overflow-hidden rounded-full bg-stone-100"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-label="Scorecard progress"
      >
        <div
          className="relative h-full rounded-full bg-[#6bb82f] transition-[width] duration-700 ease-out"
          style={{ width: `${percent}%` }}
        >
          {!complete && (
            <span className="scorecard-sheen pointer-events-none absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/70 to-transparent" />
          )}
        </div>
      </div>

      <ol className="mt-5 space-y-2">
        {STAGES.map((label, index) => {
          const state = index < step || complete ? "done" : index === step ? "current" : "waiting";
          return (
            <li key={label} className="flex items-center gap-3 text-sm">
              <span
                className={
                  state === "done"
                    ? "flex h-5 w-5 items-center justify-center rounded-full bg-[#6bb82f] text-[11px] font-semibold text-white"
                    : state === "current"
                      ? "flex h-5 w-5 items-center justify-center rounded-full border-2 border-[#6bb82f] bg-white"
                      : "flex h-5 w-5 items-center justify-center rounded-full border border-stone-300 bg-white"
                }
                aria-hidden
              >
                {state === "done" ? "✓" : state === "current" ? "" : ""}
              </span>
              <span className={state === "waiting" ? "text-stone-400" : "text-stone-800"}>{label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
