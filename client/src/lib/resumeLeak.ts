/**
 * Detect resume / CV text leaking into live captions (ASR hallucination
 * or the model reciting the uploaded document).
 */

const CV_PHRASES = [
  /e?sults[-\s]?driven/i,
  /proven track record/i,
  /cross-functional collaboration/i,
  /data-informed decision/i,
  /exceptional customer service/i,
  /dedicated to delivering/i,
  /highly motivated professional/i,
  /seeking a challenging/i,
  /demonstrated ability to/i,
  /adept at (managing|leveraging|leading)/i,
  /strong expertise in/i,
  /professional summary/i,
  /core competencies/i,
  /omni-channel support/i,
  /client retention strategies/i,
  /managing and leading teams/i,
];

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function hasFirstPerson(text: string): boolean {
  return /\b(i|i'm|i’ve|i've|i'd|i’d|me|my|we|we're|we've)\b/i.test(text);
}

/** CV-boilerplate prose that people almost never say out loud. */
export function isResumeProse(text: string): boolean {
  const t = text.trim();
  if (t.length < 50) return false;
  if (/PROFESSIONAL SUMMARY|WORK EXPERIENCE|EMPLOYMENT HISTORY|CURRICULUM VITAE/i.test(t)) {
    return true;
  }
  if (/(^|\n)\s*(EDUCATION|SKILLS|EXPERIENCE|SUMMARY|CORE COMPETENCIES)\s*(\n|:)/.test(t)) {
    return true;
  }

  const hits = CV_PHRASES.filter((re) => re.test(t)).length;
  if (hits >= 2) return true;
  if (hits >= 1 && t.length > 90 && !hasFirstPerson(t)) return true;
  if (
    /\b(skilled in|proficient in|experienced in|adept at)\b/i.test(t) &&
    !hasFirstPerson(t) &&
    t.length > 70
  ) {
    return true;
  }
  return false;
}

function resumeOverlap(caption: string, resume: string): number {
  const cap = normalize(caption);
  const res = normalize(resume);
  if (cap.length < 40 || res.length < 40) return 0;
  if (res.includes(cap)) return 1;

  const words = cap.split(" ").filter(Boolean);
  const windowSize = Math.min(8, words.length);
  if (windowSize < 6) return res.includes(cap) ? 1 : 0;

  let hits = 0;
  let windows = 0;
  for (let i = 0; i <= words.length - windowSize; i++) {
    windows += 1;
    const phrase = words.slice(i, i + windowSize).join(" ");
    if (res.includes(phrase)) hits += 1;
  }
  return windows ? hits / windows : 0;
}

/**
 * True when `text` is uploaded-resume leakage, not live speech.
 * Assistant questions that mention resume facts (and end in ?) are kept.
 */
export function isResumeLeak(
  text: string,
  resumeText?: string,
  role?: "user" | "assistant",
): boolean {
  const t = text.trim();
  if (!t) return false;
  if (isResumeProse(t)) return true;
  if (role === "assistant" && /[?]/.test(t)) return false;
  if (!resumeText?.trim()) return false;

  const overlap = resumeOverlap(t, resumeText);
  if (overlap >= 0.8) return true;
  if (overlap >= 0.5 && !hasFirstPerson(t)) return true;
  return false;
}
