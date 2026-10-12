import { appendFile, mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const dataDir = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "data");

export function debugLogPath(interviewId: string): string {
  const safe = interviewId.replace(/[^a-zA-Z0-9-]/g, "");
  return path.join(dataDir, `${safe}.debug.jsonl`);
}

export async function appendDebugEvents(
  interviewId: string,
  events: unknown[],
): Promise<void> {
  if (!interviewId || !Array.isArray(events) || events.length === 0) return;
  await mkdir(dataDir, { recursive: true });
  const lines = events
    .map((event) => JSON.stringify({ ts: new Date().toISOString(), event }))
    .join("\n");
  await appendFile(debugLogPath(interviewId), `${lines}\n`, "utf-8");
}
