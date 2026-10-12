import { useMemo, useState } from "react";
import ThemeToggle from "../../components/ThemeToggle";
import type { DemoIndustry, DemoProspect } from "./types";

const fieldClass =
  "w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-3 outline-none ring-[var(--color-accent)] focus:ring-2";

type Props = {
  industries: DemoIndustry[];
  initial?: Partial<DemoProspect>;
  submitting?: boolean;
  error?: string | null;
  onBack: () => void;
  onContinue: (prospect: DemoProspect) => void;
};

export default function DemoDetailsStep({
  industries,
  initial,
  submitting,
  error,
  onBack,
  onContinue,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [email, setEmail] = useState(initial?.email ?? "");
  const [company, setCompany] = useState(initial?.company ?? "");
  const [industry, setIndustry] = useState(initial?.industry ?? "");

  const emailOk = useMemo(() => /\S+@\S+\.\S+/.test(email.trim()), [email]);
  const ready = name.trim().length > 1 && emailOk && company.trim().length > 1 && Boolean(industry);

  return (
    <div className="relative mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>

      <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-accent)] uppercase">
        Step 1 of 2
      </p>
      <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--color-fg)] md:text-4xl">
        Who&apos;s trying the demo?
      </h1>
      <p className="mt-3 text-[var(--color-muted)]">
        We use this to personalize the session and so our team can follow up. You will sit the
        interview as the candidate.
      </p>

      <div className="mt-8 space-y-5">
        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Your name</span>
          <input
            className={fieldClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Alex Rivera"
            autoComplete="name"
            disabled={submitting}
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Work email</span>
          <input
            className={fieldClass}
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoComplete="email"
            disabled={submitting}
          />
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Company</span>
          <input
            className={fieldClass}
            value={company}
            onChange={(e) => setCompany(e.target.value)}
            placeholder="Acme Health"
            autoComplete="organization"
            disabled={submitting}
          />
        </label>

        <div>
          <span className="mb-2 block text-sm text-[var(--color-muted)]">Industry</span>
          <div className="grid grid-cols-2 gap-2">
            {industries.map((item) => {
              const selected = industry === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  disabled={submitting}
                  onClick={() => setIndustry(item.id)}
                  className={`rounded-xl border px-3 py-3 text-left transition ${
                    selected
                      ? "border-[var(--color-accent)] bg-[var(--color-accent-dim)]"
                      : "border-[var(--color-line)] bg-[var(--color-panel)] hover:border-[var(--color-muted)]"
                  }`}
                >
                  <p className="text-sm font-medium text-[var(--color-fg)]">{item.label}</p>
                  <p className="mt-0.5 text-xs text-[var(--color-muted)]">{item.blurb}</p>
                </button>
              );
            })}
          </div>
        </div>

        {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}

        <div className="flex gap-3">
          <button
            type="button"
            onClick={onBack}
            disabled={submitting}
            className="rounded-xl border border-[var(--color-line)] px-4 py-3.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            Back
          </button>
          <button
            type="button"
            disabled={!ready || submitting}
            onClick={() =>
              onContinue({
                name: name.trim(),
                email: email.trim(),
                company: company.trim(),
                industry,
              })
            }
            className="flex-1 rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)] transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {submitting ? "Saving…" : "Continue"}
          </button>
        </div>
      </div>
    </div>
  );
}
