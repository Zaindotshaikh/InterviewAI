import { mkdir, readFile, writeFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import {
  appendTranscriptTurn,
  createInterview,
  getInterview,
  saveSummary,
  type InterviewRecord,
  type TranscriptTurn,
} from "../../lib/store.js";
import type { V2ControllerState, V2Event, V2InterviewExtras } from "./types.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, "..", "..", "data");

function v2Path(id: string) {
  return path.join(dataDir, `${id}.v2.json`);
}

async function ensureDataDir() {
  await mkdir(dataDir, { recursive: true });
}

export async function saveV2Extras(id: string, extras: V2InterviewExtras): Promise<void> {
  await ensureDataDir();
  await writeFile(v2Path(id), JSON.stringify(extras, null, 2), "utf-8");
}

export async function getV2Extras(id: string): Promise<V2InterviewExtras | null> {
  try {
    const raw = await readFile(v2Path(id), "utf-8");
    return JSON.parse(raw) as V2InterviewExtras;
  } catch {
    return null;
  }
}

export async function createV2Interview(
  interview: InterviewRecord,
  extras: V2InterviewExtras,
): Promise<{ interview: InterviewRecord; extras: V2InterviewExtras }> {
  await createInterview(interview);
  await saveV2Extras(interview.id, extras);
  return { interview, extras };
}

export async function getV2Interview(id: string): Promise<{
  interview: InterviewRecord;
  extras: V2InterviewExtras;
} | null> {
  const interview = await getInterview(id);
  if (!interview) return null;
  const extras = await getV2Extras(id);
  if (!extras) return null;
  return { interview, extras };
}

// The agent posts transcript turns, events and state patches concurrently, and each one is a
// read-modify-write of the same files. Serialise them per interview so none overwrites another.
const locks = new Map<string, Promise<unknown>>();

function withLock<T>(id: string, fn: () => Promise<T>): Promise<T> {
  const prev = locks.get(id) ?? Promise.resolve();
  const run = prev.then(fn, fn);
  const tail = run.catch(() => undefined);
  locks.set(id, tail);
  void tail.then(() => {
    if (locks.get(id) === tail) locks.delete(id);
  });
  return run;
}

export const appendV2Transcript = (id: string, turn: TranscriptTurn & { turnIndex?: number }) =>
  withLock(id, () => appendV2TranscriptUnlocked(id, turn));
export const appendV2Event = (id: string, event: V2Event) => withLock(id, () => appendV2EventUnlocked(id, event));
export const updateV2Controller = (id: string, patch: Partial<V2ControllerState>) =>
  withLock(id, () => updateV2ControllerUnlocked(id, patch));
export const saveEnglishTranscript = (
  id: string,
  turns: { role: "user" | "assistant"; text: string; timestamp: string }[],
) => withLock(id, () => saveEnglishTranscriptUnlocked(id, turns));

async function appendV2TranscriptUnlocked(
  id: string,
  turn: TranscriptTurn & { turnIndex?: number },
): Promise<void> {
  const record = await getV2Interview(id);
  if (!record) throw new Error("Interview not found");

  // Idempotent by turnIndex + role + text when provided
  if (typeof turn.turnIndex === "number") {
    const existing = record.interview.transcript;
    const dup = existing.some(
      (t, i) =>
        i === turn.turnIndex ||
        (t.role === turn.role && t.text === turn.text && t.timestamp === turn.timestamp),
    );
    if (dup && existing.some((t) => t.role === turn.role && t.text === turn.text)) {
      // soft dedupe: if exact text+role already last, skip
      const last = existing[existing.length - 1];
      if (last && last.role === turn.role && last.text === turn.text) return;
    }
  }

  await appendTranscriptTurn(id, {
    role: turn.role,
    text: turn.text,
    timestamp: turn.timestamp,
    ...(turn.llmText != null ? { llmText: turn.llmText } : {}),
    ...(turn.interrupted != null ? { interrupted: turn.interrupted } : {}),
    ...(turn.move ? { move: turn.move } : {}),
  });

  const extras = record.extras;
  extras.controller.lastTurnAt = turn.timestamp;
  await saveV2Extras(id, extras);
}

async function appendV2EventUnlocked(id: string, event: V2Event): Promise<void> {
  const extras = await getV2Extras(id);
  if (!extras) throw new Error("Interview not found");
  extras.events.push(event);
  await saveV2Extras(id, extras);
}

async function updateV2ControllerUnlocked(id: string, patch: Partial<V2ControllerState>): Promise<V2ControllerState> {
  const extras = await getV2Extras(id);
  if (!extras) throw new Error("Interview not found");
  extras.controller = { ...extras.controller, ...patch };
  await saveV2Extras(id, extras);
  return extras.controller;
}

export async function completeV2Interview(id: string): Promise<void> {
  await updateV2Controller(id, { completed: true, lastTurnAt: new Date().toISOString() });
}

export async function saveV2Summary(id: string, summary: unknown): Promise<void> {
  await saveSummary(id, summary);
}

async function saveEnglishTranscriptUnlocked(
  id: string,
  turns: { role: "user" | "assistant"; text: string; timestamp: string }[],
): Promise<void> {
  const extras = await getV2Extras(id);
  if (!extras) throw new Error("Interview not found");
  extras.englishTranscript = turns;
  await saveV2Extras(id, extras);
}
