/** Private case file for one /elevenlabs-interviewer call. Readable field names, fixed key order. */

export type TraceModels = {
  screening?: string;
  clinical?: string;
  wording?: string;
  wordingFallback?: string;
  speechToText?: string;
  textToSpeech?: string;
  voiceLanguage?: string;
};

export type TraceAnalyst = {
  source: string;
  model?: string;
  intent?: string;
};

export type TraceTurn = {
  index: number;
  stage?: string;
  focus?: string;
  move?: string;
  line?: string;
  heard?: string;
  spoken?: string;
  commit?: string;
  attempt?: number;
  analyst: TraceAnalyst;
  timeline?: { fromSessionStartMs: Record<string, number> };
  latencyMs?: Record<string, number>;
};

export type TraceSlot = {
  field: string;
  value: unknown;
  status: string;
  confidence: number;
  attempts: number;
};

export type TraceDocument = {
  interviewId: string;
  language: string;
  startedAt: string;
  build: string;
  models: TraceModels;
  turns: TraceTurn[];
  summary?: Record<string, unknown>;
  closed?: {
    at: string;
    reason: string;
    outcome: string | null;
    stage: string;
    durationMs: number;
    slots: TraceSlot[];
  };
};

const MODEL_KEYS = [
  "screening",
  "clinical",
  "wording",
  "wordingFallback",
  "speechToText",
  "textToSpeech",
  "voiceLanguage",
] as const;

const TIMELINE_KEYS = ["speechEnd", "scribeFinal", "directorDone", "replyAudio"] as const;

const LATENCY_KEYS = [
  "scribeAfterSpeech",
  "director",
  "replyAfterSpeech",
  "firstAudioAfterSpeech",
  "wordingFirstToken",
  "speechFirstByte",
  "endOfUtterance",
  "transcription",
  "fillerAfterSpeech",
] as const;

const LINES = new Set(["fixed", "guided", "paraphrase"]);
const COMMITS = new Set(["short_answer", "normal"]);
const ANALYST_SOURCES = new Set(["llm", "heuristic", "unknown"]);

const SUMMARY_KEYS: Record<string, string> = {
  ttfa_vad_ms: "firstAudioAfterSpeechMs",
  reply_from_vad_ms: "replyAfterSpeechMs",
  director_ms: "directorMs",
  stt_final_from_vad_ms: "scribeAfterSpeechMs",
  llm_ttft_ms: "wordingFirstTokenMs",
  tts_ttfb_ms: "speechFirstByteMs",
  eou_delay_ms: "endOfUtteranceMs",
  transcription_delay_ms: "transcriptionMs",
  filler_from_vad_ms: "fillerAfterSpeechMs",
};

export function emptyTrace(interviewId: string): TraceDocument {
  return {
    interviewId,
    language: "",
    startedAt: "",
    build: "",
    models: {},
    turns: [],
  };
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function text(value: unknown, max: number): string {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, max);
}

function millis(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) return undefined;
  return Math.round(value);
}

function pickNumbers(source: unknown, keys: readonly string[]): Record<string, number> | undefined {
  const record = asRecord(source);
  if (!record) return undefined;
  const out: Record<string, number> = {};
  for (const key of keys) {
    const ms = millis(record[key]);
    if (ms != null) out[key] = ms;
  }
  return Object.keys(out).length ? out : undefined;
}

function modelsFrom(source: unknown): TraceModels {
  const record = asRecord(source);
  const out: TraceModels = {};
  if (!record) return out;
  for (const key of MODEL_KEYS) {
    const value = text(record[key], 80);
    if (value) out[key] = value;
  }
  return out;
}

function analystFrom(source: unknown): TraceAnalyst {
  const record = asRecord(source);
  const sourceName = text(record?.source, 20);
  const analyst: TraceAnalyst = {
    source: ANALYST_SOURCES.has(sourceName) ? sourceName : "unknown",
  };
  const model = text(record?.model, 80);
  const intent = text(record?.intent, 40);
  if (analyst.source === "llm" && model) analyst.model = model;
  if (intent) analyst.intent = intent;
  return analyst;
}

function turnFrom(source: unknown): TraceTurn | null {
  const record = asRecord(source);
  if (!record) return null;
  const index = millis(record.index);
  if (index == null) return null;
  const line = text(record.line, 20);
  const commit = text(record.commit, 20);
  const timeline = pickNumbers(asRecord(record.timeline)?.fromSessionStartMs, TIMELINE_KEYS);
  const latencyMs = pickNumbers(record.latencyMs, LATENCY_KEYS);
  const spoken = text(record.spoken, 4000);
  const attempt = millis(record.attempt);
  const turn: TraceTurn = {
    index,
    stage: text(record.stage, 40),
    focus: text(record.focus, 80),
    move: text(record.move, 80),
    line: LINES.has(line) ? line : "",
    heard: text(record.heard, 4000),
    commit: COMMITS.has(commit) ? commit : "",
    analyst: analystFrom(record.analyst),
  };
  if (spoken) turn.spoken = spoken;
  if (attempt != null) turn.attempt = attempt;
  if (timeline) turn.timeline = { fromSessionStartMs: timeline };
  if (latencyMs) turn.latencyMs = latencyMs;
  return turn;
}

function preferText(next: string | undefined, prev: string | undefined): string {
  return next || prev || "";
}

function shapeTurn(turn: {
  index: number;
  stage: string;
  focus: string;
  move: string;
  line: string;
  heard: string;
  spoken?: string;
  commit: string;
  attempt?: number;
  analyst: TraceAnalyst;
  timeline?: Record<string, number>;
  latencyMs?: Record<string, number>;
}): TraceTurn {
  const shaped: TraceTurn = { index: turn.index, analyst: turn.analyst };
  if (turn.stage) shaped.stage = turn.stage;
  if (turn.focus) shaped.focus = turn.focus;
  if (turn.move) shaped.move = turn.move;
  if (turn.line) shaped.line = turn.line;
  if (turn.heard) shaped.heard = turn.heard;
  if (turn.spoken) shaped.spoken = turn.spoken;
  if (turn.commit) shaped.commit = turn.commit;
  if (turn.attempt != null) shaped.attempt = turn.attempt;
  if (turn.timeline && Object.keys(turn.timeline).length) shaped.timeline = { fromSessionStartMs: turn.timeline };
  if (turn.latencyMs && Object.keys(turn.latencyMs).length) shaped.latencyMs = turn.latencyMs;
  return shaped;
}

function mergeTurn(prev: TraceTurn | undefined, next: TraceTurn): TraceTurn {
  const spoken = next.spoken || prev?.spoken;
  const attempt = next.attempt ?? prev?.attempt;
  const timeline = { ...prev?.timeline?.fromSessionStartMs, ...next.timeline?.fromSessionStartMs };
  const latencyMs = { ...prev?.latencyMs, ...next.latencyMs };
  const analyst: TraceAnalyst = {
    source: next.analyst.source !== "unknown" ? next.analyst.source : prev?.analyst.source || "unknown",
  };
  const model = next.analyst.model || prev?.analyst.model;
  const intent = next.analyst.intent || prev?.analyst.intent;
  if (model && analyst.source === "llm") analyst.model = model;
  if (intent) analyst.intent = intent;
  return shapeTurn({
    index: next.index,
    stage: preferText(next.stage, prev?.stage),
    focus: preferText(next.focus, prev?.focus),
    move: preferText(next.move, prev?.move),
    line: preferText(next.line, prev?.line),
    heard: preferText(next.heard, prev?.heard),
    spoken,
    commit: preferText(next.commit, prev?.commit),
    attempt,
    analyst,
    timeline,
    latencyMs,
  });
}

function slotsFrom(source: unknown): TraceSlot[] {
  if (!Array.isArray(source)) return [];
  const slots: TraceSlot[] = [];
  for (const item of source) {
    const record = asRecord(item);
    if (!record) continue;
    const field = text(record.field, 80);
    const status = text(record.status, 40);
    if (!field || (status === "empty" && (record.value == null || record.value === ""))) continue;
    const confidence = typeof record.confidence === "number" && Number.isFinite(record.confidence) ? record.confidence : 0;
    slots.push({
      field,
      value: record.value ?? null,
      status: status || "empty",
      confidence: Math.round(confidence * 100) / 100,
      attempts: millis(record.attempts) ?? 0,
    });
  }
  return slots;
}

function summaryFrom(source: unknown): Record<string, unknown> | undefined {
  const record = asRecord(source);
  if (!record) return undefined;
  const summary: Record<string, unknown> = {};
  const turns = millis(record.turns);
  if (turns != null) summary.turns = turns;
  for (const [raw, name] of Object.entries(SUMMARY_KEYS)) {
    const stat = asRecord(record[raw]);
    if (!stat) continue;
    const count = millis(stat.n);
    const median = millis(stat.p50);
    const p95 = millis(stat.p95);
    const max = millis(stat.max);
    if (count == null && median == null && p95 == null && max == null) continue;
    summary[name] = {
      ...(count != null ? { count } : {}),
      ...(median != null ? { median } : {}),
      ...(p95 != null ? { p95 } : {}),
      ...(max != null ? { max } : {}),
    };
  }
  return Object.keys(summary).length ? summary : undefined;
}

export function applyTraceChange(interviewId: string, current: TraceDocument | null, body: unknown): TraceDocument {
  const doc = current ?? emptyTrace(interviewId);
  const record = asRecord(body);
  const op = text(record?.op, 20);
  if (op === "open") {
    const models = { ...doc.models, ...modelsFrom(record?.models) };
    return {
      interviewId,
      language: text(record?.language, 20) || doc.language,
      startedAt: text(record?.startedAt, 40) || doc.startedAt,
      build: text(record?.build, 80) || doc.build,
      models,
      turns: doc.turns,
      ...(doc.summary ? { summary: doc.summary } : {}),
      ...(doc.closed ? { closed: doc.closed } : {}),
    };
  }
  if (op === "turn") {
    const incoming = turnFrom(record);
    if (!incoming) return doc;
    const turns = doc.turns.slice();
    const at = turns.findIndex((turn) => turn.index === incoming.index);
    if (at >= 0) turns[at] = mergeTurn(turns[at], incoming);
    else turns.push(mergeTurn(undefined, incoming));
    turns.sort((a, b) => a.index - b.index);
    return { ...doc, turns };
  }
  if (op === "spoken") {
    const index = millis(record?.index);
    const spoken = text(record?.spoken, 4000);
    if (index == null || !spoken) return doc;
    const turns = doc.turns.map((turn) => (turn.index === index ? mergeTurn(turn, { ...turn, spoken }) : turn));
    return { ...doc, turns };
  }
  if (op === "close") {
    const outcome = text(record?.outcome, 80);
    const summary = summaryFrom(record?.summary);
    return {
      ...doc,
      ...(summary ? { summary } : {}),
      closed: {
        at: text(record?.at, 40),
        reason: text(record?.reason, 80) || "dropped",
        outcome: outcome || null,
        stage: text(record?.stage, 40),
        durationMs: millis(record?.durationMs) ?? 0,
        slots: slotsFrom(record?.slots),
      },
    };
  }
  return doc;
}
