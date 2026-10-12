import type { InterviewBlueprint, InterviewFlowState } from "./types.js";

export type TierEvidence = { area: string; point: string; quote: string; verified: boolean };

export type TierResult = {
  tier: string;
  tier_name: string;
  confidence: number;
  reasoning: string;
  method: "rule" | "model" | "rule_override";
  evidence: TierEvidence[];
  flags: string[];
};

export type AreaSummary = {
  id: string;
  title: string;
  outcome: string;
  level: number;
  covered: string[];
  missing: string[];
  red_flags: string[];
  dont_knows: number;
  evidence: { quality: string; quote: string; summary: string }[];
};

type Area = InterviewBlueprint["clinical"]["areas"][number];

const TIER_ORDER = ["tier_1", "tier_2", "tier_3"];

export function tierName(bp: InterviewBlueprint, id: string): string {
  return bp.tiers.find((t) => t.id === id)?.name ?? id;
}

/** Key point text by id, so the model (and the scorecard) read words, not ids. */
function keyPointText(area: Area | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const lv of (area?.levels ?? []) as { key_points?: { id: string; text: string }[] }[]) {
    for (const kp of lv.key_points ?? []) out.set(kp.id, kp.text);
  }
  return out;
}

export function summarizeAreas(flow: InterviewFlowState, bp: InterviewBlueprint): AreaSummary[] {
  const out: AreaSummary[] = [];
  for (const id of flow.area_order ?? Object.keys(flow.areas ?? {})) {
    const prog = flow.areas?.[id];
    if (!prog || (prog.status === "pending" && !prog.evidence?.length)) continue;
    const area = bp.clinical.areas.find((a) => a.id === id);
    const text = keyPointText(area);
    const words = (ids: string[]) => ids.map((k) => text.get(k) ?? k);
    out.push({
      id,
      title: area?.title ?? id,
      outcome: prog.outcome,
      level: prog.level,
      covered: words(prog.covered ?? []),
      missing: words(prog.missing ?? []),
      red_flags: prog.red_flags ?? [],
      dont_knows: prog.dont_knows ?? 0,
      evidence: (prog.evidence ?? []).map((e) => ({
        quality: e.quality,
        quote: e.quote ?? "",
        summary: e.summary ?? "",
      })),
    });
  }
  return out;
}

/** What the candidate told us, in the order the client's screening specification lists it. */
export function screeningFacts(flow: InterviewFlowState): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [id, slot] of Object.entries(flow.slots ?? {})) {
    if (slot.status === "captured" || slot.status === "confirmed") out[id] = slot.value;
    else if (slot.status === "unknown") out[id] = "not provided";
  }
  const care: Record<string, string> = {};
  for (const [id, c] of Object.entries(flow.care ?? {})) {
    if (c.stance !== "unknown") care[id] = c.persuasions ? `${c.stance} (after ${c.persuasions} explanation(s))` : c.stance;
  }
  if (Object.keys(care).length) out.care_duties = care;
  if (flow.experience_level && flow.experience_level !== "unknown") out.experience_level = flow.experience_level;
  return out;
}

export function behaviourFlags(flow: InterviewFlowState): string[] {
  const flags: string[] = [];
  const turns = Math.max(1, flow.turns ?? 0);
  if ((flow.unclear_total ?? 0) / turns > 0.25) flags.push("Many answers could not be heard clearly (audio quality)");
  if ((flow.dont_know_total ?? 0) >= 3) flags.push(`Said "I don't know" ${flow.dont_know_total} times`);
  if ((flow.nervous_events ?? 0) >= 2) flags.push("Appeared nervous during parts of the interview");
  if ((flow.interruptions ?? 0) > 0) flags.push(`Call dropped and resumed ${flow.interruptions} time(s)`);
  const open = (flow.contradictions ?? []).filter((c) => !c.resolved);
  if (open.length) flags.push(`${open.length} unresolved inconsistency in the candidate's statements`);
  return flags;
}

/**
 * Cases that need no judgement: the rules the client stated outright, or too little evidence to judge.
 * Returns null when the model should classify.
 */
export function precheck(flow: InterviewFlowState | undefined, bp: InterviewBlueprint): TierResult | null {
  const mk = (tier: string, reasoning: string, flags: string[]): TierResult => ({
    tier,
    tier_name: tierName(bp, tier),
    confidence: 1,
    reasoning,
    method: "rule",
    evidence: [],
    flags,
  });

  if (!flow || !flow.turns) {
    return mk("needs_review", "The interview produced no usable candidate answers.", ["No candidate answers recorded"]);
  }

  const flags = behaviourFlags(flow);

  const gateItem = flow.gate_failed;
  if (gateItem || flow.outcome === "screened_out") {
    const care = gateItem ? flow.care?.[gateItem] : undefined;
    const label = gateItem ? gateItem.replace(/_/g, " ") : "an essential care duty";
    const why = care?.reason ? ` Their reason: ${care.reason}.` : "";
    return mk(
      "not_eligible",
      `The candidate was not willing to do ${label}, an essential duty of this role, even after it was explained ` +
        `${care?.persuasions ?? 0} time(s).${why} The clinical round was therefore not conducted.`,
      flags,
    );
  }

  const assessed = Object.values(flow.areas ?? {}).filter((a) => a.status === "done" || (a.evidence?.length ?? 0) > 0);
  const reachedClinical = flow.stage === "clinical" || flow.stage === "closing" || flow.stage === "ended";
  const endedEarly = ["incomplete_silence", "incomplete_disconnect", "withdrew"].includes(flow.outcome ?? "");
  if (endedEarly && (!reachedClinical || assessed.length < 2)) {
    return mk(
      "needs_review",
      `The interview ended early (${flow.outcome}) before enough of the clinical conversation took place to classify the candidate.`,
      [...flags, `Interview ended early: ${flow.outcome}`],
    );
  }
  if ((flow.unclear_total ?? 0) / Math.max(1, flow.turns) > 0.5) {
    return mk(
      "needs_review",
      "More than half of the candidate's turns could not be heard clearly, so their answers cannot be fairly assessed.",
      [...flags, "Poor audio"],
    );
  }
  return null;
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[\s\p{P}]+/gu, " ").trim();
}

/** Marks each quote as verified only if it really occurs in what the candidate said. */
export function verifyEvidence(
  items: { area?: string; point?: string; quote?: string }[],
  haystacks: string[],
): TierEvidence[] {
  const hay = haystacks.map(norm);
  return items
    .filter((e) => e && typeof e.quote === "string" && e.quote.trim())
    .slice(0, 12)
    .map((e) => {
      const q = norm(e.quote as string);
      return {
        area: String(e.area ?? ""),
        point: String(e.point ?? ""),
        quote: String(e.quote),
        verified: q.length > 2 && hay.some((h) => h.includes(q)),
      };
    });
}

/** Turns the model's raw answer into a safe TierResult, applying the safety guards the client cares about. */
export function finalizeModelTier(
  raw: Record<string, unknown>,
  flow: InterviewFlowState,
  bp: InterviewBlueprint,
  haystacks: string[],
): TierResult {
  const ids = bp.tiers.map((t) => t.id);
  let tier = typeof raw.tier === "string" && ids.includes(raw.tier) ? raw.tier : "needs_review";
  const flags = behaviourFlags(flow);
  let reasoning = typeof raw.reasoning === "string" ? raw.reasoning.trim() : "";
  let method: TierResult["method"] = "model";
  let confidence = Math.min(1, Math.max(0, Number(raw.confidence ?? 0.5)));

  if (tier === "needs_review" && typeof raw.tier !== "string") {
    reasoning = reasoning || "The model did not return a valid classification.";
    confidence = 0;
  }

  const unsafeAreas = Object.values(flow.areas ?? {}).filter((a) => a.outcome === "unsafe");
  if (unsafeAreas.length && TIER_ORDER.slice(0, 2).includes(tier)) {
    flags.push("An answer was marked unsafe, which conflicts with a Tier 1/2 rating");
    reasoning = `${reasoning} (Automatically sent for human review: an answer was marked unsafe.)`.trim();
    tier = "needs_review";
    method = "rule_override";
  }
  if (!reasoning) reasoning = "No reasoning was returned.";

  return {
    tier,
    tier_name: tierName(bp, tier),
    confidence,
    reasoning,
    method,
    evidence: verifyEvidence(Array.isArray(raw.evidence) ? (raw.evidence as never[]) : [], haystacks),
    flags,
  };
}

export function buildClassificationPrompt(params: {
  roleTitle: string;
  candidateName: string;
  bp: InterviewBlueprint;
  flow: InterviewFlowState;
}): string {
  const { bp, flow } = params;
  const tiers = bp.tiers
    .map((t) => `- ${t.id} (${t.name}): ${t.description}\n  Criteria: ${t.criteria.join("; ")}`)
    .join("\n");
  const digest = {
    screening: screeningFacts(flow),
    contradictions: (flow.contradictions ?? []).map((c) => ({
      said_before: c.claim_a,
      said_now: c.claim_b,
      resolved: Boolean(c.resolved),
      resolution: c.resolution ?? "",
    })),
    clinical_areas: summarizeAreas(flow, bp),
    behaviour: {
      outcome: flow.outcome,
      unclear_audio_turns: flow.unclear_total,
      total_turns: flow.turns,
      dont_know_count: flow.dont_know_total,
      nervous_moments: flow.nervous_events,
    },
  };

  return `You are classifying a nursing candidate (${params.candidateName}, applying for ${params.roleTitle}) after a voice interview.
Use ONLY the evidence below. Do not assume anything that is not in it. Candidates speak in many Indian languages and accents; never penalise accent, grammar, code-switching or nervousness.

Tiers:
${tiers}

Evidence (JSON):
${JSON.stringify(digest, null, 1)}

Rules:
- Pick exactly one tier id from the list above.
- If the evidence is too thin or too unclear to be confident, choose needs_review rather than guessing.
- "unsafe" areas and red flags weigh heavily. "unknown" areas (not assessed, or "I don't know") are missing evidence, not proof of weakness.
- Explain your reasoning in 3-5 sentences a recruiter can act on, naming the specific areas and answers behind the decision.
- evidence: up to 6 items, each {area, point (what it shows), quote} where quote is copied verbatim from the evidence above. Do not invent quotes.
- strengths and gaps: short plain-English bullet strings, at most 4 each.
- overall_score: an integer from 1 to 10 consistent with the tier.

Return ONLY JSON: {"tier": "...", "confidence": 0-1, "reasoning": "...", "overall_score": n, "strengths": ["..."], "gaps": ["..."], "evidence": [{"area": "...", "point": "...", "quote": "..."}]}`;
}
