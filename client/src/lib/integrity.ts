export type IntegrityFlagType = "no_face" | "multiple_faces" | "looked_away";

export type IntegrityEvent = {
  type: IntegrityFlagType;
  startTime: string;
  endTime: string;
  durationSeconds: number;
};

export type IntegrityReport = {
  available: boolean;
  events: IntegrityEvent[];
};

export function summarizeIntegrityEvents(events: IntegrityEvent[]): string[] {
  if (!events.length) return [];

  const byType = {
    no_face: events.filter((e) => e.type === "no_face"),
    multiple_faces: events.filter((e) => e.type === "multiple_faces"),
    looked_away: events.filter((e) => e.type === "looked_away"),
  };

  const lines: string[] = [];

  if (byType.looked_away.length) {
    const avg =
      byType.looked_away.reduce((s, e) => s + e.durationSeconds, 0) /
      byType.looked_away.length;
    lines.push(
      `Looked away from camera ${byType.looked_away.length} time${
        byType.looked_away.length === 1 ? "" : "s"
      } (avg ${avg.toFixed(1)}s)`,
    );
  }

  if (byType.no_face.length) {
    lines.push(
      `Camera briefly lost face detection (${byType.no_face.length} instance${
        byType.no_face.length === 1 ? "" : "s"
      })`,
    );
  }

  if (byType.multiple_faces.length) {
    lines.push(
      `More than one face detected in frame (${byType.multiple_faces.length} instance${
        byType.multiple_faces.length === 1 ? "" : "s"
      })`,
    );
  }

  return lines;
}
