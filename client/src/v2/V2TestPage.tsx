import { useCallback, useEffect, useRef, useState } from "react";
import LanguagePicker from "./components/LanguagePicker";
import PreflightCheck from "./components/PreflightCheck";
import LiveInterview from "./components/LiveInterview";
import ScorecardView from "./components/ScorecardView";
import { useLiveKitInterview } from "./hooks/useLiveKitInterview";
import {
  clearRejoin,
  noteRefreshDrop,
  readRejoin,
  rejoinLeftMs,
  requestRejoin,
  writeRejoin,
  type ElevenlabsRejoin,
} from "./rejoin";
import type { V2Scorecard, V2StartResponse, V2TranscriptResponse } from "./types";
import { COMPANY_NAME } from "../config/brand";
import type { IntegrityReport } from "../lib/integrity";
import { saveIntegrityReport } from "../lib/saveIntegrity";

function formatLeft(ms: number) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

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
    if (turn.role === "user" && turn.move) lines.push(`Move: ${turn.move}`);
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
  const [resumeBusy, setResumeBusy] = useState(false);
  const [resumeNote, setResumeNote] = useState(
    "Prefilled sample nurse resume — edit if you want, or upload a PDF, Word file, text file, or photo.",
  );
  const resumeInputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>("setup");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<V2StartResponse | null>(null);
  const [scorecard, setScorecard] = useState<V2Scorecard | null>(null);
  const [transcript, setTranscript] = useState<V2TranscriptResponse | null>(null);
  const [transcriptBusy, setTranscriptBusy] = useState(false);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [rejoin, setRejoin] = useState<ElevenlabsRejoin | null>(null);
  const [clock, setClock] = useState(() => Date.now());
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

  useEffect(() => {
    if (!eleven) return;
    const now = Date.now();
    setClock(now);
    setRejoin(noteRefreshDrop(now));
  }, [eleven]);

  useEffect(() => {
    if (!eleven || rejoin?.droppedAt == null) return;
    const id = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [eleven, rejoin?.droppedAt]);

  const onResumeFile = useCallback(async (file: File | undefined) => {
    if (!file) return;
    if (resumeInputRef.current) resumeInputRef.current.value = "";
    if (file.size > 8 * 1024 * 1024) {
      setError("Resume must be 8 MB or smaller");
      return;
    }
    setResumeBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("resume", file);
      const res = await fetch("/api/resume/parse", { method: "POST", body: form });
      const data = (await res.json().catch(() => ({}))) as { text?: string; error?: string };
      if (!res.ok || !data.text?.trim()) {
        throw new Error(data.error || "Could not read that resume");
      }
      setResumeText(data.text);
      setResumeNote("Text from your file. Fix anything that looks wrong before you join.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read that resume");
    } finally {
      setResumeBusy(false);
    }
  }, []);

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
      if (eleven && started.livekit) {
        const record: ElevenlabsRejoin = {
          interviewId: started.id,
          candidateName: started.candidateName,
          roleTitle: started.roleTitle,
          language: started.language,
          interviewerName: started.interviewerName,
          interviewerTitle: started.interviewerTitle,
          livekitUrl: started.livekit.url,
          token: started.livekit.token,
          droppedAt: null,
        };
        writeRejoin(record);
        setRejoin(record);
      }
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
    eleven,
  ]);

  const endAndScore = useCallback(
    async (integrity?: IntegrityReport) => {
      if (!session) return;
      if (eleven) {
        clearRejoin();
        setRejoin(null);
      }
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
    [session, eleven],
  );

  const onDropped = useCallback(() => {
    if (!eleven || !session) return;
    setRejoin((prev) => {
      const base = prev?.interviewId === session.id ? prev : readRejoin();
      if (!base || base.interviewId !== session.id || base.droppedAt != null) return base;
      const next = { ...base, droppedAt: Date.now() };
      writeRejoin(next);
      return next;
    });
  }, [eleven, session]);

  const onRejoined = useCallback((livekit: { url: string; token: string }) => {
    setRejoin((prev) => {
      if (!prev) return prev;
      const next = { ...prev, droppedAt: null, livekitUrl: livekit.url, token: livekit.token };
      writeRejoin(next);
      return next;
    });
    setSession((prev) =>
      prev?.livekit
        ? { ...prev, livekit: { ...prev.livekit, url: livekit.url, token: livekit.token } }
        : prev,
    );
  }, []);

  const abandonRejoin = useCallback(() => {
    clearRejoin();
    setRejoin(null);
    setError(null);
    setSession(null);
    setScorecard(null);
    setTranscript(null);
    setPhase("setup");
    if (candidateJoin) {
      setMicReady(false);
      setRecordingConsent(false);
    }
  }, [candidateJoin]);

  const resumeStored = useCallback(async () => {
    const current = readRejoin();
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      const livekit = await requestRejoin(current.interviewId);
      const next = { ...current, droppedAt: null, livekitUrl: livekit.url, token: livekit.token };
      writeRejoin(next);
      setRejoin(next);
      setSession({
        id: current.interviewId,
        pipeline: "v2",
        candidateName: current.candidateName,
        roleTitle: current.roleTitle,
        language: current.language as V2StartResponse["language"],
        questions: [],
        interviewerName: current.interviewerName,
        interviewerTitle: current.interviewerTitle,
        targetMinutes: 0,
        roomName: `interview-v2-${current.interviewId}`,
        livekit: { url: livekit.url, token: livekit.token, agentName: "" },
        livekitConfigured: true,
        providerMode: "",
        ttsProvider: "elevenlabs",
        planStepCount: 0,
      });
      setPhase("live");
    } catch (err) {
      const closed = err instanceof Error && err.message === "rejoin_window_closed";
      if (closed) {
        const expired = { ...current, droppedAt: Date.now() - 121_000 };
        writeRejoin(expired);
        setRejoin(expired);
      }
      setError(
        closed
          ? "This interview can no longer be rejoined. Start a new interview."
          : err instanceof Error
            ? err.message
            : "Could not rejoin",
      );
    } finally {
      setBusy(false);
    }
  }, []);

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
        allowRejoin={eleven}
        rejoinLeftMs={rejoinLeftMs(rejoin, clock)}
        onDropped={onDropped}
        onRejoined={onRejoined}
        onAbandon={abandonRejoin}
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

        {transcript?.turns.some((t) => t.role === "user" && t.move) && (
          <section className="rounded-xl border border-stone-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-stone-900">What happened next</h2>
            <p className="mt-1 text-xs text-stone-500">
              Each candidate line is shown with the move that followed it.
            </p>
            <ul className="mt-3 space-y-3">
              {transcript.turns
                .filter((t) => t.role === "user" && t.move)
                .map((t, i) => (
                  <li key={`${t.timestamp}-${i}`} className="border-b border-stone-100 pb-3 last:border-0">
                    <p className="text-sm text-stone-800">{t.text}</p>
                    <p className="mt-1 font-mono text-xs text-stone-500">Move: {t.move}</p>
                  </li>
                ))}
            </ul>
          </section>
        )}

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
    const left = eleven ? rejoinLeftMs(rejoin, clock) : null;
    const rejoinPending = Boolean(eleven && rejoin?.droppedAt != null);
    const rejoinOpen = rejoinPending && (left ?? 0) > 0;

    if (rejoinPending && rejoin) {
      return (
        <div className="mx-auto max-w-lg space-y-5 px-4 py-10">
          <div>
            <p className="text-xs uppercase tracking-wide text-stone-500">{COMPANY_NAME}</p>
            <h1 className="text-2xl font-semibold text-stone-900">
              {rejoinOpen ? "Rejoin your interview" : "Interview ended"}
            </h1>
            <p className="mt-1 text-sm text-stone-600">
              {rejoinOpen
                ? "A refresh or a dropped link stays on the same interview for 2 minutes."
                : "The 2 minute window has closed. This interview ended incomplete and was not scored. Start a new one when you are ready."}
            </p>
          </div>
          <p className="text-sm text-stone-700">
            <span className="font-medium">Interview id </span>
            <span className="select-all font-mono text-xs">{rejoin.interviewId}</span>
          </p>
          {rejoin.candidateName ? (
            <p className="text-sm text-stone-600">
              {rejoin.candidateName}
              {rejoin.roleTitle ? ` · ${rejoin.roleTitle}` : ""}
            </p>
          ) : null}
          {error && <p className="text-sm text-red-600">{error}</p>}
          {rejoinOpen ? (
            <>
              <p className="text-sm font-medium text-stone-800">{formatLeft(left ?? 0)} left</p>
              <button
                type="button"
                disabled={busy}
                onClick={() => void resumeStored()}
                className="w-full rounded-lg bg-stone-900 px-4 py-3 text-sm font-medium text-white disabled:opacity-50"
              >
                {busy ? "Rejoining…" : "Rejoin"}
              </button>
              <button
                type="button"
                onClick={abandonRejoin}
                className="w-full rounded-lg border border-stone-300 px-4 py-2.5 text-sm text-stone-700"
              >
                Start a new interview
              </button>
              <p className="text-xs text-stone-500">
                Starting a new interview abandons {rejoin.interviewId}. The answers already given stay on that id and
                are not copied over.
              </p>
            </>
          ) : (
            <button
              type="button"
              onClick={abandonRejoin}
              className="w-full rounded-lg bg-stone-900 px-4 py-3 text-sm font-medium text-white"
            >
              Start a new interview
            </button>
          )}
        </div>
      );
    }

    const canJoin =
      Boolean(roleId) && name.trim().length > 0 && recordingConsent && micReady && !busy && !resumeBusy;

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
          {eleven && (
            <input
              ref={resumeInputRef}
              type="file"
              accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
              disabled={resumeBusy}
              className="text-sm file:mr-3 file:rounded-md file:border-0 file:bg-stone-200 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-stone-800"
              onChange={(e) => void onResumeFile(e.target.files?.[0])}
            />
          )}
          <textarea
            className="min-h-40 rounded-lg border border-stone-300 px-3 py-2 font-mono text-xs leading-relaxed"
            value={resumeText}
            onChange={(e) => setResumeText(e.target.value)}
            spellCheck={false}
            readOnly={resumeBusy}
          />
          <span className="text-xs text-stone-500">
            {eleven
              ? resumeBusy
                ? "Reading resume…"
                : resumeNote
              : "Prefilled sample nurse resume — edit if you want."}
          </span>
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
          {resumeBusy ? "Reading resume…" : busy ? "Joining…" : "Join interview"}
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
