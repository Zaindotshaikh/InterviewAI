import { readFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import type { InterviewBlueprint } from "./types.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const cache = new Map<string, InterviewBlueprint>();

/** Blueprints are plain JSON so clinical reviewers can edit questions, key points and tiers without code. */
export async function loadBlueprint(name = "nursing"): Promise<InterviewBlueprint> {
  const safe = name.replace(/[^a-z0-9_-]/gi, "");
  const hit = cache.get(safe);
  if (hit) return hit;
  const raw = await readFile(path.join(__dirname, "blueprints", `${safe}.json`), "utf-8");
  const parsed = JSON.parse(raw) as InterviewBlueprint;
  if (!parsed.limits || !parsed.clinical?.areas?.length || !parsed.tiers?.length) {
    throw new Error(`Blueprint "${safe}" is missing limits, clinical areas or tiers`);
  }
  cache.set(safe, parsed);
  return parsed;
}

/** Planned length in minutes: screening + clinical target, never above the hard cap. */
export function blueprintTargetMinutes(bp: InterviewBlueprint): number {
  const l = bp.limits;
  const total = (l.screening_max_minutes ?? 7) + (l.clinical_target_minutes ?? 10);
  return Math.min(total, l.hard_cap_minutes ?? 25);
}
