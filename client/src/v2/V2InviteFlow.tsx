import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useTAStore } from "../context/TAStore";
import LanguagePicker from "./components/LanguagePicker";
import PreflightCheck from "./components/PreflightCheck";
import LiveInterview from "./components/LiveInterview";
import { useLiveKitInterview } from "./hooks/useLiveKitInterview";
import type { V2StartResponse } from "./types";
import type { IntegrityReport } from "../lib/integrity";
import { saveIntegrityReport } from "../lib/saveIntegrity";

/**
 * Invite-linked v2 flow. Uses the same TA invite token as v1, but runs the Indic pipeline.
 * Path: /v2/i/:token
 */
export default function V2InviteFlow() {
  const { token } = useParams();
  const navigate = useNavigate();
  const { getCandidateByToken, completeLiveInterview, getRole } = useTAStore();
  const candidate = token ? getCandidateByToken(token) : null;
  const role = candidate ? getRole(candidate.roleId) : undefined;
  const roleTitle = role?.title || "Role";

  const [language, setLanguage] = useState("hi-IN");
  const [resumeText, setResumeText] = useState(candidate?.resumeText || "");
  const [consent, setConsent] = useState(false);
  const [session, setSession] = useState<V2StartResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lk = useLiveKitInterview();

  useEffect(() => {
    if (candidate?.resumeText) setResumeText(candidate.resumeText);
  }, [candidate]);

  if (!candidate) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <h1 className="text-xl font-semibold">Invite not found</h1>
        <p className="mt-2 text-sm text-stone-600">Check your link or ask TA to resend.</p>
        <Link className="mt-4 inline-block text-sm underline" to="/v2/test">
          Open v2 test page
        </Link>
      </div>
    );
  }

  if (session) {
    return (
      <LiveInterview
        session={{
          id: session.id,
          candidateName: session.candidateName,
          roleTitle: session.roleTitle,
          interviewerName: session.interviewerName,
          interviewerTitle: session.interviewerTitle,
          language: session.language,
          livekit: session.livekit,
        }}
        lk={lk}
        onEnded={async (integrity: IntegrityReport) => {
          try {
            await saveIntegrityReport(session.id, integrity).catch(() => undefined);
            const res = await fetch(`/api/v2/interview/${session.id}/summary`, { method: "POST" });
            if (res.ok) {
              const scorecard = await res.json();
              completeLiveInterview({
                candidateId: candidate.id,
                interviewId: session.id,
                scorecard,
              });
            }
          } catch {
            /* ignore */
          }
          navigate(`/v2/i/${token}/thanks`);
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 px-4 py-10">
      <h1 className="text-2xl font-semibold">Interview setup (v2)</h1>
      <p className="mt-2 text-sm text-stone-600">
        Hi {candidate.name} — role: {roleTitle}. This link uses the Indic voice pipeline.
      </p>

      <LanguagePicker value={language} onChange={setLanguage} />

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Resume text (optional)</span>
        <textarea
          className="min-h-28 rounded-lg border border-stone-300 px-3 py-2"
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
        />
      </label>

      <PreflightCheck onDone={() => undefined} />

      <label className="flex items-start gap-2 text-sm">
        <input type="checkbox" className="mt-1" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>I consent to processing this interview for hiring evaluation.</span>
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="button"
        disabled={busy || !consent}
        className="w-full rounded-lg bg-stone-900 px-4 py-3 text-sm text-white disabled:opacity-50"
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            const startRes = await fetch("/api/v2/interview/start", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                roleId: candidate.roleId,
                language,
                recordingConsent: consent,
                candidateId: candidate.id,
                candidateContext: {
                  name: candidate.name,
                  roleAppliedFor: roleTitle,
                  resumeText,
                  email: candidate.email,
                },
              }),
            });
            if (!startRes.ok) throw new Error("Start failed");
            setSession((await startRes.json()) as V2StartResponse);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Failed");
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "Starting…" : "Start interview"}
      </button>
    </div>
  );
}
