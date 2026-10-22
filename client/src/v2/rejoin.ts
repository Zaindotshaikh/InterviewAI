/** Cascade demo only. GPT-Live must not read or write this key. */
export const ELEVENLABS_REJOIN_KEY = "interviewai.elevenlabs.rejoin";
export const REJOIN_WINDOW_MS = 120_000;

export type ElevenlabsRejoin = {
  interviewId: string;
  candidateName: string;
  roleTitle: string;
  language: string;
  interviewerName: string;
  interviewerTitle: string;
  livekitUrl: string;
  /** First-join token, kept only as a record. Rejoin always mints a new token. */
  token: string;
  /** Null while the call is up. Set when the page loads after a drop, or on a hard disconnect. */
  droppedAt: number | null;
};

export function readRejoin(): ElevenlabsRejoin | null {
  try {
    const raw = sessionStorage.getItem(ELEVENLABS_REJOIN_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as ElevenlabsRejoin;
    if (!parsed?.interviewId || !parsed.livekitUrl) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeRejoin(record: ElevenlabsRejoin) {
  sessionStorage.setItem(ELEVENLABS_REJOIN_KEY, JSON.stringify(record));
}

export function clearRejoin() {
  sessionStorage.removeItem(ELEVENLABS_REJOIN_KEY);
}

/** On refresh the new page load is the drop, if the call was still up. */
export function noteRefreshDrop(now = Date.now()): ElevenlabsRejoin | null {
  const current = readRejoin();
  if (!current) return null;
  if (current.droppedAt != null) return current;
  const next = { ...current, droppedAt: now };
  writeRejoin(next);
  return next;
}

export function rejoinLeftMs(record: ElevenlabsRejoin | null, now = Date.now()): number | null {
  if (!record?.droppedAt) return null;
  return Math.max(0, REJOIN_WINDOW_MS - (now - record.droppedAt));
}

export type RejoinToken = { url: string; token: string };

export async function requestRejoin(interviewId: string): Promise<RejoinToken> {
  const res = await fetch(`/api/v2/interview/${interviewId}/rejoin`, { method: "POST" });
  const body = (await res.json().catch(() => ({}))) as { error?: string; livekit?: { url?: string; token?: string } };
  if (res.status === 409 || body.error === "rejoin_window_closed") {
    throw new Error("rejoin_window_closed");
  }
  if (!res.ok || !body.livekit?.url || !body.livekit.token) {
    throw new Error(body.error || "Could not rejoin this interview");
  }
  return { url: body.livekit.url, token: body.livekit.token };
}
