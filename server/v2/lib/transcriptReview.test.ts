import assert from "node:assert/strict";
import { test } from "node:test";
import { turnsForReview } from "./transcriptReview.js";

test("a stored move stays on the candidate line that caused it", () => {
  const turns = turnsForReview(
    [
      { role: "user", text: "I will not do diaper care", timestamp: "t1", move: "persuade" },
      { role: "assistant", text: "It is part of the job. Can you do it?", timestamp: "t2" },
      { role: "user", text: "No", timestamp: "t3", move: "gate_failed" },
    ],
    [],
  );
  assert.deepEqual(
    turns.filter((t) => t.role === "user").map((t) => t.move),
    ["persuade", "gate_failed"],
  );
  assert.equal(turns[1].move, undefined);
});

test("older interviews pick the move from flow.move events in order", () => {
  const turns = turnsForReview(
    [
      { role: "user", text: "I check vitals", timestamp: "t1" },
      { role: "assistant", text: "How often?", timestamp: "t2" },
    ],
    [{ ts: "t1", type: "flow.move", data: { kind: "probe", utterance: "I check vitals" } }],
  );
  assert.equal(turns[0].move, "probe");
});
