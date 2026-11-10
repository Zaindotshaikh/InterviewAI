import assert from "node:assert/strict";
import { test } from "node:test";
import { flowFingerprint, worthPrefetch } from "./scorecardPrep.js";
import type { InterviewFlowState } from "./types.js";

function flow(over: Partial<InterviewFlowState> = {}): InterviewFlowState {
  return {
    stage: "clinical",
    language: "hi-IN",
    turns: 8,
    elapsed_s: 200,
    slots: { city: { value: "Pune", status: "confirmed" } },
    care: { diaper_care: { stance: "comfortable", persuasions: 0 } },
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
    outcome: null,
    ...over,
  };
}

test("moving from the clinical round into the goodbye does not change the score fingerprint", () => {
  const during = flow({ stage: "clinical", turns: 12 });
  const goodbye = flow({ stage: "closing", turns: 14 });
  assert.equal(flowFingerprint(during), flowFingerprint(goodbye));
});

test("a new clinical result does change the fingerprint", () => {
  const before = flow();
  const after = flow({
    areas: {
      meds: {
        area_id: "meds",
        level: 1,
        status: "done",
        outcome: "adequate",
        covered: [],
        missing: [],
        red_flags: [],
        dont_knows: 0,
        evidence: [{ turn: 4, level: 1, quality: "partial", quote: "five rights", summary: "names checks" }],
      },
    },
  });
  assert.notEqual(flowFingerprint(before), flowFingerprint(after));
});

test("prefetch waits until there is clinical evidence or the call is ending", () => {
  assert.equal(worthPrefetch(flow({ stage: "screening", turns: 2 }), false), false);
  assert.equal(worthPrefetch(flow({ stage: "screening", turns: 6 }), false), false);
  assert.equal(worthPrefetch(flow({ stage: "closing", turns: 6 }), false), true);
  assert.equal(worthPrefetch(flow({ stage: "clinical", turns: 6 }), false), false);
  assert.equal(
    worthPrefetch(
      flow({
        areas: {
          meds: {
            area_id: "meds",
            level: 1,
            status: "done",
            outcome: "strong",
            covered: [],
            missing: [],
            red_flags: [],
            dont_knows: 0,
            evidence: [],
          },
        },
      }),
      false,
    ),
    true,
  );
});
