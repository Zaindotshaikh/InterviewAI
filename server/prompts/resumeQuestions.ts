import type { CandidateContext } from "../lib/candidateContext.js";
import { formatCandidateDetailsSection } from "../lib/candidateContext.js";
import type { InterviewSeniority } from "./interviewer.js";

export function buildResumeQuestionsPrompt(params: {
  roleTitle: string;
  criteria: string[];
  candidateContext: CandidateContext;
  seniority?: InterviewSeniority;
}): string {
  const criteriaList = params.criteria.map((c) => `- ${c}`).join("\n") || "- Fit for the role";
  const details = formatCandidateDetailsSection(params.candidateContext);
  const seniority = params.seniority ?? "mid";

  const depth =
    seniority === "senior"
      ? `Senior bar: each question should probe judgment, ownership of outcomes, or leading others, still tied to ONE resume fact. Not "tell me about your day."`
      : seniority === "junior"
        ? `Junior bar: each question should be about something they personally did (a task, tool, check, or small project), still tied to ONE resume fact. Not strategy or org design.`
        : `Mid-level bar: each question should be about a piece of work they owned (a problem, process, or result), still tied to ONE resume fact.`;

  return `You are prepping questions for a live spoken interview for the role of ${params.roleTitle} (${seniority} level).
Evaluation criteria:
${criteriaList}

${depth}

Use the candidate details and resume below. Write EXACTLY 3 unique questions. Each question MUST be about a DIFFERENT resume fact (different project, employer moment, metric, skill, or transition). Do not write two questions about the same bullet.

Rules for each question:
- One clear ask only, not compound.
- Short enough to speak aloud in under ~8 seconds (roughly under 25 words).
- Reference ONE concrete resume detail, not a laundry list of metrics/employers/sectors.
- Natural spoken English, not written essay style.
- Calibrated to a ${seniority} ${params.roleTitle} interview.
- FORBIDDEN: generic STAR/behavioral questions with no resume detail (e.g. "tell me about a time you solved a difficult problem", "a major challenge", "your greatest weakness"). Every question must name a specific fact from THIS resume.

Return ONLY valid JSON:
{ "resume_questions": ["...", "...", "..."] }

${details}

## Resume:
${params.candidateContext.resumeText}`;
}
