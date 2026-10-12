import { Link } from "react-router-dom";
import ThemeToggle from "../../components/ThemeToggle";
import { COMPANY_NAME, INTERVIEWER_NAME, PRODUCT_NAME } from "../../config/brand";
import SummaryScreen from "../SummaryScreen";
import type { InterviewSession, Scorecard } from "../../types/session";

type Props = {
  session: InterviewSession;
  scorecard: Scorecard | null;
  interviewerName?: string;
  onTryAnotherRole: () => void;
  onStartOver: () => void;
};

export default function DemoComplete({
  session,
  scorecard,
  interviewerName = INTERVIEWER_NAME,
  onTryAnotherRole,
  onStartOver,
}: Props) {
  return (
    <div className="relative min-h-screen px-0 py-8">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>

      <div className="mx-auto max-w-2xl px-6">
        <p className="text-sm font-medium tracking-[0.2em] text-[var(--color-accent)] uppercase">
          {PRODUCT_NAME} live demo
        </p>
        <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--color-fg)] md:text-4xl">
          That&apos;s the candidate experience.
        </h1>
        <p className="mt-3 text-[var(--color-muted)]">
          {interviewerName} just ran a real interview. Below is the scorecard your talent team would
          open next: strengths, gaps, and notes against the brief. This is the hiring-side of{" "}
          {COMPANY_NAME} {PRODUCT_NAME}.
        </p>
      </div>

      <SummaryScreen
        session={session}
        scorecard={scorecard}
        onRestart={onTryAnotherRole}
        hideActions
        showIntegrity
      />

      <div className="mx-auto mt-2 flex max-w-2xl flex-col gap-3 px-6 pb-16 sm:flex-row">
        <button
          type="button"
          onClick={onTryAnotherRole}
          className="flex-1 rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)]"
        >
          Try another role
        </button>
        <button
          type="button"
          onClick={onStartOver}
          className="rounded-xl border border-[var(--color-line)] px-4 py-3.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          Start over
        </button>
        <Link
          to="/login"
          className="grid place-items-center rounded-xl border border-[var(--color-line)] px-4 py-3.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          TA portal
        </Link>
      </div>
    </div>
  );
}
