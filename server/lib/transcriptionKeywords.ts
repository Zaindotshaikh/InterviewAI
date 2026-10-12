/**
 * Short role/tool terms only. Never pull prose from the resume —
 * that primes ASR to dump CV summaries into live captions.
 */
export function extractTranscriptionKeywords(params: {
  roleTitle: string;
  criteria: string[];
  questions: string[];
  resumeText: string;
}): string[] {
  const found = new Set<string>();

  const add = (raw: string) => {
    const cleaned = raw.replace(/[^\w+#./-]/g, "").trim();
    if (cleaned.length < 2 || cleaned.length > 28) return;
    if (/^\d+$/.test(cleaned)) return;
    if (/^(Results|Driven|Proven|Track|Record|Skilled|Dedicated|Professional|Summary)$/i.test(cleaned)) {
      return;
    }
    found.add(cleaned);
  };

  add(params.roleTitle);
  for (const part of params.roleTitle.split(/[\s,/-]+/)) add(part);

  for (const c of params.criteria) {
    for (const word of c.split(/[\s,/]+/)) {
      if (/^[A-Z]/.test(word) || /[A-Z]{2,}|[+#]|\d/.test(word)) add(word);
    }
  }

  void params.resumeText;
  void params.questions;

  return Array.from(found).slice(0, 12);
}
