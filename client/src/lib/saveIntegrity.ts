import type { IntegrityReport } from "./integrity";

/** Same v1 persistence path: stored on the interview record and copied into the scorecard. */
export async function saveIntegrityReport(
  interviewId: string,
  integrity: IntegrityReport,
): Promise<void> {
  const res = await fetch(`/api/interview/${interviewId}/integrity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(integrity),
  });
  if (!res.ok) {
    throw new Error("Failed to save integrity events");
  }
}
