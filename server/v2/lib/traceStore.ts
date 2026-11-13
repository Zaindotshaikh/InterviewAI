import { SQL } from "bun";
import { applyTraceChange, emptyTrace, type TraceDocument } from "./traceDocument.js";

let db: InstanceType<typeof SQL> | null = null;
let ready: Promise<void> | null = null;
let warned = false;

async function database(): Promise<InstanceType<typeof SQL> | null> {
  const url = process.env.DATABASE_URL?.trim();
  if (!url) {
    if (!warned) {
      warned = true;
      console.info("[trace] DATABASE_URL unset; call file not stored");
    }
    return null;
  }
  if (!db) db = new SQL(url);
  ready ??= db`
    CREATE TABLE IF NOT EXISTS interview_traces (
      interview_id text PRIMARY KEY,
      document jsonb NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    )
  `
    .then(() => undefined)
    .catch((err: unknown) => {
      ready = null;
      throw err;
    });
  await ready;
  return db;
}

function readDocument(value: unknown, interviewId: string): TraceDocument {
  if (typeof value === "string") {
    try {
      value = JSON.parse(value) as unknown;
    } catch {
      return emptyTrace(interviewId);
    }
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return emptyTrace(interviewId);
  const record = value as Partial<TraceDocument>;
  return {
    interviewId,
    language: typeof record.language === "string" ? record.language : "",
    startedAt: typeof record.startedAt === "string" ? record.startedAt : "",
    build: typeof record.build === "string" ? record.build : "",
    models: record.models && typeof record.models === "object" ? record.models : {},
    turns: Array.isArray(record.turns) ? record.turns : [],
    ...(record.summary ? { summary: record.summary } : {}),
    ...(record.closed ? { closed: record.closed } : {}),
  };
}

export async function applyTrace(interviewId: string, body: unknown): Promise<{ ok: true; stored: boolean }> {
  const sql = await database();
  if (!sql) return { ok: true, stored: false };
  await sql.begin(async (tx) => {
    await tx`
      INSERT INTO interview_traces (interview_id, document)
      VALUES (${interviewId}, ${emptyTrace(interviewId)}::jsonb)
      ON CONFLICT (interview_id) DO NOTHING
    `;
    const rows = await tx`
      SELECT document FROM interview_traces WHERE interview_id = ${interviewId} FOR UPDATE
    `;
    const current = readDocument(rows[0]?.document, interviewId);
    const next = applyTraceChange(interviewId, current, body);
    await tx`
      UPDATE interview_traces
      SET document = ${next}::jsonb, updated_at = now()
      WHERE interview_id = ${interviewId}
    `;
  });
  return { ok: true, stored: true };
}

export async function readTrace(interviewId: string): Promise<TraceDocument | null> {
  const sql = await database();
  if (!sql) return null;
  const rows = await sql`SELECT document FROM interview_traces WHERE interview_id = ${interviewId}`;
  if (!rows[0]) return null;
  return readDocument(rows[0].document, interviewId);
}
