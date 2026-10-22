import type { TranscriptTurn } from "../../lib/store.js";
import type { V2Event } from "./types.js";

export type ReviewTurn = {
  role: "user" | "assistant";
  text: string;
  timestamp: string;
  move?: string;
};

/** Pair each candidate line with the flow move it caused. */
export function turnsForReview(turns: TranscriptTurn[], events: V2Event[]): ReviewTurn[] {
  const stored = turns.some((t) => t.role === "user" && t.move);
  const fromEvents = events.filter((e) => e.type === "flow.move");
  let eventIndex = 0;
  return turns.map((t) => {
    if (t.role !== "user") {
      return { role: t.role, text: t.text, timestamp: t.timestamp };
    }
    let move = t.move;
    if (!stored && !move && fromEvents[eventIndex]) {
      const kind = fromEvents[eventIndex]?.data?.kind;
      eventIndex += 1;
      if (typeof kind === "string" && kind) move = kind;
    }
    return {
      role: t.role,
      text: t.text,
      timestamp: t.timestamp,
      ...(move ? { move } : {}),
    };
  });
}
