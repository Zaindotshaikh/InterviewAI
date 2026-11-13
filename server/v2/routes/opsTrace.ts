import { timingSafeEqual } from "crypto";
import { Router, type NextFunction, type Request, type Response } from "express";
import { readTrace } from "../lib/traceStore.js";

const router = Router();

function requireTraceAccess(req: Request, res: Response, next: NextFunction): void {
  const secret = process.env.TRACE_ACCESS_SECRET?.trim() ?? "";
  const header = req.header("authorization") ?? "";
  const token = header.startsWith("Bearer ") ? header.slice("Bearer ".length) : "";
  if (!secret || token.length !== secret.length) {
    res.status(404).json({ error: "Not found" });
    return;
  }
  const left = Buffer.from(token);
  const right = Buffer.from(secret);
  if (!timingSafeEqual(left, right)) {
    res.status(404).json({ error: "Not found" });
    return;
  }
  next();
}

router.use(requireTraceAccess);

router.get("/:id", async (req, res) => {
  const id = req.params.id;
  if (!/^[A-Za-z0-9-]{8,80}$/.test(id)) {
    res.status(404).json({ error: "Not found" });
    return;
  }
  if (!process.env.DATABASE_URL?.trim()) {
    res.status(503).json({ error: "Trace store is not configured" });
    return;
  }
  try {
    const doc = await readTrace(id);
    if (!doc) {
      res.status(404).json({ error: "Not found" });
      return;
    }
    res.type("application/json").send(`${JSON.stringify(doc, null, 2)}\n`);
  } catch (err) {
    console.error("[trace] read failed:", err instanceof Error ? err.name : "error");
    res.status(500).json({ error: "Failed to read trace" });
  }
});

export default router;
