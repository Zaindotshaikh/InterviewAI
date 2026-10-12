import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { COMPANY_NAME } from "../config/brand";
import { useTAStore } from "../context/TAStore";
import ThemeToggle from "../components/ThemeToggle";

export default function LoginScreen() {
  const [email, setEmail] = useState("");
  const { login, user } = useTAStore();
  const navigate = useNavigate();

  if (user) return <Navigate to="/dashboard" replace />;

  function signIn() {
    login(email || undefined);
    navigate("/dashboard");
  }

  return (
    <div className="relative grid min-h-screen place-items-center px-6">
      <div className="absolute top-5 right-5 z-40">
        <ThemeToggle />
      </div>
      <div
        className="w-full max-w-md rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/90 p-8"
        style={{ boxShadow: "var(--shadow-panel)" }}
      >
        <div className="mb-8 flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-xl bg-[var(--color-accent)] text-lg font-bold text-[var(--color-on-accent)]">
            K
          </div>
          <div>
            <h1 className="text-lg font-semibold text-[var(--color-fg)]">{COMPANY_NAME}</h1>
            <p className="text-sm text-[var(--color-muted)]">Talent Acquisition Portal</p>
          </div>
        </div>

        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Work email</span>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@kreedalabs.com"
            className="w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-input)] px-4 py-3 outline-none ring-[var(--color-accent)] focus:ring-2"
          />
        </label>

        <button
          type="button"
          onClick={signIn}
          className="mt-5 w-full rounded-xl bg-[var(--color-accent)] px-4 py-3 font-semibold text-[var(--color-on-accent)]"
        >
          Sign in
        </button>

        <button
          type="button"
          onClick={signIn}
          className="mt-3 w-full rounded-xl border border-[var(--color-line)] px-4 py-3 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          Continue as TA Admin
        </button>

        <p className="mt-6 text-center text-xs text-[var(--color-muted)]">
          Demo login. No password required
        </p>
        <p className="mt-3 text-center text-xs text-[var(--color-muted)]">
          Prospect?{" "}
          <Link to="/demo" className="text-[var(--color-accent)] hover:underline">
            Try the live demo
          </Link>
        </p>
      </div>
    </div>
  );
}
