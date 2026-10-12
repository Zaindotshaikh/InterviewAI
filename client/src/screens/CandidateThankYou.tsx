import ThemeToggle from "../components/ThemeToggle";
import { COMPANY_NAME } from "../config/brand";

export default function CandidateThankYou() {
  return (
    <div className="relative mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-16 text-center">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>
      <div className="mx-auto mb-6 grid h-16 w-16 place-items-center rounded-full bg-[var(--color-accent)]/15 text-2xl text-[var(--color-accent)]">
        ✓
      </div>
      <h1 className="font-[family-name:var(--font-display)] text-4xl text-[var(--color-fg)]">Thank you</h1>
      <p className="mt-4 text-[var(--color-muted)]">
        Your interview is complete. The {COMPANY_NAME} talent team will review your conversation and
        be in touch with next steps.
      </p>
      <p className="mt-8 text-xs text-[var(--color-muted)]">You can close this window.</p>
    </div>
  );
}
