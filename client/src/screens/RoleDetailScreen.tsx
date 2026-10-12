import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useTAStore } from "../context/TAStore";
import type { CandidateStatus } from "../data/mockData";

const statusColor: Record<CandidateStatus, string> = {
  "Not Invited": "bg-[var(--color-hover)] text-[var(--color-muted)]",
  Invited: "bg-sky-500/15 text-sky-300 light:text-sky-800",
  "In Progress": "bg-[var(--color-warn)]/15 text-[var(--color-warn)]",
  Completed: "bg-[var(--color-accent)]/15 text-[var(--color-accent)]",
  Reviewed: "bg-violet-500/15 text-violet-300 light:text-violet-800",
  Shortlisted: "bg-emerald-500/15 text-emerald-300 light:text-emerald-800",
  Rejected: "bg-[var(--color-danger)]/15 text-[var(--color-danger)]",
};

export default function RoleDetailScreen() {
  const { roleId = "" } = useParams();
  const {
    getRole,
    getCandidatesForRole,
    inviteCandidate,
    addCandidate,
  } = useTAStore();
  const role = getRole(roleId);
  const candidates = getCandidatesForRole(roleId);

  const [inviteModal, setInviteModal] = useState<{
    name: string;
    email: string;
    link: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [addForm, setAddForm] = useState({
    name: "",
    email: "",
    noticePeriod: "",
    currentCompany: "",
    yearsOfExperience: "",
    resumeText: "",
  });
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const sorted = useMemo(
    () =>
      [...candidates].sort((a, b) => a.name.localeCompare(b.name)),
    [candidates],
  );

  if (!role) {
    return (
      <p className="text-[var(--color-muted)]">
        Role not found. <Link to="/dashboard" className="text-[var(--color-accent)]">Back</Link>
      </p>
    );
  }

  function sendInvite(candidateId: string, name: string, email: string) {
    const { link } = inviteCandidate(candidateId);
    setInviteModal({ name, email, link });
    setCopied(false);
  }

  async function handleAddCandidate() {
    if (!addForm.name.trim() || !addForm.email.trim()) return;
    setAdding(true);
    setAddError(null);
    try {
      let resumeText = addForm.resumeText.trim() || undefined;
      if (resumeFile) {
        const form = new FormData();
        form.append("resume", resumeFile);
        const res = await fetch("/api/resume/parse", { method: "POST", body: form });
        if (!res.ok) throw new Error(await res.text());
        const data = (await res.json()) as { text: string };
        resumeText = data.text;
      }

      const created = addCandidate({
        roleId,
        name: addForm.name,
        email: addForm.email,
        noticePeriod: addForm.noticePeriod || undefined,
        currentCompany: addForm.currentCompany || undefined,
        yearsOfExperience: addForm.yearsOfExperience || undefined,
        resumeText,
      });

      // Also persist to server candidates store for interview context reuse
      void fetch("/api/candidates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: created.name,
          roleId,
          email: created.email,
          noticePeriod: created.noticePeriod,
          currentCompany: created.currentCompany,
          yearsOfExperience: created.yearsOfExperience,
          resumeText: created.resumeText,
        }),
      });

      setShowAdd(false);
      setAddForm({
        name: "",
        email: "",
        noticePeriod: "",
        currentCompany: "",
        yearsOfExperience: "",
        resumeText: "",
      });
      setResumeFile(null);
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add candidate");
    } finally {
      setAdding(false);
    }
  }

  return (
    <div>
      <Link to="/dashboard" className="text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]">
        ← Dashboard
      </Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-3xl text-[var(--color-fg)]">
            {role.title}
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[var(--color-muted)]">
            Evaluation criteria: {role.criteria.join(" · ")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          className="rounded-xl bg-[var(--color-accent)] px-4 py-2.5 text-sm font-semibold text-[var(--color-on-accent)]"
        >
          Add Candidate
        </button>
      </div>

      <div className="mt-8 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)] shadow-[var(--shadow-card)]">
        <table className="w-full text-left text-sm">
          <thead className="bg-[var(--color-panel)] text-[var(--color-muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="hidden px-4 py-3 font-medium md:table-cell">Date invited</th>
              <th className="px-4 py-3 font-medium">Score</th>
              <th className="px-4 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((c) => (
              <tr key={c.id} className="border-t border-[var(--color-line)]">
                <td className="px-4 py-3">
                  <div className="text-[var(--color-fg)]">{c.name}</div>
                  <div className="text-xs text-[var(--color-muted)]">{c.email}</div>
                </td>
                <td className="px-4 py-3">
                  <span className={`rounded-full px-2.5 py-1 text-xs ${statusColor[c.status]}`}>
                    {c.status}
                  </span>
                </td>
                <td className="hidden px-4 py-3 text-[var(--color-muted)] md:table-cell">
                  {c.dateInvited ?? "-"}
                </td>
                <td className="px-4 py-3 tabular-nums text-[var(--color-muted)]">
                  {c.score != null ? `${c.score}/10` : "-"}
                </td>
                <td className="px-4 py-3 text-right">
                  {c.status === "Not Invited" && (
                    <button
                      type="button"
                      onClick={() => sendInvite(c.id, c.name, c.email)}
                      className="text-[var(--color-accent)] hover:underline"
                    >
                      Send Interview Invite
                    </button>
                  )}
                  {(c.status === "Invited" || c.status === "In Progress") && c.inviteToken && (
                    <button
                      type="button"
                      onClick={() =>
                        setInviteModal({
                          name: c.name,
                          email: c.email,
                          link: `${window.location.origin}/i/${c.inviteToken}`,
                        })
                      }
                      className="text-[var(--color-muted)] hover:text-[var(--color-fg)]"
                    >
                      Copy invite link
                    </button>
                  )}
                  {["Completed", "Reviewed", "Shortlisted", "Rejected"].includes(c.status) &&
                    c.scorecard && (
                      <Link
                        to={`/candidates/${c.id}/scorecard`}
                        className="text-[var(--color-accent)] hover:underline"
                      >
                        View Scorecard
                      </Link>
                    )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {inviteModal && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[var(--color-overlay)] px-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)] p-6">
            <h2 className="text-lg font-semibold text-[var(--color-fg)]">Interview invite</h2>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Share this link with <span className="text-[var(--color-fg)]">{inviteModal.name}</span> (
              {inviteModal.email}). No email is sent in this demo.
            </p>
            <div className="mt-4 rounded-xl border border-[var(--color-line)] bg-[var(--color-input)] px-3 py-2 text-sm break-all text-[var(--color-accent)]">
              {inviteModal.link}
            </div>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={() => setInviteModal(null)}
                className="rounded-lg px-3 py-2 text-sm text-[var(--color-muted)]"
              >
                Close
              </button>
              <button
                type="button"
                onClick={async () => {
                  await navigator.clipboard.writeText(inviteModal.link);
                  setCopied(true);
                }}
                className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
              >
                {copied ? "Copied" : "Copy Link"}
              </button>
              <button
                type="button"
                onClick={() => window.open(inviteModal.link, "_blank", "noopener,noreferrer")}
                className="rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-[var(--color-on-accent)]"
              >
                Open invite
              </button>
            </div>
          </div>
        </div>
      )}

      {showAdd && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[var(--color-overlay)] px-4 backdrop-blur-sm">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)] p-6">
            <h2 className="text-lg font-semibold text-[var(--color-fg)]">Add Candidate</h2>
            <div className="mt-4 space-y-3">
              {(
                [
                  ["name", "Name *"],
                  ["email", "Email *"],
                  ["currentCompany", "Current company"],
                  ["yearsOfExperience", "Years of experience"],
                  ["noticePeriod", "Notice period"],
                ] as const
              ).map(([key, label]) => (
                <label key={key} className="block">
                  <span className="mb-1 block text-xs text-[var(--color-muted)]">{label}</span>
                  <input
                    className="w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-input)] px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
                    value={addForm[key]}
                    onChange={(e) => setAddForm((f) => ({ ...f, [key]: e.target.value }))}
                  />
                </label>
              ))}
              <label className="block">
                <span className="mb-1 block text-xs text-[var(--color-muted)]">Resume PDF</span>
                <input
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                  className="text-sm text-[var(--color-muted)]"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-[var(--color-muted)]">Or paste resume text</span>
                <textarea
                  rows={4}
                  className="w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-input)] px-3 py-2 text-sm"
                  value={addForm.resumeText}
                  onChange={(e) => setAddForm((f) => ({ ...f, resumeText: e.target.value }))}
                />
              </label>
            </div>
            {addError && <p className="mt-2 text-sm text-[var(--color-danger)]">{addError}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="rounded-lg px-3 py-2 text-sm text-[var(--color-muted)]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={adding || !addForm.name.trim() || !addForm.email.trim()}
                onClick={() => void handleAddCandidate()}
                className="rounded-lg bg-[var(--color-accent)] px-3 py-2 text-sm font-semibold text-[var(--color-on-accent)] disabled:opacity-40"
              >
                {adding ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
