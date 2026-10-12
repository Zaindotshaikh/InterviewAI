import { Router } from "express";
import { appendDebugEvents } from "../lib/debugLog.js";

const router = Router();

/** Client realtime diagnostics. Written to server/data/<id>.debug.jsonl */
router.post("/:id/debug", async (req, res) => {
  try {
    const events = Array.isArray(req.body?.events) ? req.body.events : [];
    if (!events.length) {
      res.json({ ok: true, wrote: 0 });
      return;
    }
    await appendDebugEvents(req.params.id, events.slice(0, 80));
    res.json({ ok: true, wrote: Math.min(events.length, 80) });
  } catch (err) {
    console.error("Debug log error:", err);
    res.status(500).json({ error: "Failed to write debug log" });
  }
});

export default router;
