import { Router } from "express";
import multer from "multer";
import pdfParse from "pdf-parse";

const router = Router();
const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 8 * 1024 * 1024 },
  fileFilter: (_req, file, cb) => {
    if (file.mimetype === "application/pdf" || file.originalname.toLowerCase().endsWith(".pdf")) {
      cb(null, true);
      return;
    }
    cb(new Error("Only PDF files are supported"));
  },
});

async function extractPdfText(buffer: Buffer): Promise<string> {
  const parsed = await pdfParse(buffer);
  return (parsed.text || "").replace(/\s+\n/g, "\n").trim();
}

/**
 * POST /api/resume/parse
 * - multipart: field "resume" (PDF)
 * - JSON: { "text": "..." } for paste-as-text
 */
router.post("/parse", (req, res) => {
  const isMultipart = Boolean(req.is("multipart/form-data"));

  if (!isMultipart) {
    const text = String((req.body as { text?: string })?.text ?? "").trim();
    if (!text) {
      res.status(400).json({ error: "Upload a PDF or provide resume text" });
      return;
    }
    res.json({ text });
    return;
  }

  upload.single("resume")(req, res, async (err) => {
    if (err) {
      res.status(400).json({ error: err.message || "Upload failed" });
      return;
    }

    try {
      if (!req.file) {
        res.status(400).json({ error: "PDF file is required" });
        return;
      }

      const text = await extractPdfText(req.file.buffer);
      if (!text) {
        res.status(422).json({ error: "Could not extract text from PDF" });
        return;
      }
      res.json({ text });
    } catch (parseErr) {
      console.error("Resume parse error:", parseErr);
      res.status(500).json({ error: "Failed to parse resume" });
    }
  });
});

export default router;
