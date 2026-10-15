import { useCallback, useEffect, useState } from "react";
import LanguagePicker from "./components/LanguagePicker";
import PreflightCheck from "./components/PreflightCheck";
import LiveInterview from "./components/LiveInterview";
import ScorecardView from "./components/ScorecardView";
import { useLiveKitInterview } from "./hooks/useLiveKitInterview";
import type { V2Scorecard, V2StartResponse } from "./types";
import { COMPANY_NAME } from "../config/brand";
import type { IntegrityReport } from "../lib/integrity";
import { saveIntegrityReport } from "../lib/saveIntegrity";

type Role = { id: string; title: string; criteria: string[] };

type Phase = "setup" | "live" | "scorecard" | "error";

type Props = {
  avatar?: boolean;
  /** When set, forces that TTS for this route only (e.g. elevenlabs). */
  ttsProvider?: string;
  /** Full-duplex voice path (e.g. gpt_live) — replaces cascade STT/LLM/TTS. */
  voiceProvider?: string;
};

export default function V2TestPage({ avatar = false, ttsProvider, voiceProvider }: Props) {
  const [roles, setRoles] = useState<Role[]>([]);
  const [roleId, setRoleId] = useState("");
  const [language, setLanguage] = useState("hi-IN");
  const [name, setName] = useState("Test Candidate");
  const [resumeText, setResumeText] = useState(
    "Registered Nurse with 3 years experience at Apollo Hospital ICU. Skilled in patient monitoring, medication administration, and emergency response.",
  );
  const [recordingConsent, setRecordingConsent] = useState(true);
  const [preflightDone, setPreflightDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("setup");
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<V2StartResponse | null>(null);
  const [scorecard, setScorecard] = useState<V2Scorecard | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const lk = useLiveKitInterview();
  const eleven = ttsProvider === "elevenlabs";
  const gptLive = voiceProvider === "gpt_live";

  useEffect(() => {
    void fetch("/api/roles")
      .then((r) => r.json())
      .then((data: Role[] | { roles: Role[] }) => {
        const list = Array.isArray(data) ? data : data.roles;
        setRoles(list || []);
        if (list?.[0]) setRoleId(list[0].id);
      })
      .catch(() => undefined);
    void fetch("/api/v2/interview/health")
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => undefined);
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
      setSession(started);
      setPhase("live");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Start failed");
      setPhase("error");
    } finally {
      setBusy(false);
    }
  }, [roles, roleId, name, resumeText, language, recordingConsent, avatar, ttsProvider, voiceProvider]);

  const endAndScore = useCallback(async (integrity?: IntegrityReport) => {
    if (!session) return;
    setBusy(true);
    try {
      if (integrity) {
        await saveIntegrityReport(session.id, integrity).catch(() => undefined);
      }
      // Wait a moment for agent transcript flush
      await new Promise((r) => setTimeout(r, 1500));
      const res = await fetch(`/api/v2/interview/${session.id}/summary`, { method: "POST" });
      if (res.ok) {
        setScorecard((await res.json()) as V2Scorecard);
      }
      setPhase("scorecard");
    } catch {
      setPhase("scorecard");
    } finally {
      setBusy(false);
    }
  }, [session]);

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
    return (
      <div className="mx-auto max-w-lg px-4 py-10">
        <h1 className="text-2xl font-semibold">Interview complete</h1>
        <p className="mt-1 text-sm text-stone-600">Session {session?.id}</p>
        {scorecard ? (
          <ScorecardView scorecard={scorecard} />
        ) : (
          <p className="mt-4 text-sm text-stone-600">
            No scorecard yet (need transcript turns from the agent). Session was saved.
          </p>
        )}
        <button
          type="button"
          className="mt-6 rounded-lg bg-stone-900 px-4 py-2 text-sm text-white"
          onClick={() => {
            setPhase("setup");
            setSession(null);
            setScorecard(null);
          }}
        >
          Run another
        </button>
      </div>
    );
  }

  const title = avatar
    ? "Avatar interviewer test"
    : gptLive
      ? "GPT-Live voice test"
      : eleven
        ? "ElevenLabs voice test"
        : "Indic voice interview test";
  const blurb = avatar
    ? "Same v2 interview agent, with a Tavus face on this route only. /v2/test stays voice-only."
    : gptLive
      ? "Same interview Flow/Director as /v2/test, but speech uses OpenAI GPT-Live full-duplex (model handles pauses, fillers, backchannels). Requires GPT-Live alpha on the API key."
      : eleven
        ? "Same interview flow as /v2/test, but speech uses ElevenLabs multilingual TTS so you can A/B how human it sounds vs Chirp."
        : "Parallel flow for South Indian languages, Hinglish/Tanglish, and ward-noise handling. Existing `/i/*` routes are unchanged.";
  const startLabel = avatar
    ? "Start avatar interview"
    : gptLive
      ? "Start GPT-Live interview"
      : eleven
        ? "Start ElevenLabs interview"
        : "Start v2 interview";

  return (
    <div className="mx-auto max-w-lg space-y-5 px-4 py-10">
      <div>
        <p className="text-xs uppercase tracking-wide text-stone-500">
          {COMPANY_NAME} · pipeline v2
          {avatar ? " · Tavus avatar" : ""}
          {eleven ? " · ElevenLabs TTS" : ""}
          {gptLive ? " · GPT-Live" : ""}
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

      <PreflightCheck onDone={() => setPreflightDone(true)} />

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
