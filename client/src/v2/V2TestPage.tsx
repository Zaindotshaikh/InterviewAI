import { useCallback, useEffect, useState } from "react";
import LanguagePicker from "./components/LanguagePicker";
import PreflightCheck from "./components/PreflightCheck";
import LiveInterview from "./components/LiveInterview";
import ScorecardView from "./components/ScorecardView";
import { useLiveKitInterview } from "./hooks/useLiveKitInterview";
import type { V2Scorecard, V2StartResponse, V2TranscriptResponse } from "./types";
import { COMPANY_NAME } from "../config/brand";
import type { IntegrityReport } from "../lib/integrity";
import { saveIntegrityReport } from "../lib/saveIntegrity";

function downloadTranscriptTxt(data: V2TranscriptResponse) {
  const lines = [
    "Interview transcript",
    `Candidate: ${data.candidateName || "—"}`,
    `Role: ${data.roleTitle || "—"}`,
    data.language ? `Language: ${data.language}` : "",
    `Session: ${data.id}`,
    "",
    "—".repeat(40),
    "",
  ].filter(Boolean);

  for (const turn of data.turns) {
    const who = turn.role === "assistant" ? "Interviewer" : "Candidate";
    lines.push(`${who}:`);
    lines.push(turn.text.trim() || "(empty)");
    lines.push("");
  }

  const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  const safeName = (data.candidateName || "candidate").replace(/[^\w\-]+/g, "_").slice(0, 40);
  a.href = url;
  a.download = `interview-transcript-${safeName}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

type Role = { id: string; title: string; criteria: string[] };

type Phase = "setup" | "live" | "scorecard" | "error";

type Props = {
  avatar?: boolean;
  /** When set, forces that TTS for this route only (e.g. elevenlabs). */
  ttsProvider?: string;
  /** Full-duplex voice path (e.g. gpt_live) — replaces cascade STT/LLM/TTS. */
  voiceProvider?: string;
};

/** Realistic Staff Nurse resume used on EL / GPT-Live join screens (editable). */
const NURSE_RESUME_PREFILL = `Registered Nurse (Staff Nurse) | 28 years
Mobile: 98765 43210 | Email: nurse.candidate@email.com
City: Pune, Maharashtra | Willing to relocate: Mumbai, Hyderabad, Bangalore

PROFESSIONAL SUMMARY
B.Sc. Nursing graduate with 3 years 8 months clinical experience in multi-specialty hospital settings. Strong background in ICU / Critical Care and General Ward nursing. Comfortable with patient assessment, medication administration (oral, IV, IM), vital monitoring, wound care, catheterization, Ryle’s tube feeding, and essential hygiene care including diaper change for bedridden patients. Able to work night shifts and handle emergency situations calmly.

EDUCATION
• B.Sc. Nursing — Bharati Vidyapeeth College of Nursing, Pune (2018 – 2022)
• Registered with Maharashtra Nursing Council (MNC) — Registration No. MH-RN-2022-45821
• Basic Life Support (BLS) certified — American Heart Association (valid till 2027)
• ACLS awareness workshop completed (2024)

WORK EXPERIENCE

1) Staff Nurse — Medical ICU
   Apollo Hospitals, Pune | July 2023 – Present (about 2 years 3 months)
   • Care for critically ill patients on ventilators, NIV, and multiparameter monitors
   • IV cannulation, infusion pump setup, blood transfusion monitoring, ABG sampling assist
   • Pre- and post-operative care; shift handover using SBAR
   • Administer medications as per doctor orders; maintain accurate nursing notes
   • Assist in Code Blue / CPR; check defibrillator and emergency trolley readiness
   • Infection control: hand hygiene, PPE, biomedical waste segregation
   • Support families with clear updates; maintain patient dignity during hygiene care

2) Staff Nurse — General Medicine Ward
   Ruby Hall Clinic, Pune | Nov 2022 – June 2023 (8 months)
   • Bedside nursing for 8–12 patients per shift (admission, discharge, daily care)
   • Vital signs, intake-output charting, glucose monitoring, dressing and wound care
   • Assisted with diaper care, sponge bath, oral care, and pressure-ulcer prevention
   • Coordinated with doctors, physiotherapists, and lab for investigations
   • Night duty rotation; mentored new joiners on ward protocols

SKILLS
Critical care monitoring • IV therapy & medication safety • ECG basic interpretation
Wound / pressure-sore care • Catheter & Ryle’s tube care • Diaper & personal hygiene care
Emergency response / BLS • Infection control • Patient counselling • Documentation (EMR)
Languages: Hindi, Marathi, English (spoken & written)

ADDITIONAL
• Notice period: 30 days
• Preferred shifts: Rotational including night duty
• Immediate strengths: calm under pressure, teamwork, punctual, willing to learn ICU protocols`;

export default function V2TestPage({ avatar = false, ttsProvider, voiceProvider }: Props) {
  const eleven = ttsProvider === "elevenlabs";
  const gptLive = voiceProvider === "gpt_live";
  const candidateJoin = eleven || gptLive;

  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState("");
  const [language, setLanguage] = useState("hi-IN");
  const [name, setName] = useState(candidateJoin ? "" : "Test Candidate");
  const [resumeText, setResumeText] = useState(
    candidateJoin
      ? NURSE_RESUME_PREFILL
      : "Registered Nurse with 3 years experience at Apollo Hospital ICU. Skilled in patient monitoring, medication administration, and emergency response.",
  );
  const [recordingConsent, setRecordingConsent] = useState(!candidateJoin);
  const [preflightDone, setPreflightDone] = useState(false);
  const [micReady, setMicReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("setup");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<V2StartResponse | null>(null);
  const [scorecard, setScorecard] = useState<V2Scorecard | null>(null);
  const [transcript, setTranscript] = useState<V2TranscriptResponse | null>(null);
  const [transcriptBusy, setTranscriptBusy] = useState(false);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const lk = useLiveKitInterview();

  const roleTitle = roles.find((r) => r.id === roleId)?.title || "Staff Nurse";

  useEffect(() => {
    void fetch("/api/roles")
      .then((r) => r.json())
      .then((data: Role[] | { roles: Role[] }) => {
        const list = Array.isArray(data) ? data : data.roles;
        setRoles(list || []);
        if (list?.[0]) setRoleId(list[0].id);
      })
      .catch(() => undefined);
    if (!candidateJoin) {
      void fetch("/api/v2/interview/health")
        .then((r) => r.json())
        .then(setHealth)
        .catch(() => undefined);
    }
  }, [candidateJoin]);

  const start = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const role = roles.find((r) => r.id === roleId);
      // No pre-written questions: the interviewer adapts to the candidate from the role blueprint.
      const startRes = await fetch("/api/v2/interview/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roleId,
          language,
          recordingConsent,
          avatar: avatar || undefined,
          ttsProvider: ttsProvider || undefined,
          voiceProvider: voiceProvider || undefined,
          candidateContext: {
            name,
            roleAppliedFor: role?.title || "Staff Nurse",
            resumeText,
          },
        }),
      });
      if (!startRes.ok) {
        const err = await startRes.json().catch(() => ({}));
        throw new Error(err.error || "Failed to start interview");
      }
      const started = (await startRes.json()) as V2StartResponse;
      setSession(started);
      setPhase("live");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start failed");
      setPhase("error");
    } finally {
      setBusy(false);
    }
  }, [
    roles,
    roleId,
    name,
    resumeText,
    language,
    recordingConsent,
    avatar,
    ttsProvider,
    voiceProvider,
    candidateJoin,
  ]);

  const endAndScore = useCallback(
    async (integrity?: IntegrityReport) => {
      if (!session) return;
      setBusy(true);
      try {
        if (integrity) {
          await saveIntegrityReport(session.id, integrity).catch(() => undefined);
        }
        // Wait a moment for agent transcript flush
        await new Promise((r) => setTimeout(r, 1500));
        const [summaryRes, transcriptRes] = await Promise.all([
          fetch(`/api/v2/interview/${session.id}/summary`, { method: "POST" }),
          fetch(`/api/v2/interview/${session.id}/transcript`),
        ]);
        if (summaryRes.ok) {
          setScorecard((await summaryRes.json()) as V2Scorecard);
        }
        if (transcriptRes.ok) {
          setTranscript((await transcriptRes.json()) as V2TranscriptResponse);
        }
        setPhase("scorecard");
      } catch {
        setPhase("scorecard");
      } finally {
        setBusy(false);
      }
    },
    [session],
  );

  const onDownloadTranscript = useCallback(async () => {
    if (!session) return;
    setTranscriptBusy(true);
    try {
      let data = transcript;
      if (!data?.turns?.length) {
        const res = await fetch(`/api/v2/interview/${session.id}/transcript`);
        if (!res.ok) throw new Error("Could not load transcript");
        data = (await res.json()) as V2TranscriptResponse;
        setTranscript(data);
      }
      if (!data.turns.length) {
        setError("No transcript turns were saved for this interview yet.");
        return;
      }
      downloadTranscriptTxt(data);
    } catch {
      setError("Could not download transcript. Please try again.");
    } finally {
      setTranscriptBusy(false);
    }
  }, [session, transcript]);

  if (phase === "live" && session) {
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
        showAvatar={avatar}
        onEnded={(integrity) => void endAndScore(integrity)}
      />
    );
  }

  if (phase === "scorecard") {
    const turnCount = transcript?.turns?.length ?? 0;
    return (
      <div className="mx-auto max-w-lg space-y-6 px-4 py-10">
        <div>
          <p className="text-xs uppercase tracking-wide text-stone-500">{COMPANY_NAME}</p>
          <h1 className="text-2xl font-semibold text-stone-900">Interview complete</h1>
          <p className="mt-1 text-sm text-stone-600">
            {session?.candidateName ? (
              <>
                <span className="font-medium text-stone-800">{session.candidateName}</span>
                {session.roleTitle ? ` · ${session.roleTitle}` : ""}
              </>
            ) : (
              session?.roleTitle || "Screening finished"
            )}
          </p>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div>
          <h2 className="text-sm font-semibold text-stone-900">Results</h2>
          <div className="mt-2">
            {scorecard ? (
              <ScorecardView scorecard={scorecard} />
            ) : (
              <p className="rounded-xl border border-stone-200 bg-stone-50 p-4 text-sm text-stone-600">
                Results are not ready yet. The session was saved
                {turnCount > 0 ? ` (${turnCount} transcript turns)` : ""}.
              </p>
            )}
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <button
            type="button"
            disabled={transcriptBusy || !session}
            onClick={() => void onDownloadTranscript()}
            className="flex-1 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm font-medium text-stone-900 disabled:opacity-50"
          >
            {transcriptBusy ? "Preparing…" : "Download full transcript"}
          </button>
          <button
            type="button"
            className="flex-1 rounded-lg bg-stone-900 px-4 py-2.5 text-sm font-medium text-white"
            onClick={() => {
              setPhase("setup");
              setSession(null);
              setScorecard(null);
              setTranscript(null);
              setError(null);
              if (candidateJoin) {
                setMicReady(false);
                setRecordingConsent(false);
              }
            }}
          >
            {candidateJoin ? "Done" : "Run another"}
          </button>
        </div>
      </div>
    );
  }

  if (candidateJoin) {
    const canJoin =
      Boolean(roleId) && name.trim().length > 0 && recordingConsent && micReady && !busy;

    return (
      <div className="mx-auto max-w-lg space-y-5 px-4 py-10">
        <div>
          <p className="text-xs uppercase tracking-wide text-stone-500">{COMPANY_NAME}</p>
          <h1 className="text-2xl font-semibold text-stone-900">Join your interview</h1>
          <p className="mt-1 text-sm text-stone-600">
            {roleTitle} screening — a short spoken interview. Find a quiet spot if you can, then join when
            you are ready.
          </p>
        </div>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Your name</span>
          <input
            className="rounded-lg border border-stone-300 px-3 py-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Full name"
            autoComplete="name"
          />
        </label>

        <LanguagePicker value={language} onChange={setLanguage} />

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Resume</span>
          <textarea
            className="min-h-40 rounded-lg border border-stone-300 px-3 py-2 font-mono text-xs leading-relaxed"
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            spellCheck={false}
          />
          <span className="text-xs text-stone-500">Prefilled sample nurse resume — edit if you want.</span>
        </label>

        <PreflightCheck
          simple
          onDone={(result) => {
            setMicReady(result.ok);
            setPreflightDone(result.ok);
          }}
        />

        <label className="flex items-start gap-2 text-sm">
          <input
            type="checkbox"
            className="mt-1"
            checked={recordingConsent}
            onChange={(e) => setRecordingConsent(e.target.checked)}
          />
          <span>
            I consent to this interview being processed for hiring evaluation (DPDP). Optional recording may
            be stored per company retention policy.
          </span>
        </label>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="button"
          disabled={!canJoin}
          onClick={() => void start()}
          className="w-full rounded-lg bg-stone-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Joining…" : "Join interview"}
        </button>
      </div>
    );
  }

  const title = avatar ? "Avatar interviewer test" : "Indic voice interview test";
  const blurb = avatar
    ? "Same v2 interview agent, with a Tavus face on this route only. /v2/test stays voice-only."
    : "Parallel flow for South Indian languages, Hinglish/Tanglish, and ward-noise handling. Existing `/i/*` routes are unchanged.";
  const startLabel = avatar ? "Start avatar interview" : "Start v2 interview";

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 py-10">
      <div>
        <p className="text-xs uppercase tracking-wide text-stone-500">
          {COMPANY_NAME} · pipeline v2
          {avatar ? " · Tavus avatar" : ""}
        </p>
        <h1 className="text-2xl font-semibold text-stone-900">{title}</h1>
        <p className="mt-1 text-sm text-stone-600">{blurb}</p>
      </div>

      {health && (
        <pre className="overflow-auto rounded-lg bg-stone-100 p-3 text-xs text-stone-700">
          {JSON.stringify(health, null, 2)}
        </pre>
      )}

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Role</span>
        <select
          className="rounded-lg border border-stone-300 px-3 py-2"
          value={roleId}
          onChange={(e) => setRoleId(e.target.value)}
        >
          {roles.map((r) => (
            <option key={r.id} value={r.id}>
              {r.title}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Candidate name</span>
        <input
          className="rounded-lg border border-stone-300 px-3 py-2"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <LanguagePicker value={language} onChange={setLanguage} />

      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Resume text (optional)</span>
        <textarea
          className="min-h-28 rounded-lg border border-stone-300 px-3 py-2"
          value={resumeText}
          onChange={(e) => setResumeText(e.target.value)}
        />
      </label>

      <PreflightCheck
        onDone={() => {
          setPreflightDone(true);
          setMicReady(true);
        }}
      />

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          className="mt-1"
          checked={recordingConsent}
          onChange={(e) => setRecordingConsent(e.target.checked)}
        />
        <span>
          I consent to this interview being processed for hiring evaluation (DPDP). Optional recording may be
          stored per company retention policy.
        </span>
      </label>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <button
        type="button"
        disabled={busy || !roleId || !name.trim()}
        onClick={() => void start()}
        className="w-full rounded-lg bg-stone-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "Starting…" : preflightDone ? startLabel : "Start without preflight"}
      </button>
    </div>
  );
}
