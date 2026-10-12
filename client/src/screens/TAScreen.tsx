import { useEffect, useState } from "react";
import type { CandidateRecord } from "../lib/candidate";

type Role = {
  id: string;
  title: string;
};

type Props = {
  onInterviewCandidate: (candidate: CandidateRecord) => void;
  onOpenLanding: () => void;
};

const fieldClass =
  "w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-3 outline-none ring-[var(--color-accent)] focus:ring-2";

export default function TAScreen({ onInterviewCandidate, onOpenLanding }: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [candidates, setCandidates] = useState<CandidateRecord[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [name, setName] = useState("");
  const [roleId, setRoleId] = useState("");
  const [email, setEmail] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [yearsOfExperience, setYearsOfExperience] = useState("");
  const [resumeText, setResumeText] = useState("");

  async function refresh() {
    const [rolesRes, candRes] = await Promise.all([
      fetch("/api/roles"),
      fetch("/api/candidates"),
    ]);
    if (rolesRes.ok) {
      const data = (await rolesRes.json()) as Role[];
      setRoles(data);
      if (data[0] && !roleId) setRoleId(data[0].id);
    }
    if (candRes.ok) {
      setCandidates((await candRes.json()) as CandidateRecord[]);
    }
  }

  useEffect(() => {
    void refresh().catch(() => setError("Could not load pipeline. Is the server running?"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function saveCandidate() {
    if (!name.trim() || !roleId) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          roleId,
          email: email.trim() || undefined,
          noticePeriod: noticePeriod.trim() || undefined,
          currentCompany: currentCompany.trim() || undefined,
          yearsOfExperience: yearsOfExperience.trim() || undefined,
          resumeText: resumeText.trim() || undefined,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setShowForm(false);
      setName("");
      setEmail("");
      setNoticePeriod("");
      setCurrentCompany("");
      setYearsOfExperience("");
      setResumeText("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save candidate");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-12">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-sm font-medium tracking-[0.2em] text-[var(--color-accent)] uppercase">
            InterviewAI · TA
          </p>
          <h1 className="mt-2 font-[family-name:var(--font-display)] text-4xl text-[var(--color-fg)]">
            Candidate pipeline
          </h1>
          <p className="mt-2 text-[var(--color-muted)]">
            Add candidates with full details. They thread into the interviewer context at session start.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onOpenLanding}
            className="rounded-xl border border-[var(--color-line)] px-4 py-2.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            Candidate landing
          </button>
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-on-accent)]"
          >
            {showForm ? "Close" : "Add Candidate"}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="mb-8 space-y-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/80 p-5">
          <h2 className="text-sm font-semibold tracking-wide text-[var(--color-muted)] uppercase">
            Add Candidate
          </h2>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="block md:col-span-2">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Name *</span>
              <input className={fieldClass} value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="block md:col-span-2">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Role *</span>
              <select className={fieldClass} value={roleId} onChange={(e) => setRoleId(e.target.value)}>
                {roles.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Email</span>
              <input
                className={fieldClass}
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Notice period</span>
              <input
                className={fieldClass}
                value={noticePeriod}
                onChange={(e) => setNoticePeriod(e.target.value)}
                placeholder="e.g. 30 days"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Current company</span>
              <input
                className={fieldClass}
                value={currentCompany}
                onChange={(e) => setCurrentCompany(e.target.value)}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Years of experience</span>
              <input
                className={fieldClass}
                value={yearsOfExperience}
                onChange={(e) => setYearsOfExperience(e.target.value)}
                placeholder="e.g. 5"
              />
            </label>
            <label className="block md:col-span-2">
              <span className="mb-1.5 block text-sm text-[var(--color-muted)]">
                Resume text (optional here; you can upload on landing)
              </span>
              <textarea
                className={fieldClass}
                rows={4}
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value)}
              />
            </label>
          </div>
          <button
            type="button"
            disabled={!name.trim() || !roleId || saving}
            onClick={() => void saveCandidate()}
            className="rounded-xl bg-[var(--color-accent)] px-4 py-3 text-sm font-semibold text-[var(--color-on-accent)] disabled:opacity-40"
          >
            {saving ? "Saving…" : "Save candidate"}
          </button>
        </div>
      )}

      {error && <p className="mb-4 text-sm text-[var(--color-danger)]">{error}</p>}

      <div className="overflow-hidden rounded-2xl border border-[var(--color-line)]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[var(--color-panel)] text-[var(--color-muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Role</th>
              <th className="hidden px-4 py-3 font-medium md:table-cell">Company</th>
              <th className="hidden px-4 py-3 font-medium md:table-cell">Exp / Notice</th>
              <th className="px-4 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {candidates.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-[var(--color-muted)]">
                  No candidates yet. Use Add Candidate to create one.
                </td>
              </tr>
            ) : (
              candidates.map((c) => (
                <tr key={c.id} className="border-t border-[var(--color-line)]">
                  <td className="px-4 py-3 text-[var(--color-fg)]">
                    <div>{c.name}</div>
                    {c.email && (
                      <div className="text-xs text-[var(--color-muted)]">{c.email}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-[var(--color-muted)]">{c.roleAppliedFor}</td>
                  <td className="hidden px-4 py-3 text-[var(--color-muted)] md:table-cell">
                    {c.currentCompany || "-"}
                  </td>
                  <td className="hidden px-4 py-3 text-[var(--color-muted)] md:table-cell">
                    {[c.yearsOfExperience && `${c.yearsOfExperience} yrs`, c.noticePeriod]
                      .filter(Boolean)
                      .join(" · ") || "-"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      type="button"
                      onClick={() => onInterviewCandidate(c)}
                      className="text-sm font-medium text-[var(--color-accent)] hover:underline"
                    >
                      Start interview
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
