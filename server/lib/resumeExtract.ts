import zlib from "zlib";
import OpenAI from "openai";
import pdfParse from "pdf-parse";
import mammoth from "mammoth";

const MAX_CHARS = 20_000;
const SPARSE_CHARS_PER_PAGE = 50;

const TRANSCRIBE =
  "Transcribe this entire resume into plain text. Include every column and every section you can see, including profile, contact, skills, experience, education, certifications, and any other heading. Read the left column from top to bottom, then the right column, or top to bottom when there is one column. Do not stop after the first section. Do not add employers, dates, skills, or headings that are not visible. Skip a word only when that word itself is unreadable. If there is no resume text, reply with an empty message.";

export class ResumeExtractError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ResumeExtractError";
  }
}

type Upload = {
  buffer: Buffer;
  originalname: string;
  mimetype: string;
};

function clean(text: string): string {
  const collapsed = text
    .replace(/\u0000/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
  if (collapsed.length <= MAX_CHARS) return collapsed;
  return `${collapsed.slice(0, MAX_CHARS).trim()}\n[Resume text truncated.]`;
}

function startsWith(buffer: Buffer, signature: Buffer): boolean {
  return buffer.length >= signature.length && buffer.subarray(0, signature.length).equals(signature);
}

function extension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

function isWebp(buffer: Buffer): boolean {
  return (
    buffer.length >= 12 &&
    buffer.toString("ascii", 0, 4) === "RIFF" &&
    buffer.toString("ascii", 8, 12) === "WEBP"
  );
}

function isHeic(buffer: Buffer): boolean {
  if (buffer.length < 12 || buffer.toString("ascii", 4, 8) !== "ftyp") return false;
  const brand = buffer.toString("ascii", 8, 12).toLowerCase();
  return ["heic", "heif", "heix", "hevc", "mif1", "msf1"].includes(brand);
}

function isZip(buffer: Buffer): boolean {
  return (
    startsWith(buffer, Buffer.from([0x50, 0x4b, 0x03, 0x04])) ||
    startsWith(buffer, Buffer.from([0x50, 0x4b, 0x05, 0x06])) ||
    startsWith(buffer, Buffer.from([0x50, 0x4b, 0x07, 0x08]))
  );
}

function isDocx(file: Upload): boolean {
  const mime = file.mimetype.toLowerCase();
  return (
    extension(file.originalname) === ".docx" ||
    mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  );
}

function isTxt(file: Upload): boolean {
  const mime = file.mimetype.toLowerCase();
  return extension(file.originalname) === ".txt" || mime === "text/plain";
}

function sparse(text: string, pages: number): boolean {
  const chars = text.replace(/\s/g, "").length;
  return chars < Math.max(1, pages) * SPARSE_CHARS_PER_PAGE;
}

async function transcribe(
  content: OpenAI.Responses.ResponseInputContent[],
): Promise<string> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new ResumeExtractError("OPENAI_API_KEY not configured", 500);
  }

  const openai = new OpenAI({ apiKey });
  const response = await openai.responses.create({
    model: process.env.CHAT_MODEL || "gpt-4o",
    store: false,
    max_output_tokens: 4096,
    input: [
      {
        role: "user",
        content: [{ type: "input_text", text: TRANSCRIBE }, ...content],
      },
    ],
  });

  return clean(response.output_text || "");
}

async function transcribeImage(buffer: Buffer, mime: "image/jpeg" | "image/png" | "image/webp"): Promise<string> {
  return transcribe([
    {
      type: "input_image",
      image_url: `data:${mime};base64,${buffer.toString("base64")}`,
      detail: "high",
    },
  ]);
}

async function transcribePdf(buffer: Buffer): Promise<string> {
  const images = extractEmbeddedJpegs(buffer);
  if (images.length) {
    return transcribe(
      images.map((image) => ({
        type: "input_image" as const,
        image_url: `data:image/jpeg;base64,${image.toString("base64")}`,
        detail: "high" as const,
      })),
    );
  }

  const file: OpenAI.Responses.ResponseInputFile & { detail?: "high" } = {
    type: "input_file",
    filename: "resume.pdf",
    file_data: `data:application/pdf;base64,${buffer.toString("base64")}`,
    detail: "high",
  };
  return transcribe([file]);
}

function matchingDictEnd(latin: string, open: number): number {
  let depth = 0;
  for (let i = open; i < latin.length - 1; i++) {
    if (latin[i] === "<" && latin[i + 1] === "<") {
      depth++;
      i++;
      continue;
    }
    if (latin[i] === ">" && latin[i + 1] === ">") {
      depth--;
      i++;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

function pdfFilters(dict: string): string[] {
  const listed = dict.match(/\/Filter\s*\[([^\]]+)\]/);
  if (listed?.[1]) return [...listed[1].matchAll(/\/([A-Za-z0-9]+)/g)].map((match) => match[1]);
  const single = dict.match(/\/Filter\s*\/([A-Za-z0-9]+)/);
  return single?.[1] ? [single[1]] : [];
}

function streamBytes(pdf: Buffer, latin: string, dictEnd: number): { data: Buffer; next: number } | null {
  const streamAt = latin.indexOf("stream", dictEnd);
  if (streamAt < 0 || streamAt - dictEnd > 16) return null;
  let start = streamAt + "stream".length;
  if (pdf[start] === 0x0d) start++;
  if (pdf[start] === 0x0a) start++;
  const end = latin.indexOf("endstream", start);
  if (end < 0) return null;
  let dataEnd = end;
  if (dataEnd > start && pdf[dataEnd - 1] === 0x0a) dataEnd--;
  if (dataEnd > start && pdf[dataEnd - 1] === 0x0d) dataEnd--;
  return { data: pdf.subarray(start, dataEnd), next: end + "endstream".length };
}

function decodeJpeg(dict: string, raw: Buffer): Buffer | null {
  const filters = pdfFilters(dict);
  if (!filters.includes("DCTDecode")) return null;
  let data = raw;
  for (const filter of [...filters].reverse()) {
    if (filter === "DCTDecode") continue;
    if (filter !== "FlateDecode") return null;
    try {
      data = zlib.inflateSync(data);
    } catch {
      return null;
    }
  }
  if (data.length >= 3 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff) return data;
  return null;
}

/** Full-page resume JPEGs embedded in a PDF. Skips tiny icons. */
function extractEmbeddedJpegs(pdf: Buffer): Buffer[] {
  const latin = pdf.toString("latin1");
  const jpegs: Buffer[] = [];
  let from = 0;
  while (jpegs.length < 6) {
    const sub = latin.indexOf("/Subtype", from);
    if (sub < 0) break;
    if (!latin.slice(sub, sub + 40).replace(/\s+/g, "").startsWith("/Subtype/Image")) {
      from = sub + "/Subtype".length;
      continue;
    }
    let open = latin.lastIndexOf("<<", sub);
    let handled = false;
    while (open >= 0) {
      const end = matchingDictEnd(latin, open);
      if (end > sub) {
        const stream = streamBytes(pdf, latin, end);
        const jpeg = stream ? decodeJpeg(latin.slice(open, end), stream.data) : null;
        if (jpeg && jpeg.length >= 8_000) jpegs.push(jpeg);
        from = stream ? stream.next : end;
        handled = true;
        break;
      }
      open = latin.lastIndexOf("<<", open - 2);
    }
    if (!handled) from = sub + "/Subtype".length;
  }
  return jpegs;
}

async function extractPdf(buffer: Buffer): Promise<string> {
  let layered = "";
  try {
    const parsed = await pdfParse(buffer);
    layered = clean(parsed.text || "");
    if (layered && !sparse(layered, parsed.numpages || 1)) return layered;
  } catch (err) {
    console.error("PDF text layer failed:", err instanceof Error ? err.message : err);
  }

  const transcribed = await transcribePdf(buffer);
  return transcribed || layered;
}

async function extractDocx(buffer: Buffer): Promise<string> {
  const result = await mammoth.extractRawText({ buffer });
  return clean(result.value || "");
}

function extractTxt(buffer: Buffer): string {
  if (buffer.includes(0)) {
    throw new ResumeExtractError("That text file is not readable as plain text", 400);
  }
  return clean(buffer.toString("utf8").replace(/^\uFEFF/, ""));
}

export async function extractResumeText(file: Upload): Promise<string> {
  const buffer = file.buffer;
  if (!buffer.length) {
    throw new ResumeExtractError("Resume file is empty", 400);
  }

  if (isHeic(buffer)) {
    throw new ResumeExtractError("HEIC photos are not supported. Export a JPEG or PNG.", 400);
  }

  if (startsWith(buffer, Buffer.from([0xd0, 0xcf, 0x11, 0xe0]))) {
    throw new ResumeExtractError("Word .doc files are not supported. Save as .docx or PDF.", 400);
  }

  let text = "";
  if (startsWith(buffer, Buffer.from("%PDF"))) {
    text = await extractPdf(buffer);
  } else if (startsWith(buffer, Buffer.from([0x89, 0x50, 0x4e, 0x47]))) {
    text = await transcribeImage(buffer, "image/png");
  } else if (startsWith(buffer, Buffer.from([0xff, 0xd8, 0xff]))) {
    text = await transcribeImage(buffer, "image/jpeg");
  } else if (isWebp(buffer)) {
    text = await transcribeImage(buffer, "image/webp");
  } else if (isZip(buffer) && isDocx(file)) {
    text = await extractDocx(buffer);
  } else if (isTxt(file)) {
    text = extractTxt(buffer);
  } else {
    throw new ResumeExtractError(
      "Upload a PDF, Word (.docx), text file, or a JPEG, PNG, or WebP photo.",
      400,
    );
  }

  if (!text) {
    throw new ResumeExtractError("Could not extract text from this file", 422);
  }
  return text;
}
