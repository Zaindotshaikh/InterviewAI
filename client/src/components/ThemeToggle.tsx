import { useTheme } from "../context/Theme";

type Props = {
  className?: string;
};

export default function ThemeToggle({ className = "" }: Props) {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${next} theme`}
      title={`Switch to ${next} theme`}
      className={`grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--color-line)] bg-[var(--color-panel)] text-[var(--color-muted)] transition hover:border-[var(--color-accent)]/40 hover:text-[var(--color-fg)] ${className}`}
    >
      {theme === "dark" ? (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path
            strokeLinecap="round"
            d="M12 3v1.5M12 19.5V21M4.93 4.93l1.06 1.06M18.01 18.01l1.06 1.06M3 12h1.5M19.5 12H21M4.93 19.07l1.06-1.06M18.01 5.99l1.06-1.06"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M21 14.3A8.4 8.4 0 1 1 9.7 3 6.6 6.6 0 0 0 21 14.3z"
          />
        </svg>
      )}
    </button>
  );
}
