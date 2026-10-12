import { Link } from "react-router-dom";
import {
  COMPANY_NAME,
  INTERVIEWER_NAME,
  INTERVIEWER_TITLE,
  PRODUCT_NAME,
} from "../../config/brand";
import ThemeToggle from "../../components/ThemeToggle";

type Props = {
  interviewerName?: string;
  interviewerTitle?: string;
  onStart: () => void;
};

const STEPS = [
  {
    n: "01",
    title: "Your details",
    body: "Name, work email, company, and industry, so we can set the scene.",
  },
  {
    n: "02",
    title: "Pick a role",
    body: "Choose a senior, mid, or junior brief from your industry, with a job description and resume.",
  },
  {
    n: "03",
    title: "Go live",
    body: "A real spoken interview. Camera on, mic on: the same session your candidates would sit.",
  },
];

export default function DemoLanding({
  interviewerName = INTERVIEWER_NAME,
  interviewerTitle = INTERVIEWER_TITLE,
  onStart,
}: Props) {
  return (
    <div className="relative mx-auto flex min-h-screen max-w-3xl flex-col justify-center px-6 py-16">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>

      <p className="text-sm font-medium tracking-[0.2em] text-[var(--color-accent)] uppercase">
        {COMPANY_NAME} · {PRODUCT_NAME}
      </p>
      <h1 className="mt-3 font-[family-name:var(--font-display)] text-4xl leading-tight text-[var(--color-fg)] md:text-5xl">
        Sit a live interview. See how your candidates will feel.
      </h1>
      <p className="mt-4 max-w-xl text-[var(--color-muted)]">
        This is not a slide deck. You will speak with {interviewerName}, our AI{" "}
        {interviewerTitle.toLowerCase()}, on a role from your industry, tailored to a resume, with
        presence checks on.
      </p>

      <div className="mt-8 flex items-center gap-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/80 p-4">
        <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-[var(--color-accent)] text-xl font-bold text-[var(--color-on-accent)]">
          {interviewerName.slice(0, 1)}
        </div>
        <div>
          <p className="text-sm font-medium text-[var(--color-fg)]">Meet {interviewerName}</p>
          <p className="text-sm text-[var(--color-muted)]">
            {interviewerTitle} · live voice, one question at a time
          </p>
        </div>
      </div>

      <ol className="mt-8 grid gap-3 sm:grid-cols-3">
        {STEPS.map((step) => (
          <li
            key={step.n}
            className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/60 p-4"
          >
            <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-accent)]">
              {step.n}
            </p>
            <p className="mt-2 text-sm font-medium text-[var(--color-fg)]">
              {step.n === "03" ? `Go live with ${interviewerName}` : step.title}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-[var(--color-muted)]">{step.body}</p>
          </li>
        ))}
      </ol>

      <button
        type="button"
        onClick={onStart}
        className="mt-10 w-full rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)] transition hover:brightness-110 sm:w-auto sm:min-w-64"
      >
        Start Live Demo
      </button>
      <p className="mt-3 text-xs text-[var(--color-muted)]">
        About 10 minutes once you begin · microphone and camera required
      </p>

      <p className="mt-10 text-sm text-[var(--color-muted)]">
        Talent team?{" "}
        <Link to="/login" className="text-[var(--color-accent)] hover:underline">
          Open the TA portal
        </Link>
      </p>
    </div>
  );
}
