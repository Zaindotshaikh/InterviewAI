import { COMPANY_NAME, PRODUCT_NAME } from "../config/brand";
import { summarizeIntegrityEvents } from "../lib/integrity";
import type { InterviewSession, Scorecard } from "../types/session";

type Props = {
  session: InterviewSession;
  scorecard: Scorecard | null;
  onRestart: () => void;
  hideActions?: boolean;
  /** TA-only integrity notes (never shown on candidate thank-you path) */
  showIntegrity?: boolean;
};

export default function SummaryScreen({
  session,
  scorecard,
  onRestart,
  hideActions,
  showIntegrity,
}: Props) {
  const score = scorecard?.overall_score ?? 0;
  const pct = Math.round((score / 10) * 100);
  const integrityLines = scorecard?.integrity
    ? summarizeIntegrityEvents(scorecard.integrity.events)
    : [];


  return (
    <div className="mx-auto max-w-2xl px-6 py-12 print:bg-white print:text-black">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium tracking-[0.2em] text-[var(--color-accent)] uppercase print:text-lime-800">
            {PRODUCT_NAME} · {COMPANY_NAME} Scorecard
          </p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl text-[var(--color-fg)] print:text-black">
            {session.candidateName}
          </h1>
          <p className="mt-1 text-[var(--color-muted)] print:text-neutral-600">{session.roleTitle}</p>
        </div>
        {!hideActions && (
          <div className="flex gap-2 print:hidden">
            <button
              type="button"
              onClick={() => window.print()}
              className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            >
              Print / Export
            </button>
            <button
              type="button"
              onClick={onRestart}
              className="rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-[var(--color-on-accent)]"
            >
              New interview
            </button>
          </div>
        )}
        {hideActions && (
          <button
            type="button"
            onClick={() => window.print()}
            className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)] print:hidden"
          >
            Print / Export
          </button>
        )}
      </div>

      {!scorecard ? (
        <p className="animate-pulse text-[var(--color-muted)]">Generating scorecard…</p>
      ) : (
        <div className="space-y-8">
          <div className="flex items-center gap-6 rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)] p-6 print:border-neutral-200 print:bg-neutral-50">
            <div
              className="relative grid h-28 w-28 place-items-center rounded-full"
              style={{
                background: `conic-gradient(var(--color-accent) ${pct}%, var(--color-line) 0)`,
              }}
            >
              <div className="absolute inset-[8px] grid place-items-center rounded-full bg-[var(--color-panel)] print:bg-neutral-50">
                <span className="text-3xl font-semibold tabular-nums">{score}</span>
                <span className="text-[10px] tracking-wide text-[var(--color-muted)] uppercase">
                  / 10
                </span>
              </div>
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-medium text-[var(--color-fg)] print:text-black">Recommendation</h2>
              <p className="mt-2 leading-relaxed text-[var(--color-muted)] print:text-neutral-700">
                {scorecard.recommendation}
              </p>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <section>
              <h3 className="mb-3 text-sm font-semibold tracking-wide text-[var(--color-accent)] uppercase">
                Strengths
              </h3>
              <ul className="space-y-2">
                {scorecard.strengths.map((s) => (
                  <li
                    key={s}
                    className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)]/60 px-3 py-2 text-sm print:border-neutral-200"
                  >
                    {s}
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="mb-3 text-sm font-semibold tracking-wide text-[var(--color-warn)] uppercase">
                Gaps
              </h3>
              <ul className="space-y-2">
                {scorecard.gaps.map((g) => (
                  <li
                    key={g}
                    className="rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)]/60 px-3 py-2 text-sm print:border-neutral-200"
                  >
                    {g}
                  </li>
                ))}
              </ul>
            </section>
          </div>

          <section>
            <h3 className="mb-3 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
              Per-question notes
            </h3>
            <div className="space-y-3">
              {scorecard.per_question_notes.map((n) => (
                <div
                  key={n.question}
                  className="rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)]/50 p-4 print:border-neutral-200"
                >
                  <p className="text-sm font-medium text-[var(--color-fg)] print:text-black">{n.question}</p>
                  <p className="mt-1.5 text-sm text-[var(--color-muted)] print:text-neutral-700">
                    {n.note}
                  </p>
                </div>
              ))}
            </div>
          </section>

          {showIntegrity && (
            <section className="rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)]/40 p-4">
              <h3 className="mb-2 text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
                Integrity notes
              </h3>
              {!scorecard.integrity || scorecard.integrity.available === false ? (
                <p className="text-sm text-[var(--color-muted)]">
                  Camera monitoring unavailable
                </p>
              ) : integrityLines.length === 0 ? (
                <p className="text-sm text-[var(--color-muted)]">
                  No integrity concerns detected
                </p>
              ) : (
                <ul className="space-y-1.5 text-sm text-[var(--color-caption)]">
                  {integrityLines.map((line) => (
                    <li key={line}>• {line}</li>
                  ))}
                </ul>
              )}
              <p className="mt-2 text-xs text-[var(--color-muted)]">
                Informational signal for review only, not an automatic disqualification.
              </p>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
