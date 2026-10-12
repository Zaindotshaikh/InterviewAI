import { Link } from "react-router-dom";
import { DASHBOARD_STATS } from "../data/mockData";
import { useTAStore } from "../context/TAStore";

export default function DashboardScreen() {
  const { roles, roleStats, candidates } = useTAStore();

  const liveCompleted = candidates.filter((c) => c.interviewId).length;

  const cards = [
    { label: "Open Roles", value: DASHBOARD_STATS.openRoles },
    { label: "Candidates in Pipeline", value: candidates.length },
    {
      label: "Interviews Completed This Week",
      value: DASHBOARD_STATS.interviewsCompletedThisWeek + liveCompleted,
    },
    { label: "Avg. Time-to-Screen", value: `${DASHBOARD_STATS.avgTimeToScreenDays}d` },
  ];

  return (
    <div>
      <h1 className="font-[family-name:var(--font-display)] text-3xl text-[var(--color-fg)]">Dashboard</h1>
      <p className="mt-1 text-[var(--color-muted)]">Hiring overview across open roles</p>

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((c) => (
          <div
            key={c.label}
            className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/70 p-5 shadow-[var(--shadow-card)]"
          >
            <p className="text-xs tracking-wide text-[var(--color-muted)] uppercase">{c.label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums text-[var(--color-fg)]">{c.value}</p>
          </div>
        ))}
      </div>

      <div className="mt-10 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)] shadow-[var(--shadow-card)]">
        <div className="border-b border-[var(--color-line)] bg-[var(--color-panel)] px-5 py-3">
          <h2 className="text-sm font-semibold text-[var(--color-fg)]">Active roles</h2>
        </div>
        <table className="w-full text-left text-sm">
          <thead className="text-[var(--color-muted)]">
            <tr>
              <th className="px-5 py-3 font-medium">Role</th>
              <th className="px-5 py-3 font-medium">Candidates</th>
              <th className="px-5 py-3 font-medium">Completed</th>
              <th className="px-5 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {roles.map((role) => {
              const stats = roleStats(role.id);
              return (
                <tr key={role.id} className="border-t border-[var(--color-line)]">
                  <td className="px-5 py-3.5 text-[var(--color-fg)]">{role.title}</td>
                  <td className="px-5 py-3.5 tabular-nums text-[var(--color-muted)]">
                    {stats.candidates}
                  </td>
                  <td className="px-5 py-3.5 tabular-nums text-[var(--color-muted)]">
                    {stats.completed}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <Link
                      to={`/roles/${role.id}`}
                      className="text-[var(--color-accent)] hover:underline"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
