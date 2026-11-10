import OpenAI from "openai";
import { buildScorecardPrompt } from "../../prompts/scorecard.js";
import { loadBlueprint } from "./blueprint.js";
import {
  buildClassificationPrompt,
  finalizeModelTier,
  precheck,
  screeningFacts,
  summarizeAreas,
  verifyEvidence,
  type TierResult,
} from "./classification.js";
import type { InterviewFlowState } from "./types.js";
import { getV2Interview, saveEnglishTranscript, saveV2Summary } from "./v2Store.js";

type V2Record = NonNullable<Awaited<ReturnType<typeof getV2Interview>>>;

export class ScorecardError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/**
 * What would change the hiring decision. A new goodbye line does not, so a score
 * started during the call can be reused when the session ends.
 */
export function flowFingerprint(flow: InterviewFlowState | undefined): string {
  if (!flow) return "no-flow";
  const slots = Object.entries(flow.slots ?? {})
    .map(([k, v]) => `${k}:${v.status}:${String(v.value ?? "")}`)
    .sort()
    .join("|");
  const areas = Object.entries(flow.areas ?? {})
    .map(([k, a]) => `${k}:${a.status}:${a.outcome}:${a.evidence?.length ?? 0}:${(a.red_flags ?? []).join(",")}`)
    .sort()
    .join("|");
  const care = Object.entries(flow.care ?? {})
    .map(([k, c]) => `${k}:${c.stance}:${c.persuasions}`)
    .sort()
    .join("|");
  const contradictions = (flow.contradictions ?? [])
    .map((c) => `${c.resolved ? 1 : 0}:${c.claim_a ?? ""}:${c.claim_b ?? ""}`)
    .join("|");
  return [
    flow.outcome ?? "",
    flow.gate_failed ?? "",
    flow.experience_level ?? "",
    flow.unclear_total ?? 0,
    flow.dont_know_total ?? 0,
    slots,
    areas,
    care,
    contradictions,
  ].join("~");
}

/** Start a model score once there is something to judge. Screening-only chatter waits. */
export function worthPrefetch(flow: InterviewFlowState | undefined, completed: boolean): boolean {
  if (!flow || (flow.turns ?? 0) < 3) return false;
  if (completed || flow.outcome) return true;
  if (flow.stage === "closing" || flow.stage === "ended") return true;
  if (flow.stage !== "clinical") return false;
  return Object.values(flow.areas ?? {}).some((a) => a.status === "done" || (a.evidence?.length ?? 0) > 0);
}

type CachedModel = { fp: string; model: Record<string, unknown> };

const models = new Map<string, CachedModel>();
const inflight = new Map<string, { fp: string; promise: Promise<Record<string, unknown> | null> }>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();

function openaiClient(): OpenAI | null {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) return null;
  return new OpenAI({ apiKey });
}

/** Coalesce the agent's rapid state saves into one scoring pass. */
export function scheduleScorecardPrep(id: string, delayMs = 2000): void {
  const prev = timers.get(id);
  if (prev) clearTimeout(prev);
  const timer = setTimeout(() => {
    timers.delete(id);
    void prefetch(id);
  }, delayMs);
  timer.unref?.();
  timers.set(id, timer);
}

async function prefetch(id: string): Promise<void> {
  if (!openaiClient()) return;
  const record = await getV2Interview(id);
  if (!record) return;
  const flow = record.extras.controller.flow;
  if (!record.extras.plan || record.extras.plan.version < 2) return;
  if (!worthPrefetch(flow, record.extras.controller.completed)) return;
  const bp = record.extras.plan.blueprint ?? (await loadBlueprint());
  if (precheck(flow, bp)) return;
  const fp = flowFingerprint(flow);
  if (models.get(id)?.fp === fp) return;
  try {
    await classify(id, fp);
  } catch (err) {
    console.error("[v2] scorecard prefetch failed:", err);
  }
}

function classify(id: string, fp: string): Promise<Record<string, unknown> | null> {
  const existing = inflight.get(id);
  if (existing?.fp === fp) return existing.promise;
  const promise = classifyUncached(id, fp);
  inflight.set(id, { fp, promise });
  void promise.finally(() => {
    if (inflight.get(id)?.promise === promise) inflight.delete(id);
  });
  return promise;
}

async function classifyUncached(id: string, fp: string): Promise<Record<string, unknown> | null> {
  const openai = openaiClient();
  const record = await getV2Interview(id);
  if (!openai || !record?.extras.controller.flow || record.extras.plan.version < 2) return null;
  if (flowFingerprint(record.extras.controller.flow) !== fp) return null;
  const bp = record.extras.plan.blueprint ?? (await loadBlueprint());
  const completion = await openai.chat.completions.create({
    model: process.env.CLASSIFIER_MODEL || process.env.CHAT_MODEL || "gpt-4o",
    temperature: 0.1,
    response_format: { type: "json_object" },
    messages: [
      {
        role: "system",
        content:
          "You classify nursing candidates for a hiring team from interview evidence. Return ONLY valid JSON matching the requested schema.",
      },
      {
        role: "user",
        content: buildClassificationPrompt({
          roleTitle: record.interview.roleTitle,
          candidateName: record.interview.candidateName,
          bp,
          flow: record.extras.controller.flow,
        }),
      },
    ],
  });
  const model = JSON.parse(completion.choices[0]?.message?.content ?? "{}") as Record<string, unknown>;
  const fresh = await getV2Interview(id);
  if (!fresh?.extras.controller.flow || flowFingerprint(fresh.extras.controller.flow) !== fp) return null;
  models.set(id, { fp, model });
  return model;
}

function assemble(
  record: V2Record,
  tier: TierResult,
  model: Record<string, unknown>,
): Record<string, unknown> {
  const flow = record.extras.controller.flow!;
  const bp = record.extras.plan.blueprint!;
  const haystacks = record.interview.transcript.map((t) => t.text);
  const areas = summarizeAreas(flow, bp).map((a) => ({
    ...a,
    evidence: a.evidence.map((e) => {
      const quote = e.quote ?? "";
      const ok = quote
        ? verifyEvidence([{ area: a.title, point: e.quality, quote }], haystacks)[0]?.verified === true
        : false;
      return { ...e, quote: ok ? quote : "" };
    }),
  }));
  // Quotes are checked against the spoken transcript, including lines saved after the draft.
  const used = tier.method === "rule" ? tier : finalizeModelTier(model, flow, bp, haystacks);
  const scoreByTier: Record<string, number | null> = {
    tier_1: 9,
    tier_2: 7,
    tier_3: 5,
    not_eligible: 2,
    needs_review: null,
  };
  const modelScore = Number(model.overall_score);
  const strList = (v: unknown) => (Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : []);
  return {
    overall_score:
      used.method === "model" && Number.isFinite(modelScore)
        ? Math.min(10, Math.max(1, Math.round(modelScore)))
        : (scoreByTier[used.tier] ?? null),
    recommendation: `${used.tier_name}. ${used.reasoning}`,
    strengths: used.method === "rule" ? [] : strList(model.strengths),
    gaps: used.method === "rule" ? [] : strList(model.gaps),
    per_question_notes: areas.map((a) => ({
      question: a.title,
      note: `${a.outcome}${a.evidence.length ? `. ${a.evidence.map((e) => e.summary).filter(Boolean).join(" ")}` : ""}`,
    })),
    tier: used.tier,
    tier_name: used.tier_name,
    tier_confidence: used.confidence,
    tier_reasoning: used.reasoning,
    tier_method: used.method,
    tier_evidence: used.evidence.filter((e) => e.verified),
    flags: used.flags,
    screening: screeningFacts(flow),
    clinical_areas: areas,
    contradictions: flow.contradictions ?? [],
    outcome: flow.outcome,
    profile: {
      gender: record.interview.candidateContext?.gender ?? null,
    },
    pipeline: "v2",
    language: record.extras.language,
    integrity: record.interview.integrity ?? { available: false, events: [] },
  };
}

async function scoringTranscript(record: V2Record): Promise<V2Record["interview"]["transcript"]> {
  if (record.extras.language === "en-IN") return record.interview.transcript;
  const openai = openaiClient();
  if (!openai) return record.interview.transcript;
  const cached = record.extras.englishTranscript ?? [];
  if (cached.length === record.interview.transcript.length) {
    return cached.map((t) => ({ ...t }));
  }
  const completion = await openai.chat.completions.create({
    model: process.env.CHAT_MODEL || "gpt-4o",
    temperature: 0.2,
    response_format: { type: "json_object" },
    messages: [
      {
        role: "system",
        content:
          "Translate interview turns to clear English for a hiring scorecard. Preserve meaning. Return JSON { turns: [{ role, text, timestamp }] }.",
      },
      {
        role: "user",
        content: JSON.stringify({
          sourceLanguage: record.extras.language,
          turns: record.interview.transcript,
        }),
      },
    ],
  });
  const raw = completion.choices[0]?.message?.content ?? "{}";
  const parsed = JSON.parse(raw) as {
    turns?: { role: "user" | "assistant"; text: string; timestamp: string }[];
  };
  if (Array.isArray(parsed.turns) && parsed.turns.length) {
    await saveEnglishTranscript(record.interview.id, parsed.turns);
    return parsed.turns.map((t) => ({ ...t }));
  }
  return record.interview.transcript;
}

/** Finish the scorecard. A draft started mid-interview is reused when the call has not changed. */
export async function resolveScorecard(id: string): Promise<Record<string, unknown>> {
  if (!openaiClient()) {
    throw new ScorecardError(500, "OPENAI_API_KEY not configured");
  }
  const record = await getV2Interview(id);
  if (!record) throw new ScorecardError(404, "Interview not found");
  const transcript = record.interview.transcript;
  if (!transcript.length) throw new ScorecardError(400, "No transcript available to score");

  const flow = record.extras.controller.flow;
  if (flow && record.extras.plan.version >= 2) {
    const bp = record.extras.plan.blueprint ?? (await loadBlueprint());
    const withBlueprint = {
      ...record,
      extras: { ...record.extras, plan: { ...record.extras.plan, blueprint: bp } },
    };
    const ruled = precheck(flow, bp);
    if (ruled) {
      const payload = assemble(withBlueprint, ruled, {});
      await saveV2Summary(id, payload);
      return payload;
    }
    const fp = flowFingerprint(flow);
    const cached = models.get(id);
    let model = cached?.fp === fp ? cached.model : null;
    if (!model) {
      const flying = inflight.get(id);
      model = flying?.fp === fp ? await flying.promise : await classify(id, fp);
    }
    const fresh = await getV2Interview(id);
    const freshFlow = fresh?.extras.controller.flow;
    const freshFp = flowFingerprint(freshFlow);
    if (fresh && freshFlow && freshFp !== fp) {
      const ruledNow = precheck(freshFlow, bp);
      if (ruledNow) {
        const payload = assemble(
          { ...fresh, extras: { ...fresh.extras, plan: { ...fresh.extras.plan, blueprint: bp } } },
          ruledNow,
          {},
        );
        await saveV2Summary(id, payload);
        return payload;
      }
      model = models.get(id)?.fp === freshFp ? models.get(id)!.model : await classify(id, freshFp);
      const payload = assemble(
        { ...fresh, extras: { ...fresh.extras, plan: { ...fresh.extras.plan, blueprint: bp } } },
        {
          tier: "needs_review",
          tier_name: "Needs review",
          confidence: 0,
          reasoning: "",
          method: "model",
          evidence: [],
          flags: [],
        },
        model ?? {},
      );
      await saveV2Summary(id, payload);
      return payload;
    }
    const payload = assemble(withBlueprint, {
      tier: "needs_review",
      tier_name: "Needs review",
      confidence: 0,
      reasoning: "",
      method: "model",
      evidence: [],
      flags: [],
    }, model ?? {});
    await saveV2Summary(id, payload);
    return payload;
  }

  const openai = openaiClient()!;
  const scoring = await scoringTranscript(record);
  const prompt = buildScorecardPrompt({
    roleTitle: record.interview.roleTitle,
    candidateName: record.interview.candidateName,
    criteria: record.interview.criteria,
    transcript: scoring,
  });
  const completion = await openai.chat.completions.create({
    model: process.env.CHAT_MODEL || "gpt-4o",
    temperature: 0.3,
    response_format: { type: "json_object" },
    messages: [
      {
        role: "system",
        content: "You score completed job interviews. Return ONLY valid JSON matching the requested schema.",
      },
      { role: "user", content: prompt },
    ],
  });
  const summary = JSON.parse(completion.choices[0]?.message?.content ?? "{}") as Record<string, unknown>;
  const payload = {
    ...summary,
    pipeline: "v2",
    language: record.extras.language,
    integrity: record.interview.integrity ?? { available: false, events: [] },
  };
  await saveV2Summary(id, payload);
  return payload;
}
