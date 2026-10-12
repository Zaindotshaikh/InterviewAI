import { useEffect, useMemo, useState } from "react";
import type { InterviewSession } from "../types/session";
import {
  buildClientCandidateContext,
  type CandidateRecord,
} from "../lib/candidate";
import { MicTestCard } from "../components/WaveformVisualizer";
import { OrbitingLoader } from "../components/OrbitingLoader";
import ThemeToggle from "../components/ThemeToggle";

type Role = {
  id: string;
  title: string;
  questions: string[];
  criteria: string[];
};

type Props = {
  onStarted: (session: InterviewSession) => void;
  onOpenTA?: () => void;
  /** Prefill from TA pipeline / invite */
  prefillCandidate?: CandidateRecord | null;
  /** Candidate invite flow: hide TA chrome */
  candidateMode?: boolean;
};

type PrepStep = "idle" | "parsing" | "generating" | "starting";

const fieldClass =
  "w-full rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)] px-4 py-3 outline-none ring-[var(--color-accent)] focus:ring-2 disabled:opacity-60";

export default function SetupScreen({
  onStarted,
  onOpenTA,
  prefillCandidate,
  candidateMode,
}: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [, setCandidateId] = useState<string | undefined>();
  const [candidateName, setCandidateName] = useState("");
  const [roleId, setRoleId] = useState("");
  const [email, setEmail] = useState("");
  const [noticePeriod, setNoticePeriod] = useState("");
  const [currentCompany, setCurrentCompany] = useState("");
  const [yearsOfExperience, setYearsOfExperience] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumePaste, setResumePaste] = useState("");
  const [resumeMode, setResumeMode] = useState<"pdf" | "paste">("pdf");
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const [prepStep, setPrepStep] = useState<PrepStep>("idle");
  const [error, setError] = useState<string | null>(null);

  const selectedRole = useMemo(
    () => roles.find((r) => r.id === roleId) ?? null,
    [roles, roleId],
  );

  const hasResume =
    resumeMode === "pdf"
      ? Boolean(resumeFile) || resumePaste.trim().length > 40
      : resumePaste.trim().length > 40;

  const loading = prepStep !== "idle";

  useEffect(() => {
    void fetch("/api/roles")
      .then((r) => r.json())
      .then((data: Role[]) => {
        setRoles(data);
        // Prefer invited/prefilled role; never clobber it with roles[0]
        setRoleId((current) => {
          if (current) return current;
          if (prefillCandidate?.roleId) return prefillCandidate.roleId;
          return data[0]?.id ?? "";
        });
      })
      .catch(() => setError("Could not load roles. Is the server running?"));
  }, [prefillCandidate?.roleId]);

  useEffect(() => {
    if (!prefillCandidate) return;
    setCandidateId(prefillCandidate.id);
    setCandidateName(prefillCandidate.name);
    setRoleId(prefillCandidate.roleId);
    setEmail(prefillCandidate.email ?? "");
    setNoticePeriod(prefillCandidate.noticePeriod ?? "");
    setCurrentCompany(prefillCandidate.currentCompany ?? "");
    setYearsOfExperience(prefillCandidate.yearsOfExperience ?? "");
    if (prefillCandidate.resumeText?.trim()) {
      setResumePaste(prefillCandidate.resumeText);
      setResumeMode("paste");
    }
  }, [prefillCandidate]);

  useEffect(() => {
    let stream: MediaStream | null = null;
    let cancelled = false;

    async function enableMic() {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        setMicStream(stream);
        setMicError(null);
      } catch {
        setMicError("Microphone permission denied or unavailable");
      }
    }

    void enableMic();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function parseResume(): Promise<string> {
    setPrepStep("parsing");

    if (resumeMode === "paste" || (!resumeFile && resumePaste.trim())) {
      const res = await fetch("/api/resume/parse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: resumePaste.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { text: string };
      return data.text;
    }

    if (!resumeFile) throw new Error("Resume PDF is required");

    const form = new FormData();
    form.append("resume", resumeFile);
    const res = await fetch("/api/resume/parse", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { text: string };
    return data.text;
  }

  async function startInterview() {
    // Invite flow: dashboard pipeline name is authoritative (not resume / editable form drift)
    const authoritativeName = (
      candidateMode && prefillCandidate?.name?.trim()
        ? prefillCandidate.name
        : candidateName
    ).trim();

    if (!authoritativeName || !roleId || !selectedRole || !hasResume) return;
    setError(null);

    try {
      micStream?.getTracks().forEach((t) => t.stop());
      setMicStream(null);

      const resumeText = await parseResume();

      const candidateContext = buildClientCandidateContext({
        name: authoritativeName,
        roleAppliedFor: selectedRole.title,
        resumeText,
        email,
        noticePeriod,
        currentCompany,
        yearsOfExperience,
      });

      // Mock pipeline IDs live only in the TA client store. Upsert a real server
      // candidate so start/resume flows never 404 on "Candidate not found".
      let serverCandidateId: string | undefined;
      try {
        const upsertRes = await fetch("/api/candidates", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: candidateContext.name,
            roleId,
            email: candidateContext.email,
            noticePeriod: candidateContext.noticePeriod,
            currentCompany: candidateContext.currentCompany,
            yearsOfExperience: candidateContext.yearsOfExperience,
            resumeText: candidateContext.resumeText,
          }),
        });
        if (upsertRes.ok) {
          const saved = (await upsertRes.json()) as { id: string };
          serverCandidateId = saved.id;
          setCandidateId(saved.id);
        }
      } catch {
        // Non-fatal; interview can proceed with candidateContext alone
      }

      setPrepStep("generating");
      const genRes = await fetch("/api/interview/generate-questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidateContext,
          roleCriteria: selectedRole.criteria,
        }),
      });
      if (!genRes.ok) throw new Error(await genRes.text());
      const genData = (await genRes.json()) as { resume_questions: string[] };

      setPrepStep("starting");
      const startRes = await fetch("/api/interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roleId,
          candidateId: serverCandidateId,
          candidateContext,
          resumeQuestions: genData.resume_questions,
        }),
      });
      if (!startRes.ok) throw new Error(await startRes.text());
      const data = (await startRes.json()) as InterviewSession;
      onStarted(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start interview");
      setPrepStep("idle");
    }
  }

  return (
    <div className="relative mx-auto flex min-h-screen max-w-xl flex-col justify-center px-6 py-16">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>
      {loading && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[var(--color-ink)]/90">
          <div className="mx-6 text-center">
            <OrbitingLoader size={112} />
            <p className="mt-8 text-base text-[var(--color-muted)]">
              Please wait while processing
            </p>
          </div>
        </div>
      )}

      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="text-sm font-medium tracking-[0.2em] text-[var(--color-accent)] uppercase">
          InterviewAI
        </p>
        {onOpenTA && !candidateMode && (
          <button
            type="button"
            onClick={onOpenTA}
            className="text-xs text-[var(--color-muted)] hover:text-[var(--color-fg)]"
          >
            TA pipeline →
          </button>
        )}
      </div>
      <h1 className="font-[family-name:var(--font-display)] text-4xl leading-tight text-[var(--color-fg)] md:text-5xl">
        Voice interview, ready when you are.
      </h1>
      <p className="mt-3 text-[var(--color-muted)]">
        Enter candidate details, add a resume, confirm your mic, then start a live spoken interview.
      </p>

      <div className="mt-10 space-y-5">
        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Candidate name</span>
          <input
            className={fieldClass}
            value={candidateName}
            onChange={(e) => setCandidateName(e.target.value)}
            placeholder="Alex Rivera"
            disabled={loading || Boolean(candidateMode && prefillCandidate?.name)}
            readOnly={Boolean(candidateMode && prefillCandidate?.name)}
            title={
              candidateMode && prefillCandidate?.name
                ? "Name is set from the TA dashboard invite"
                : undefined
            }
          />
          {candidateMode && prefillCandidate?.name ? (
            <span className="mt-1.5 block text-xs text-[var(--color-muted)]">
              Locked to the name from your interview invite.
            </span>
          ) : null}
        </label>

        <label className="block">
          <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Role / interview type</span>
          <select
            className={fieldClass}
            value={roleId}
            onChange={(e) => setRoleId(e.target.value)}
            disabled={loading || Boolean(candidateMode && prefillCandidate?.roleId)}
          >
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title}
              </option>
            ))}
          </select>
          {candidateMode && prefillCandidate?.roleId && (
            <p className="mt-1.5 text-xs text-[var(--color-muted)]">
              Role is set from your interview invite.
            </p>
          )}
        </label>

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Email</span>
            <input
              className={fieldClass}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={loading}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Notice period</span>
            <input
              className={fieldClass}
              value={noticePeriod}
              onChange={(e) => setNoticePeriod(e.target.value)}
              placeholder="e.g. 30 days"
              disabled={loading}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Current company</span>
            <input
              className={fieldClass}
              value={currentCompany}
              onChange={(e) => setCurrentCompany(e.target.value)}
              disabled={loading}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-sm text-[var(--color-muted)]">Years of experience</span>
            <input
              className={fieldClass}
              value={yearsOfExperience}
              onChange={(e) => setYearsOfExperience(e.target.value)}
              placeholder="e.g. 5"
              disabled={loading}
            />
          </label>
        </div>

        <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-panel)]/80 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="text-sm text-[var(--color-muted)]">Resume</span>
            <div className="flex rounded-lg border border-[var(--color-line)] p-0.5 text-xs">
              <button
                type="button"
                disabled={loading}
                onClick={() => setResumeMode("pdf")}
                className={`rounded-md px-2.5 py-1 ${
                  resumeMode === "pdf"
                    ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
                    : "text-[var(--color-muted)]"
                }`}
              >
                Upload PDF
              </button>
              <button
                type="button"
                disabled={loading}
                onClick={() => setResumeMode("paste")}
                className={`rounded-md px-2.5 py-1 ${
                  resumeMode === "paste"
                    ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
                    : "text-[var(--color-muted)]"
                }`}
              >
                Paste text
              </button>
            </div>
          </div>

          {resumeMode === "pdf" ? (
            <label className="block">
              <input
                type="file"
                accept="application/pdf,.pdf"
                disabled={loading}
                onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm text-[var(--color-muted)] file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--color-accent-dim)] file:px-3 file:py-2 file:text-sm file:font-medium file:text-[var(--color-accent)]"
              />
              {resumeFile && (
                <p className="mt-2 text-xs text-[var(--color-accent)]">{resumeFile.name}</p>
              )}
              {!resumeFile && resumePaste.trim() && (
                <p className="mt-2 text-xs text-[var(--color-muted)]">
                  Prefill resume text available. Switch to Paste text, or upload a PDF to replace it.
                </p>
              )}
            </label>
          ) : (
            <textarea
              rows={6}
              disabled={loading}
              value={resumePaste}
              onChange={(e) => setResumePaste(e.target.value)}
              placeholder="Paste the candidate's resume text here…"
              className="w-full resize-y rounded-lg border border-[var(--color-line)] bg-[var(--color-input)] px-3 py-2 text-sm outline-none ring-[var(--color-accent)] focus:ring-2"
            />
          )}
          <p className="mt-2 text-xs text-[var(--color-muted)]">
            Required. Used with candidate details to generate tailored questions before the live session.
          </p>
        </div>

        <MicTestCard stream={micStream} error={micError} />

        {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}

        <button
          type="button"
          disabled={!candidateName.trim() || !roleId || !hasResume || !micStream || loading}
          onClick={() => void startInterview()}
          className="w-full rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)] transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Preparing…" : "Start interview"}
        </button>
      </div>
    </div>
  );
}
