type DebugEvent = {
  t: number;
  src: "rt" | "app" | "pc" | "dc";
  type: string;
  data?: Record<string, unknown>;
};

const SKIP_TYPES = new Set([
  "response.output_audio.delta",
  "response.audio.delta",
  "response.output_audio_transcript.delta",
  "response.audio_transcript.delta",
  "conversation.item.input_audio_transcription.delta",
]);

function clip(value: unknown, max = 240): unknown {
  if (typeof value !== "string") return value;
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

export function summarizeRealtimeEvent(event: Record<string, unknown>): DebugEvent | null {
  const type = String(event.type ?? "unknown");
  if (SKIP_TYPES.has(type)) return null;

  const data: Record<string, unknown> = {};
  if (event.error && typeof event.error === "object") {
    const err = event.error as Record<string, unknown>;
    data.code = err.code;
    data.message = clip(err.message);
    data.error_type = err.type;
  }
  if (event.response && typeof event.response === "object") {
    const response = event.response as Record<string, unknown>;
    data.response_id = response.id;
    data.status = response.status;
    data.status_details = response.status_details;
    data.usage = response.usage;
  }
  if (Array.isArray(event.rate_limits)) data.rate_limits = event.rate_limits;
  if (event.transcript) data.transcript = clip(event.transcript);
  if (event.item_id) data.item_id = event.item_id;
  if (event.session && typeof event.session === "object") {
    const session = event.session as Record<string, unknown>;
    data.session_id = session.id;
    data.model = session.model;
    data.max_output_tokens = session.max_output_tokens ?? session.max_response_output_tokens;
    data.truncation = session.truncation;
  }

  return { t: Date.now(), src: "rt", type, data };
}

export function createRealtimeLogger(interviewId: string) {
  const buffer: DebugEvent[] = [];
  let timer: number | null = null;
  let stopped = false;

  const flush = () => {
    if (timer != null) {
      window.clearTimeout(timer);
      timer = null;
    }
    if (!interviewId || buffer.length === 0) return;
    const batch = buffer.splice(0, buffer.length);
    void fetch(`/api/interview/${interviewId}/debug`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    }).catch(() => undefined);
  };

  const schedule = () => {
    if (timer != null) return;
    timer = window.setTimeout(flush, 800);
  };

  const log = (src: DebugEvent["src"], type: string, data?: Record<string, unknown>) => {
    if (stopped) return;
    const event: DebugEvent = { t: Date.now(), src, type, data };
    buffer.push(event);
    const noisy = type.endsWith(".delta");
    if (!noisy) {
      console.info(`[rt] ${src} ${type}`, data ?? "");
    }
    if (buffer.length >= 20) flush();
    else schedule();
  };

  const logRealtime = (raw: Record<string, unknown>) => {
    if (stopped) return;
    const summarized = summarizeRealtimeEvent(raw);
    if (!summarized) return;
    buffer.push(summarized);
    console.info(`[rt] ${summarized.type}`, summarized.data ?? "");
    if (buffer.length >= 20) flush();
    else schedule();
  };

  const onHide = () => flush();
  window.addEventListener("pagehide", onHide);
  window.addEventListener("beforeunload", onHide);

  const stop = () => {
    stopped = true;
    window.removeEventListener("pagehide", onHide);
    window.removeEventListener("beforeunload", onHide);
    flush();
  };

  return { log, logRealtime, flush, stop };
}
