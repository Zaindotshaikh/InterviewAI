import dotenv from "dotenv";
import express from "express";
import cors from "cors";
import { existsSync } from "fs";
import path from "path";
import { fileURLToPath } from "url";
import sessionRouter from "./routes/session.js";
import interviewRouter from "./routes/interview.js";
import transcriptRouter from "./routes/transcript.js";
import debugRouter from "./routes/debug.js";
import summaryRouter from "./routes/summary.js";
import resumeRouter from "./routes/resume.js";
import candidatesRouter from "./routes/candidates.js";
import demoRouter from "./routes/demo.js";
import interviewV2Router from "./v2/routes/interviewV2.js";
import internalV2Router from "./v2/routes/internalV2.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
dotenv.config({ path: path.join(__dirname, ".env") });

const app = express();
const PORT = Number(process.env.PORT) || 3001;

app.set("trust proxy", 1);
app.use(
  cors({
    origin: process.env.CLIENT_ORIGIN
      ? process.env.CLIENT_ORIGIN.split(",").map((s) => s.trim())
      : true,
  }),
);
app.use(express.json({ limit: "5mb" }));

app.get("/api/health", (_req, res) => {
  res.json({ ok: true, hasKey: Boolean(process.env.OPENAI_API_KEY) });
});

app.use("/api/session", sessionRouter);
app.use("/api/resume", resumeRouter);
app.use("/api/candidates", candidatesRouter);
app.use("/api/demo", demoRouter);
app.use("/api/interview", interviewRouter);
app.use("/api/interview", transcriptRouter);
app.use("/api/interview", debugRouter);
app.use("/api/interview", summaryRouter);

// Parallel Indic voice pipeline (does not replace existing /api/interview routes)
app.use("/api/v2/interview", interviewV2Router);
app.use("/api/v2/internal", internalV2Router);

app.get("/api/roles", async (_req, res) => {
  try {
    const { readFile } = await import("fs/promises");
    const rolesPath = path.join(__dirname, "config", "roles.json");
    const raw = await readFile(rolesPath, "utf-8");
    res.json(JSON.parse(raw));
  } catch (err) {
    console.error("Failed to load roles:", err);
    res.status(500).json({ error: "Failed to load roles" });
  }
});

const clientDist = path.join(__dirname, "..", "client", "dist");
if (existsSync(clientDist)) {
  app.use(express.static(clientDist));
  app.get(/^(?!\/api).*/, (_req, res) => {
    res.sendFile(path.join(clientDist, "index.html"));
  });
}

app.listen(PORT, "0.0.0.0", () => {
  console.log(`InterviewAI server listening on http://0.0.0.0:${PORT}`);
  if (!process.env.OPENAI_API_KEY) {
    console.warn("WARNING: OPENAI_API_KEY is not set");
  }
});
