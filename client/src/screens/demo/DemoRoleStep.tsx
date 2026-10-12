import { useEffect, useMemo, useState } from "react";
import { INTERVIEWER_NAME } from "../../config/brand";
import { OrbitingLoader } from "../../components/OrbitingLoader";
import ThemeToggle from "../../components/ThemeToggle";
import { MicTestCard } from "../../components/WaveformVisualizer";
import { buildClientCandidateContext } from "../../lib/candidate";
import type { InterviewSession } from "../../types/session";
import { SENIORITY_LABEL, SENIORITY_ORDER, type DemoIndustry, type DemoProspect, type DemoRole } from "./types";

type ResumeMode = "sample" | "upload";
type PrepStep = "idle" | "parsing" | "generating" | "starting";

type Props = {
  industry: DemoIndustry;
  prospect: DemoProspect;
  interviewerName?: string;
  onBack: () => void;
  onStarted: (session: InterviewSession, role: DemoRole) => void;
};

export default function DemoRoleStep({
  industry,
  prospect,
  interviewerName = INTERVIEWER_NAME,
  onBack,
  onStarted,
}: Props) {
  const roles = useMemo(
    () =>
      [...industry.roles].sort(
        (a, b) => SENIORITY_ORDER.indexOf(a.seniority) - SENIORITY_ORDER.indexOf(b.seniority),
      ),
    [industry.roles],
  );

  const [roleId, setRoleId] = useState(roles[0]?.id ?? "");
  const [resumeMode, setResumeMode] = useState<ResumeMode>("sample");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [micStream, setMicStream] = useState<MediaStream | null>(null);
  const [micError, setMicError] = useState<string | null>(null);
  const [prepStep, setPrepStep] = useState<PrepStep>("idle");
  const [error, setError] = useState<string | null>(null);

  const selectedRole = useMemo(
    () => roles.find((r) => r.id === roleId) ?? roles[0] ?? null,
    [roles, roleId],
  );

  const hasResume = resumeMode === "sample" ? Boolean(selectedRole) : Boolean(resumeFile);
  const loading = prepStep !== "idle";

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

  async function parseUploadedResume(): Promise<string> {
    if (!resumeFile) throw new Error("Resume PDF is required");
    const form = new FormData();
    form.append("resume", resumeFile);
    const res = await fetch("/api/resume/parse", { method: "POST", body: form });
    if (!res.ok) throw new Error(await res.text());
    const data = (await res.json()) as { text: string };
    return data.text;
  }

  async function startInterview() {
    if (!selectedRole || !hasResume) return;
    setError(null);

    try {
      micStream?.getTracks().forEach((t) => t.stop());
      setMicStream(null);

      let resumeText: string;
      let yearsOfExperience = selectedRole.sampleResume.yearsOfExperience;
      let currentCompany = selectedRole.sampleResume.currentCompany;

      if (resumeMode === "upload") {
        setPrepStep("parsing");
        resumeText = await parseUploadedResume();
        yearsOfExperience = "";
        currentCompany = "";
      } else {
        resumeText = selectedRole.sampleResume.text;
      }

      const candidateContext = buildClientCandidateContext({
        name: prospect.name,
        roleAppliedFor: selectedRole.title,
        resumeText,
        email: prospect.email,
        yearsOfExperience: yearsOfExperience || undefined,
        currentCompany: currentCompany || undefined,
      });

      setPrepStep("generating");
      const genRes = await fetch("/api/interview/generate-questions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          candidateContext,
          roleCriteria: selectedRole.criteria,
          seniority: selectedRole.seniority,
        }),
      });
      if (!genRes.ok) throw new Error(await genRes.text());
      const genData = (await genRes.json()) as { resume_questions: string[] };

      setPrepStep("starting");
      const startRes = await fetch("/api/interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roleId: selectedRole.id,
          candidateContext,
          resumeQuestions: genData.resume_questions,
          demo: true,
        }),
      });
      if (!startRes.ok) throw new Error(await startRes.text());
      const data = (await startRes.json()) as InterviewSession;
      onStarted(data, selectedRole);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start interview");
      setPrepStep("idle");
    }
  }

  return (
    <div className="relative mx-auto min-h-screen max-w-5xl px-6 py-14">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>

      {loading && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-[var(--color-ink)]/90">
          <div className="mx-6 text-center">
            <OrbitingLoader size={112} />
            <p className="mt-8 text-base text-[var(--color-muted)]">
              {prepStep === "parsing"
                ? "Reading the resume…"
                : prepStep === "generating"
                  ? `${interviewerName} is preparing questions from the resume…`
                  : "Connecting you to the live interview…"}
            </p>
          </div>
        </div>
      )}

      <p className="text-xs font-semibold tracking-[0.18em] text-[var(--color-accent)] uppercase">
        Step 2 of 2 · {industry.label}
      </p>
      <h1 className="mt-2 font-[family-name:var(--font-display)] text-3xl text-[var(--color-fg)] md:text-4xl">
        Choose the role you want {interviewerName} to interview for
      </h1>
      <p className="mt-3 max-w-2xl text-[var(--color-muted)]">
        You will answer as the candidate. Pick a seniority, read the brief, then use a sample
        resume or upload your own. {interviewerName} tailors questions to it.
      </p>

      <div className="mt-8 grid gap-3 md:grid-cols-3">
        {roles.map((role) => {
          const selected = role.id === selectedRole?.id;
          return (
            <button
              key={role.id}
              type="button"
              disabled={loading}
              onClick={() => {
                setRoleId(role.id);
                setResumeFile(null);
                setResumeMode("sample");
              }}
              className={`rounded-2xl border p-4 text-left transition ${
                selected
                  ? "border-[var(--color-accent)] bg-[var(--color-accent-dim)]"
                  : "border-[var(--color-line)] bg-[var(--color-panel)]/70 hover:border-[var(--color-muted)]"
              }`}
            >
              <p className="text-[10px] font-semibold tracking-[0.16em] text-[var(--color-accent)] uppercase">
                {SENIORITY_LABEL[role.seniority]}
              </p>
              <p className="mt-2 text-sm font-medium text-[var(--color-fg)]">{role.title}</p>
              <p className="mt-1 line-clamp-3 text-xs leading-relaxed text-[var(--color-muted)]">
                {role.summary}
              </p>
            </button>
          );
        })}
      </div>

      {selectedRole && (
        <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <section className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/70 p-5">
            <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-muted)] uppercase">
              Job description
            </p>
            <h2 className="mt-2 text-xl font-medium text-[var(--color-fg)]">{selectedRole.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-[var(--color-muted)]">
              {selectedRole.summary}
            </p>
            <h3 className="mt-5 text-xs font-semibold tracking-wide text-[var(--color-fg)] uppercase">
              What you&apos;d own
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm text-[var(--color-muted)]">
              {selectedRole.responsibilities.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
            <h3 className="mt-5 text-xs font-semibold tracking-wide text-[var(--color-fg)] uppercase">
              What we look for
            </h3>
            <ul className="mt-2 space-y-1.5 text-sm text-[var(--color-muted)]">
              {selectedRole.requirements.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
          </section>

          <div className="space-y-5">
            <section className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-panel)]/70 p-5">
              <p className="text-xs font-semibold tracking-[0.16em] text-[var(--color-muted)] uppercase">
                Resume
              </p>
              <p className="mt-2 text-sm leading-relaxed text-[var(--color-muted)]">
                {interviewerName} reads this before you go live and writes questions against this
                person&apos;s experience, not a generic script.
              </p>

              <div className="mt-4 flex rounded-lg border border-[var(--color-line)] p-0.5 text-xs">
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => setResumeMode("sample")}
                  className={`flex-1 rounded-md px-2.5 py-1.5 ${
                    resumeMode === "sample"
                      ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
                      : "text-[var(--color-muted)]"
                  }`}
                >
                  Use sample resume
                </button>
                <button
                  type="button"
                  disabled={loading}
                  onClick={() => setResumeMode("upload")}
                  className={`flex-1 rounded-md px-2.5 py-1.5 ${
                    resumeMode === "upload"
                      ? "bg-[var(--color-accent)] text-[var(--color-on-accent)]"
                      : "text-[var(--color-muted)]"
                  }`}
                >
                  Upload PDF
                </button>
              </div>

              {resumeMode === "sample" ? (
                <div className="mt-4 rounded-xl border border-[var(--color-line)] bg-[var(--color-input)] p-3">
                  <p className="text-sm font-medium text-[var(--color-fg)]">
                    {selectedRole.sampleResume.label}
                  </p>
                  <p className="mt-2 max-h-36 overflow-y-auto whitespace-pre-wrap text-xs leading-relaxed text-[var(--color-muted)]">
                    {selectedRole.sampleResume.text}
                  </p>
                </div>
              ) : (
                <label className="mt-4 block">
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
                </label>
              )}
            </section>

            <MicTestCard stream={micStream} error={micError} />
          </div>
        </div>
      )}

      {error && <p className="mt-4 text-sm text-[var(--color-danger)]">{error}</p>}

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onBack}
          disabled={loading}
          className="rounded-xl border border-[var(--color-line)] px-4 py-3.5 text-sm text-[var(--color-muted)] hover:text-[var(--color-fg)]"
        >
          Back
        </button>
        <button
          type="button"
          disabled={!selectedRole || !hasResume || !micStream || loading}
          onClick={() => void startInterview()}
          className="flex-1 rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)] transition enabled:hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {loading ? "Preparing…" : `Start interview with ${interviewerName}`}
        </button>
      </div>
    </div>
  );
}
