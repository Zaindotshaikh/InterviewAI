import assert from "node:assert/strict";
import { test } from "node:test";
import { loadBlueprint, blueprintTargetMinutes } from "./blueprint.js";
import { finalizeModelTier, precheck, summarizeAreas, verifyEvidence } from "./classification.js";
import type { InterviewFlowState } from "./types.js";

function flow(over: Partial<InterviewFlowState> = {}): InterviewFlowState {
  return {
    stage: "ended",
    language: "hi-IN",
    turns: 20,
    elapsed_s: 900,
    slots: { city: { value: "Pune", status: "captured" } },
    care: {},
    gate_failed: null,
    experience_level: "experienced",
    areas: {},
    area_order: [],
    contradictions: [],
    unclear_total: 0,
    dont_know_total: 0,
    repeat_requests: 0,
    nervous_events: 0,
    interruptions: 0,
    outcome: "completed",
    ...over,
  };
}

const area = (outcome: string, extra = {}) => ({
  area_id: "vitals_monitoring",
  level: 2,
  status: "done",
  outcome,
  covered: ["vm1_bp"],
  missing: [],
  red_flags: [],
  dont_knows: 0,
  evidence: [{ turn: 3, level: 1, quality: "correct", quote: "BP one twenty over eighty", summary: "Knows BP range" }],
  ...extra,
});

test("blueprint loads and has the tiers the rules rely on", async () => {
  const bp = await loadBlueprint();
  const ids = bp.tiers.map((t) => t.id);
  for (const id of ["tier_1", "tier_2", "tier_3", "not_eligible", "needs_review"]) assert.ok(ids.includes(id));
  assert.ok(blueprintTargetMinutes(bp) <= bp.limits.hard_cap_minutes);
});

test("refusing diaper care is not eligible without calling the model", async () => {
  const bp = await loadBlueprint();
  const r = precheck(
    flow({
      stage: "ended",
      outcome: "screened_out",
      gate_failed: "diaper_care",
      care: { diaper_care: { stance: "refuses", persuasions: 2, reason: "feels it is not nursing work" } },
    }),
    bp,
  );
  assert.equal(r?.tier, "not_eligible");
  assert.equal(r?.method, "rule");
  assert.match(r?.reasoning ?? "", /diaper care/);
});

test("early end or poor audio goes to human review", async () => {
  const bp = await loadBlueprint();
  assert.equal(precheck(flow({ outcome: "incomplete_silence", stage: "ended", turns: 5 }), bp)?.tier, "needs_review");
  assert.equal(precheck(flow({ unclear_total: 15 }), bp)?.tier, "needs_review");
  assert.equal(precheck(undefined, bp)?.tier, "needs_review");
});

test("a normal completed interview is left for the model", async () => {
  const bp = await loadBlueprint();
  const f = flow({ areas: { vitals_monitoring: area("strong"), medication_safety: area("adequate") } });
  assert.equal(precheck(f, bp), null);
});

test("model tier is validated and unsafe answers block tier 1/2", async () => {
  const bp = await loadBlueprint();
  const f = flow({ areas: { vitals_monitoring: area("unsafe") } });
  const r = finalizeModelTier({ tier: "tier_1", confidence: 0.9, reasoning: "Strong." }, f, bp, []);
  assert.equal(r.tier, "needs_review");
  assert.equal(r.method, "rule_override");

  const bad = finalizeModelTier({ tier: "platinum" }, flow(), bp, []);
  assert.equal(bad.tier, "needs_review");
});

test("evidence quotes are only verified when the candidate really said them", () => {
  const out = verifyEvidence(
    [
      { area: "a", point: "p", quote: "BP one twenty over eighty" },
      { area: "a", point: "p", quote: "I have ten years in ICU" },
    ],
    ["Haan, BP one twenty over eighty hota hai."],
  );
  assert.deepEqual(
    out.map((e) => e.verified),
    [true, false],
  );
});

test("area summaries show key point wording, not ids", async () => {
  const bp = await loadBlueprint();
  const [a] = summarizeAreas(flow({ area_order: ["vitals_monitoring"], areas: { vitals_monitoring: area("strong") } }), bp);
  assert.match(a.covered[0], /BP/);
});
