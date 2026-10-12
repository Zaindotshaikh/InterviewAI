import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectRealtimeWebRTC,
  fetchEphemeralSession,
  requestAssistantResponse,
  requestCancelResponse,
  requestInitialGreeting,
  requestRestateCurrentQuestion,
  sendSessionUpdate,
  type TranscriptionContext,
} from "../lib/realtime";
import { createRealtimeLogger } from "../lib/realtimeDebug";
import { isResumeLeak } from "../lib/resumeLeak";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "live"
  | "reconnecting"
  | "ended"
  | "error";

export type Speaker = "user" | "assistant" | null;

export type Caption = {
  id: string;
  role: "user" | "assistant";
  text: string;
  partial?: boolean;
};

type Options = {
  instructions: string;
  interviewId: string;
  candidateName: string;
  interviewerName?: string;
  demo?: boolean;
  transcriptionContext?: TranscriptionContext;
  resumeText?: string;
  autoStart?: boolean;
};

/** Apply incremental or cumulative ASR delta snapshots safely. */
function applyTranscriptDelta(current: string, incoming: string): string {
  const delta = incoming ?? "";
  if (!delta) return current;
  if (!current) return delta;
  // Some API versions send the full transcript so far as each "delta"
  if (delta.startsWith(current)) return delta;
  if (current.includes(delta) && delta.length < current.length) return current;
  return current + delta;
}

/** Resume / document dumps hallucinated into captions (prompt leakage). */
function looksLikeResumeDump(text: string, resumeText?: string): boolean {
  return isResumeLeak(text, resumeText, "user");
}

function pickBestTranscript(completed: string, partial: string): string {
  const a = completed.trim();
  const b = partial.trim();
  if (!a) return b;
  if (!b) return a;
  if (a.startsWith(b) || b.startsWith(a)) return a.length >= b.length ? a : b;
  return a.length >= b.length ? a : b;
}

function normalizeForEcho(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isLikelyEchoOfAssistant(userText: string, assistantText: string): boolean {
  const user = normalizeForEcho(userText);
  const assistant = normalizeForEcho(assistantText);
  if (!user || !assistant || user.length < 16) return false;
  if (assistant.includes(user) || user.includes(assistant)) return true;
  const userWords = new Set(user.split(" ").filter((w) => w.length > 3));
  if (userWords.size < 4) return false;
  const assistantWords = assistant.split(" ").filter((w) => w.length > 3);
  const overlap = assistantWords.filter((w) => userWords.has(w)).length;
  return overlap >= 5 && overlap / Math.max(userWords.size, 1) >= 0.7;
}

const FILLER_WORDS = new Set([
  "okay",
  "ok",
  "um",
  "uh",
  "uhm",
  "hmm",
  "hm",
  "yeah",
  "yep",
  "yup",
  "yes",
  "no",
  "nah",
  "right",
  "alright",
  "sure",
  "hello",
  "hi",
  "hey",
  "thanks",
  "thank",
  "you",
  "mmm",
  "mm",
  "ah",
  "oh",
  "huh",
  "what",
  "sorry",
  "pardon",
  "a",
  "the",
  "and",
  "so",
  "like",
  "well",
]);

type SpeechKind = "noise" | "weak" | "substantive";

/**
 * Only full-sentence-ish candidate speech should advance the interview.
 * Coughs, clicks, short fillers, and half-answers must not skip ahead.
 */
function classifyUserSpeech(text: string, resumeText?: string): SpeechKind {
  const t = text.trim();
  if (!t || looksLikeResumeDump(t, resumeText)) return "noise";

  const words = t
    .split(/\s+/)
    .map((w) => w.replace(/[^\p{L}\p{N}']/gu, "").toLowerCase())
    .filter(Boolean);

  if (words.length < 3) return "noise";

  const meaningful = words.filter((w) => !FILLER_WORDS.has(w) && w.length > 1);
  if (meaningful.length < 2) return "noise";

  const normalized = words.join(" ");
  if (
    /^(okay|ok|um+|uh+|hmm+|yeah|yes|no|right|alright|sure|hello|hi)(\s+(okay|ok|um+|uh+|yeah|yes|right|so|like|well))*$/i.test(
      normalized,
    )
  ) {
    return "noise";
  }

  if (
    /^(i don't know|i dont know|no idea|not sure|nothing|skip|next question)([.!? ]*)$/i.test(
      t,
    )
  ) {
    return "weak";
  }

  if (t.length < 40 || words.length < 10 || meaningful.length < 6) return "weak";
  return "substantive";
}

/** Realtime API races / config noise. Never surface to the candidate UI. */
function isIgnorableRealtimeError(code?: string, message?: string): boolean {
  const c = (code ?? "").toLowerCase();
  const m = (message ?? "").toLowerCase();
  if (
    c === "cannot_update_voice" ||
    c === "conversation_already_has_active_response" ||
    c === "response_cancel_not_active" ||
    c === "input_audio_buffer_commit_empty"
  ) {
    return true;
  }
  if (m.includes("already has an active response")) return true;
  if (m.includes("no active response")) return true;
  if (m.includes("buffer is empty")) return true;
  return false;
}

function isRateLimitError(code?: string, message?: string): boolean {
  const c = (code ?? "").toLowerCase();
  const m = (message ?? "").toLowerCase();
  return c.includes("rate_limit") || m.includes("rate limit") || m.includes("429");
}

function isContextError(code?: string, message?: string): boolean {
  const c = (code ?? "").toLowerCase();
  const m = (message ?? "").toLowerCase();
  return (
    c.includes("context") ||
    m.includes("context length") ||
    m.includes("maximum context") ||
    m.includes("too many tokens")
  );
}

function upsertPartialCaption(
  prev: Caption[],
  role: "user" | "assistant",
  id: string,
  text: string,
): Caption[] {
  const idx = prev.findIndex((c) => c.id === id || (c.role === role && c.partial));
  if (idx >= 0) {
    const next = [...prev];
    next[idx] = { ...next[idx], id, role, text, partial: true };
    return next;
  }
  return [...prev, { id, role, text, partial: true }];
}

function finalizePartialCaption(
  prev: Caption[],
  role: "user" | "assistant",
  id: string,
  text: string,
): Caption[] {
  const idx = prev.findIndex((c) => c.id === id || (c.role === role && c.partial));
  if (idx >= 0) {
    const next = [...prev];
    next[idx] = { ...next[idx], id, role, text, partial: false };
    return next;
  }
  return [...prev, { id, role, text, partial: false }];
}

export function useRealtimeSession(options: Options) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [activeSpeaker, setActiveSpeaker] = useState<Speaker>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [captions, setCaptions] = useState<Caption[]>([]);
  const [remoteStream, setRemoteStream] = useState<MediaStream | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const localStreamRef = useRef<MediaStream | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const retryUsedRef = useRef(false);
  const startedRef = useRef(false);
  const partialAssistantRef = useRef<string>("");
  const partialUserRef = useRef<string>("");
  const assistantPartialIdRef = useRef(`a-${Date.now()}`);
  const userPartialIdRef = useRef(`u-${Date.now()}`);
  const assistantSpeakingRef = useRef(false);
  /** True from response.created until response.done. Gates response.create */
  const responseInFlightRef = useRef(false);
  const inFlightWatchdogRef = useRef<number | null>(null);
  const pendingContinueRef = useRef<"advance" | "restate" | null>(null);
  const greetingDoneRef = useRef(false);
  /** Wait for ASR before deciding whether to create an assistant turn */
  const awaitingTranscriptRef = useRef(false);
  const transcriptWaitTimerRef = useRef<number | null>(null);
  /** Ignore echo/bleed right after the AI finishes speaking */
  const ignoreSpeechUntilRef = useRef(0);
  const lastAssistantTextRef = useRef("");
  const instructionsRef = useRef(options.instructions);
  const interviewIdRef = useRef(options.interviewId);
  const candidateNameRef = useRef(options.candidateName);
  const interviewerNameRef = useRef(options.interviewerName);
  const demoRef = useRef(options.demo);
  const transcriptionContextRef = useRef(options.transcriptionContext);
  const resumeTextRef = useRef(options.resumeText ?? "");
  const pendingGreetingRef = useRef(false);
  const greetingTimerRef = useRef<number | null>(null);
  const loggerRef = useRef<ReturnType<typeof createRealtimeLogger> | null>(null);
  const rateLimitResetRef = useRef(3);
  const rateLimitRetryTimerRef = useRef<number | null>(null);

  instructionsRef.current = options.instructions;
  interviewIdRef.current = options.interviewId;
  candidateNameRef.current = options.candidateName;
  interviewerNameRef.current = options.interviewerName;
  demoRef.current = options.demo;
  transcriptionContextRef.current = options.transcriptionContext;
  resumeTextRef.current = options.resumeText ?? "";

  const logTranscript = useCallback(async (role: "user" | "assistant", text: string) => {
    const id = interviewIdRef.current;
    if (!id || !text.trim()) return;
    if (isResumeLeak(text, resumeTextRef.current, role)) return;
    try {
      await fetch(`/api/interview/${id}/transcript`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role, text, timestamp: new Date().toISOString() }),
      });
    } catch (err) {
      console.warn("Failed to log transcript turn", err);
    }
  }, []);

  const cleanup = useCallback(() => {
    if (transcriptWaitTimerRef.current != null) {
      window.clearTimeout(transcriptWaitTimerRef.current);
      transcriptWaitTimerRef.current = null;
    }
    if (greetingTimerRef.current != null) {
      window.clearTimeout(greetingTimerRef.current);
      greetingTimerRef.current = null;
    }
    if (inFlightWatchdogRef.current != null) {
      window.clearTimeout(inFlightWatchdogRef.current);
      inFlightWatchdogRef.current = null;
    }
    if (rateLimitRetryTimerRef.current != null) {
      window.clearTimeout(rateLimitRetryTimerRef.current);
      rateLimitRetryTimerRef.current = null;
    }
    loggerRef.current?.log("app", "cleanup", {
      inFlight: responseInFlightRef.current,
      speaking: assistantSpeakingRef.current,
    });
    loggerRef.current?.stop();
    loggerRef.current = null;
    pendingContinueRef.current = null;
    pendingGreetingRef.current = false;
    awaitingTranscriptRef.current = false;
    dcRef.current?.close();
    pcRef.current?.close();
    localStreamRef.current?.getTracks().forEach((t) => t.stop());
    dcRef.current = null;
    pcRef.current = null;
    localStreamRef.current = null;
    if (audioElRef.current) {
      audioElRef.current.srcObject = null;
    }
  }, []);

  const discardUserPartial = useCallback(() => {
    partialUserRef.current = "";
    setCaptions((prev) => prev.filter((c) => !(c.role === "user" && c.partial)));
  }, []);

  const clearTranscriptWait = useCallback(() => {
    awaitingTranscriptRef.current = false;
    if (transcriptWaitTimerRef.current != null) {
      window.clearTimeout(transcriptWaitTimerRef.current);
      transcriptWaitTimerRef.current = null;
    }
  }, []);

  const dropNoiseItem = useCallback((itemId?: string) => {
    const dc = dcRef.current;
    if (!dc || dc.readyState !== "open") return;
    try {
      dc.send(JSON.stringify({ type: "input_audio_buffer.clear" }));
      if (itemId) {
        dc.send(JSON.stringify({ type: "conversation.item.delete", item_id: itemId }));
      }
    } catch {
      /* ignore */
    }
  }, []);

  const clearInFlightWatchdog = useCallback(() => {
    if (inFlightWatchdogRef.current != null) {
      window.clearTimeout(inFlightWatchdogRef.current);
      inFlightWatchdogRef.current = null;
    }
  }, []);

  const armInFlightWatchdog = useCallback(() => {
    clearInFlightWatchdog();
    inFlightWatchdogRef.current = window.setTimeout(() => {
      if (!responseInFlightRef.current) return;
      loggerRef.current?.log("app", "inflight_watchdog", {
        pending: pendingContinueRef.current,
      });
      const dc = dcRef.current;
      if (dc) requestCancelResponse(dc);
      responseInFlightRef.current = false;
      assistantSpeakingRef.current = false;
      setIsThinking(false);
      const queued = pendingContinueRef.current;
      pendingContinueRef.current = null;
      if (queued && dc && dc.readyState === "open") {
        responseInFlightRef.current = true;
        setIsThinking(true);
        try {
          if (queued === "restate") requestRestateCurrentQuestion(dc);
          else requestAssistantResponse(dc);
          armInFlightWatchdog();
        } catch {
          responseInFlightRef.current = false;
          setIsThinking(false);
        }
      }
    }, 12000);
  }, [clearInFlightWatchdog]);

  const markResponseInFlight = useCallback(() => {
    responseInFlightRef.current = true;
    armInFlightWatchdog();
  }, [armInFlightWatchdog]);

  const askAssistant = useCallback(
    (kind: "advance" | "restate") => {
      const dc = dcRef.current;
      if (!dc || dc.readyState !== "open") return;
      if (responseInFlightRef.current || assistantSpeakingRef.current) {
        pendingContinueRef.current = kind;
        loggerRef.current?.log("app", "ask_queued", {
          kind,
          inFlight: responseInFlightRef.current,
          speaking: assistantSpeakingRef.current,
        });
        return;
      }
      loggerRef.current?.log("app", "ask_send", { kind });
      markResponseInFlight();
      setIsThinking(true);
      try {
        if (kind === "restate") requestRestateCurrentQuestion(dc);
        else requestAssistantResponse(dc);
      } catch {
        responseInFlightRef.current = false;
        clearInFlightWatchdog();
        setIsThinking(false);
      }
    },
    [clearInFlightWatchdog, markResponseInFlight],
  );

  const fireInitialGreeting = useCallback(() => {
    if (!pendingGreetingRef.current) return;
    if (greetingDoneRef.current) return;
    const dc = dcRef.current;
    if (!dc || dc.readyState !== "open") return;
    if (responseInFlightRef.current) return;

    pendingGreetingRef.current = false;
    if (greetingTimerRef.current != null) {
      window.clearTimeout(greetingTimerRef.current);
      greetingTimerRef.current = null;
    }
    markResponseInFlight();
    try {
      requestInitialGreeting(dc, candidateNameRef.current, {
        demo: demoRef.current,
        interviewerName: interviewerNameRef.current,
      });
    } catch {
      responseInFlightRef.current = false;
      clearInFlightWatchdog();
      pendingGreetingRef.current = true;
    }
  }, [clearInFlightWatchdog, markResponseInFlight]);

  const handleServerEvent = useCallback(
    (raw: MessageEvent) => {
      let event: Record<string, unknown>;
      try {
        event = JSON.parse(String(raw.data)) as Record<string, unknown>;
      } catch {
        return;
      }

      try {
      const type = String(event.type ?? "");
      loggerRef.current?.logRealtime(event);
      const assistantBusy = assistantSpeakingRef.current;

      if (type === "session.updated" || type === "session.created") {
        fireInitialGreeting();
      }

      if (type === "input_audio_buffer.speech_started") {
        // Echo / cough / noise while AI is talking or in post-speak cooldown
        if (assistantBusy) {
          dropNoiseItem();
          return;
        }
        setActiveSpeaker("user");
        setIsThinking(false);
        userPartialIdRef.current = `u-${Date.now()}`;
        partialUserRef.current = "";
      }

      if (type === "input_audio_buffer.speech_stopped") {
        if (assistantBusy) {
          clearTranscriptWait();
          dropNoiseItem();
          return;
        }
        setActiveSpeaker(null);
        // Do NOT create a response yet. Wait for a real transcript
        awaitingTranscriptRef.current = true;
        setIsThinking(true);
        if (transcriptWaitTimerRef.current != null) {
          window.clearTimeout(transcriptWaitTimerRef.current);
        }
        transcriptWaitTimerRef.current = window.setTimeout(() => {
          // ASR never arrived / noise only; stay on current question
          if (!awaitingTranscriptRef.current) return;
          clearTranscriptWait();
          setIsThinking(false);
          dropNoiseItem();
        }, 4500);
        return;
      }

      if (
        type === "response.created" ||
        type === "response.output_audio.delta" ||
        type === "response.audio.delta"
      ) {
        clearTranscriptWait();
        markResponseInFlight();
        setIsThinking(false);
        setActiveSpeaker("assistant");
        if (!assistantSpeakingRef.current) {
          assistantSpeakingRef.current = true;
          assistantPartialIdRef.current = `a-${Date.now()}`;
          partialAssistantRef.current = "";
          discardUserPartial();
        }
      }

      // Audio may finish before the response is fully closed. Keep in-flight until done
      if (type === "response.output_audio.done" || type === "response.audio.done") {
        assistantSpeakingRef.current = false;
        greetingDoneRef.current = true;
        ignoreSpeechUntilRef.current = Date.now() + 1000;
        setActiveSpeaker(null);
      }

      if (
        type === "response.done" ||
        type === "response.cancelled" ||
        type === "response.incomplete"
      ) {
        const response = event.response as
          | { status?: string; status_details?: unknown; usage?: unknown }
          | undefined;
        loggerRef.current?.log("app", "response_closed", {
          type,
          status: response?.status,
          status_details: response?.status_details,
          usage: response?.usage,
          pending: pendingContinueRef.current,
        });
        responseInFlightRef.current = false;
        assistantSpeakingRef.current = false;
        greetingDoneRef.current = true;
        ignoreSpeechUntilRef.current = Date.now() + 800;
        setActiveSpeaker(null);
        setIsThinking(false);
        if (inFlightWatchdogRef.current != null) {
          window.clearTimeout(inFlightWatchdogRef.current);
          inFlightWatchdogRef.current = null;
        }
        const queued = pendingContinueRef.current;
        if (queued) {
          pendingContinueRef.current = null;
          window.setTimeout(() => askAssistant(queued), 250);
        } else if (response?.status === "failed") {
          loggerRef.current?.log("app", "response_failed_no_queue", {
            status_details: response.status_details,
          });
        }
      }

      // Assistant transcript: update one growing line per turn
      if (
        type === "response.output_audio_transcript.delta" ||
        type === "response.audio_transcript.delta"
      ) {
        const incoming = String(event.delta ?? event.transcript ?? "");
        partialAssistantRef.current = applyTranscriptDelta(
          partialAssistantRef.current,
          incoming,
        );
        const text = partialAssistantRef.current;
        if (isResumeLeak(text, resumeTextRef.current, "assistant")) {
          setCaptions((prev) => prev.filter((c) => !(c.role === "assistant" && c.partial)));
          return;
        }
        setCaptions((prev) =>
          upsertPartialCaption(prev, "assistant", assistantPartialIdRef.current, text),
        );
      }

      if (
        type === "response.output_audio_transcript.done" ||
        type === "response.audio_transcript.done"
      ) {
        const text =
          String(event.transcript ?? partialAssistantRef.current).trim() ||
          partialAssistantRef.current.trim();
        partialAssistantRef.current = "";
        greetingDoneRef.current = true;
        assistantSpeakingRef.current = false;
        ignoreSpeechUntilRef.current = Date.now() + 1000;
        if (text) {
          if (isResumeLeak(text, resumeTextRef.current, "assistant")) {
            loggerRef.current?.log("app", "resume_leak_dropped", {
              role: "assistant",
              chars: text.length,
              preview: text.slice(0, 160),
            });
            setCaptions((prev) => prev.filter((c) => !(c.role === "assistant" && c.partial)));
            return;
          }
          lastAssistantTextRef.current = text;
          setCaptions((prev) =>
            finalizePartialCaption(prev, "assistant", assistantPartialIdRef.current, text),
          );
          void logTranscript("assistant", text);
        }
      }

      // User captions: live deltas, but never during AI speech / before first greeting
      const allowUserCaptions = greetingDoneRef.current && !assistantSpeakingRef.current;

      if (type === "conversation.item.input_audio_transcription.delta") {
        if (!allowUserCaptions) {
          discardUserPartial();
          return;
        }
        const incoming = String(event.delta ?? event.transcript ?? "");
        partialUserRef.current = applyTranscriptDelta(partialUserRef.current, incoming);
        const text = partialUserRef.current;
        if (looksLikeResumeDump(text, resumeTextRef.current)) {
          loggerRef.current?.log("app", "resume_leak_dropped", {
            role: "user",
            stage: "delta",
            chars: text.length,
            preview: text.slice(0, 160),
          });
          discardUserPartial();
          return;
        }
        setCaptions((prev) =>
          upsertPartialCaption(prev, "user", userPartialIdRef.current, text),
        );
      }

      if (type === "conversation.item.input_audio_transcription.completed") {
        const itemId = typeof event.item_id === "string" ? event.item_id : undefined;
        const text = pickBestTranscript(
          String(event.transcript ?? ""),
          partialUserRef.current,
        );
        partialUserRef.current = "";

        clearTranscriptWait();

        if (!greetingDoneRef.current || assistantSpeakingRef.current) {
          discardUserPartial();
          dropNoiseItem(itemId);
          setIsThinking(false);
          return;
        }

        if (isLikelyEchoOfAssistant(text, lastAssistantTextRef.current)) {
          loggerRef.current?.log("app", "user_transcript_echo", {
            chars: text.length,
            preview: text.slice(0, 160),
          });
          discardUserPartial();
          dropNoiseItem(itemId);
          setIsThinking(false);
          return;
        }

        if (looksLikeResumeDump(text, resumeTextRef.current)) {
          loggerRef.current?.log("app", "resume_leak_dropped", {
            role: "user",
            stage: "completed",
            chars: text.length,
            preview: text.slice(0, 160),
          });
          discardUserPartial();
          dropNoiseItem(itemId);
          setIsThinking(false);
          return;
        }

        const kind = classifyUserSpeech(text, resumeTextRef.current);
        loggerRef.current?.log("app", "user_transcript", {
          kind,
          chars: text.length,
          words: text.trim().split(/\s+/).filter(Boolean).length,
          preview: text.slice(0, 280),
        });
        if (!text || kind === "noise") {
          discardUserPartial();
          dropNoiseItem(itemId);
          setIsThinking(false);
          return;
        }

        setCaptions((prev) =>
          finalizePartialCaption(prev, "user", userPartialIdRef.current, text),
        );
        void logTranscript("user", text);

        if (kind === "weak") {
          askAssistant("restate");
          return;
        }

        askAssistant("advance");
        return;
      }

      if (type === "conversation.item.input_audio_transcription.failed") {
        clearTranscriptWait();
        discardUserPartial();
        setIsThinking(false);
        dropNoiseItem(typeof event.item_id === "string" ? event.item_id : undefined);
      }

      if (type === "rate_limits.updated") {
        const limits = Array.isArray(event.rate_limits) ? event.rate_limits : [];
        for (const raw of limits) {
          const limit = raw as { name?: string; remaining?: number; reset_seconds?: number };
          if (limit.name === "tokens" && typeof limit.reset_seconds === "number") {
            rateLimitResetRef.current = limit.reset_seconds;
          }
          if (
            limit.name === "tokens" &&
            typeof limit.remaining === "number" &&
            limit.remaining < 400
          ) {
            loggerRef.current?.log("app", "rate_limit_low", limit);
          }
        }
      }

      if (type === "error") {
        const errObj = (event.error ?? event) as {
          code?: string;
          message?: string;
          type?: string;
        };
        const code = errObj.code ?? errObj.type;
        const message = errObj.message;

        if (isRateLimitError(code, message)) {
          loggerRef.current?.log("app", "rate_limit_error", { code, message });
          responseInFlightRef.current = false;
          clearInFlightWatchdog();
          const waitMs = Math.min(Math.max(rateLimitResetRef.current, 2), 12) * 1000;
          if (rateLimitRetryTimerRef.current != null) {
            window.clearTimeout(rateLimitRetryTimerRef.current);
          }
          rateLimitRetryTimerRef.current = window.setTimeout(() => {
            const queued = pendingContinueRef.current ?? "advance";
            pendingContinueRef.current = null;
            askAssistant(queued);
          }, waitMs);
          return;
        }

        if (
          (code ?? "").includes("active_response") ||
          (message ?? "").toLowerCase().includes("active response")
        ) {
          loggerRef.current?.log("app", "active_response_conflict", { code, message });
          const dc = dcRef.current;
          if (dc) requestCancelResponse(dc);
          return;
        }

        if (isIgnorableRealtimeError(code, message)) {
          console.warn("Ignoring Realtime API error", code);
          return;
        }

        if (isContextError(code, message)) {
          loggerRef.current?.log("app", "context_error", { code, message });
          responseInFlightRef.current = false;
          clearInFlightWatchdog();
          setError("The live session ran out of context. End and restart if Aven goes quiet.");
          return;
        }

        console.error("Realtime error event", event);
        loggerRef.current?.log("app", "realtime_error", { code, message });
        setError(
          "Something went wrong with the connection. Please continue, or end and restart if it persists.",
        );
      }
      } catch (err) {
        loggerRef.current?.log("app", "handler_throw", {
          message: err instanceof Error ? err.message : String(err),
        });
        console.error("Realtime event handler threw", err);
      }
    },
    [askAssistant, clearInFlightWatchdog, clearTranscriptWait, discardUserPartial, dropNoiseItem, fireInitialGreeting, logTranscript, markResponseInFlight],
  );

  const connect = useCallback(async () => {
    setError(null);
    setConnectionState(retryUsedRef.current ? "reconnecting" : "connecting");
    greetingDoneRef.current = false;
    assistantSpeakingRef.current = false;
    responseInFlightRef.current = false;
    awaitingTranscriptRef.current = false;
    pendingContinueRef.current = null;
    ignoreSpeechUntilRef.current = 0;
    lastAssistantTextRef.current = "";
    partialAssistantRef.current = "";
    partialUserRef.current = "";
    setCaptions([]);

    try {
      cleanup();
      loggerRef.current = createRealtimeLogger(interviewIdRef.current);
      loggerRef.current?.log("app", "connect_start", {
        instructionChars: instructionsRef.current.length,
      });

      const session = await fetchEphemeralSession(instructionsRef.current);
      if (!loggerRef.current) {
        loggerRef.current = createRealtimeLogger(interviewIdRef.current);
      }
      loggerRef.current?.log("app", "session_minted", {
        model: session.model,
        expires_at: session.expires_at,
      });

      if (!audioElRef.current) {
        const el = document.createElement("audio");
        el.autoplay = true;
        el.setAttribute("playsinline", "true");
        document.body.appendChild(el);
        audioElRef.current = el;
      }

      const { pc, dc, localStream: mic } = await connectRealtimeWebRTC({
        ephemeralKey: session.client_secret,
        model: session.model,
        instructions: instructionsRef.current,
        onRemoteTrack: (stream) => {
          setRemoteStream(stream);
          if (audioElRef.current) {
            audioElRef.current.srcObject = stream;
            void audioElRef.current.play().catch(() => undefined);
          }
        },
        onDataChannel: (channel) => {
          loggerRef.current?.log("dc", "created", { readyState: channel.readyState });
          channel.addEventListener("message", handleServerEvent);
          channel.addEventListener("close", () => {
            loggerRef.current?.log("dc", "close");
          });
          channel.addEventListener("error", () => {
            loggerRef.current?.log("dc", "error");
          });
          channel.addEventListener("open", () => {
            loggerRef.current?.log("dc", "open");
            sendSessionUpdate(
              channel,
              instructionsRef.current,
              transcriptionContextRef.current,
            );
            pendingGreetingRef.current = true;
            if (greetingTimerRef.current != null) {
              window.clearTimeout(greetingTimerRef.current);
            }
            greetingTimerRef.current = window.setTimeout(() => {
              fireInitialGreeting();
            }, 2000);
          });
        },
      });

      pcRef.current = pc;
      dcRef.current = dc;
      localStreamRef.current = mic;
      setLocalStream(mic);

      pc.onconnectionstatechange = () => {
        const state = pc.connectionState;
        loggerRef.current?.log("pc", "connectionstate", { state });
        if (state === "connected") {
          setConnectionState("live");
        } else if (state === "failed" || state === "disconnected") {
          if (!retryUsedRef.current) {
            retryUsedRef.current = true;
            void connect();
          } else {
            setConnectionState("error");
            setError("Connection lost");
          }
        }
      };
      pc.oniceconnectionstatechange = () => {
        loggerRef.current?.log("pc", "ice", { state: pc.iceConnectionState });
      };

      setConnectionState("live");
    } catch (err) {
      console.error(err);
      setConnectionState("error");
      setError(err instanceof Error ? err.message : "Connection failed");
    }
  }, [cleanup, fireInitialGreeting, handleServerEvent]);

  const disconnect = useCallback(() => {
    cleanup();
    setConnectionState("ended");
    setActiveSpeaker(null);
    setIsThinking(false);
  }, [cleanup]);

  useEffect(() => {
    if (options.autoStart && !startedRef.current) {
      startedRef.current = true;
      void connect();
    }
    return () => {
      cleanup();
      if (audioElRef.current) {
        audioElRef.current.remove();
        audioElRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    connectionState,
    error,
    activeSpeaker,
    isThinking,
    captions,
    remoteStream,
    localStream,
    connect,
    disconnect,
  };
}
