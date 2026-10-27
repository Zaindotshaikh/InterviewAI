import { Router } from "express";
import multer from "multer";
import { extractResumeText, ResumeExtractError } from "../lib/resumeExtract.js";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 8 * 1024 * 1024 },
});

function uploadError(err: unknown): string {
  if (err && typeof err === "object" && "code" in err && err.code === "LIMIT_FILE_SIZE") {
    return "Resume must be 8 MB or smaller";
  }
  return err instanceof Error ? err.message : "Upload failed";
}

/**
 * POST /api/resume/parse
 * - multipart: field "resume" (PDF, DOCX, TXT, JPEG, PNG, WebP)
 * - JSON: { "text": "..." } for paste-as-text
 */
router.post("/parse", (req, res) => {
  const isMultipart = Boolean(req.is("multipart/form-data"));

  if (!isMultipart) {
    const text = String((req.body as { text?: string })?.text ?? "").trim();
    if (!text) {
      res.status(400).json({ error: "Upload a resume file or provide resume text" });
      return;
    }
    res.json({ text });
    return;
  }

  upload.single("resume")(req, res, async (err) => {
    if (err) {
      res.status(400).json({ error: uploadError(err) });
      return;
    }

    try {
      if (!req.file) {
        res.status(400).json({ error: "Resume file is required" });
        return;
      }

      const text = await extractResumeText({
        buffer: req.file.buffer,
        originalname: req.file.originalname,
        mimetype: req.file.mimetype,
      });
      res.json({ text });
    } catch (parseErr) {
      if (parseErr instanceof ResumeExtractError) {
        res.status(parseErr.status).json({ error: parseErr.message });
        return;
      }
      console.error("Resume parse error:", parseErr instanceof Error ? parseErr.message : parseErr);
      res.status(500).json({ error: "Failed to parse resume" });
    }
  });
});

export default router;
