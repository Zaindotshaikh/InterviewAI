import { Navigate, Outlet } from "react-router-dom";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { COMPANY_NAME, PRODUCT_NAME } from "../../config/brand";
import { useTAStore } from "../../context/TAStore";
import ThemeToggle from "../ThemeToggle";

export default function TALayout() {
  const { user, logout } = useTAStore();
  const navigate = useNavigate();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-[var(--color-ink)]">
      <header className="border-b border-[var(--color-line)] bg-[var(--color-panel)]/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3.5">
          <div className="flex items-center gap-6">
            <Link to="/dashboard" className="flex items-center gap-3">
              <div className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--color-accent)] font-semibold text-[var(--color-on-accent)]">
                K
              </div>
              <div>
                <p className="text-sm font-semibold text-[var(--color-fg)]">{COMPANY_NAME}</p>
                <p className="text-[10px] tracking-wide text-[var(--color-muted)] uppercase">
                  {PRODUCT_NAME} · TA Portal
                </p>
              </div>
            </Link>
            <nav className="hidden items-center gap-1 text-sm sm:flex">
              <NavLink
                to="/dashboard"
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 ${isActive ? "bg-[var(--color-hover)] text-[var(--color-fg)]" : "text-[var(--color-muted)] hover:text-[var(--color-fg)]"}`
                }
              >
                Dashboard
              </NavLink>
            </nav>
          </div>
          <div className="flex items-center gap-3 sm:gap-4">
            <div className="text-right">
              <p className="text-sm text-[var(--color-fg)]">{user.name}</p>
              <p className="text-xs text-[var(--color-muted)]">{user.role}</p>
            </div>
            <ThemeToggle />
            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/login");
              }}
              className="rounded-lg border border-[var(--color-line)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
