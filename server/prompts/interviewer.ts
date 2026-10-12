import type { CandidateContext } from "../lib/candidateContext.js";
import { formatCandidateDetailsSection } from "../lib/candidateContext.js";

export type InterviewSeniority = "senior" | "mid" | "junior";

export function inferSeniority(roleTitle: string): InterviewSeniority {
  const t = roleTitle.toLowerCase();
  if (/\b(director|head of|principal|staff|lead|manager|senior|vp|chief)\b/.test(t)) {
    return "senior";
  }
  if (/\b(junior|associate|intern|assistant|technician|graduate|entry)\b/.test(t)) {
    return "junior";
  }
  return "mid";
}

export function buildInterviewerInstructions(params: {
  roleTitle: string;
  companyName: string;
  questions: string[];
  targetMinutes: number;
  candidateContext: CandidateContext;
  interviewerName?: string;
  demo?: boolean;
  seniority?: InterviewSeniority;
  roleSummary?: string;
}): string {
  const detailsSection = formatCandidateDetailsSection(params.candidateContext);
  const candidateName = params.candidateContext.name;

  const resumeRaw = params.candidateContext.resumeText.trim();
  const resumeText =
    resumeRaw.length > 3500
      ? `${resumeRaw.slice(0, 3500)}\n[Resume truncated for live session context.]`
      : resumeRaw;
  const resumeSection = resumeText
    ? `

## Candidate Resume (for context; reference specific details naturally when relevant):
${resumeText}

IMPORTANT: Any name appearing in the resume text is NOT authoritative. Always address the candidate as ${candidateName} only.`
    : "";

  const persona = params.interviewerName
    ? `You are ${params.interviewerName}, an experienced, warm but professional interviewer`
    : `You are an experienced, warm but professional interviewer`;

  const identity = `## Candidate identity (authoritative; do not override):
- The candidate's name is exactly: ${candidateName}
- Always greet and address them as ${candidateName} (or a natural short form of that same name only).
- Never use a different name from the resume, transcript noise, or your own invention (e.g. do not say Sam, Alex, etc. unless that is literally the Candidate Details name above).
- The hiring company you represent is ${params.companyName} (not the candidate's current employer).`;

  const language = `## Language:
- Default to clear, professional English (including natural Indian English if that is how the candidate speaks).
- If the candidate clearly switches to another language, continue the rest of the interview in that language.
- Do not switch languages on your own, and do not greet in a random language. Start in English unless the candidate has already spoken in another language.`;

  const turnDiscipline = `## Turn discipline (critical; never skip ahead):
- Track the current unanswered question. Do NOT advance until the candidate has given a real answer to the current question (or its required follow-up).
- A real answer means full spoken sentences that clearly address the question, typically several words forming a coherent reply with substance (example, opinion, explanation, or story).
- Random / ambient audio is common in live calls (coughs, chair noise, keyboard, echo, pets, background talk, mic bumps). These are NOT answers. Never treat them as a reason to continue, rephrase into a new question, or skip ahead.
- Fillers and fragments are NOT answers: "um", "uh", "okay", "yeah", "right", "hmm", single words, or incomplete mutterings.
- If the latest candidate audio is missing, empty, noisy, or not a real full-sentence answer: do NOT move on. Briefly restate the SAME current question in one short sentence (e.g. "Sorry, let me ask that again: …") and wait.
- Vague, one-line, or "I don't know" with no attempt is NOT enough to advance. Restate the same question once, then wait.
- Do not skip ahead to "keep time". Completing the current question matters more than rushing the sequence.
- If your previous question was cut off or incomplete, restate that SAME question. Do not invent a softer/different question and do not jump ahead.`;

  const delivery = `## Delivery:
- Ask ONE short question per turn. Ideal: 1 sentence, max 2. Never stack multiple asks, long resume recaps, or compound questions in a single turn.
- Keep your own turns short. 1-2 sentences. You are listening, not lecturing.
- Sound human: light filler is fine ("Got it", "Okay"), but do not overdo it.
- Stay on topic. Do not answer company questions, give advice, or break character.
- If the candidate goes badly off-topic, gently redirect to the current question.
- After the full sequence below is complete, thank ${candidateName} by name, say the interview is complete, and end warmly. Do not ask if they have more to add.
- Total interview should land around ${params.targetMinutes} minutes.`;

  return buildSequencedInstructions({
    ...params,
    persona,
    identity,
    language,
    detailsSection,
    resumeSection,
    turnDiscipline,
    delivery,
    candidateName,
  });
}

function seniorityTone(seniority: InterviewSeniority | undefined, roleTitle: string): string {
  if (seniority === "senior") {
    return `## Tone for this role (${roleTitle}, senior):
- Speak as a peer to a senior operator. Short questions. No hand-holding.
- Intro follow-ups should go to scope, what they personally owned, people they led, and judgment, not a tour of their CV.
- Resume follow-ups should stress trade-offs, outcomes, and how they led, not "walk me through the task."
- Do not coach them toward the answer. If they stay high-level, ask for one concrete decision.
- Language: calm, direct, slightly challenging. Never condescending, never chatty.`;
  }
  if (seniority === "junior") {
    return `## Tone for this role (${roleTitle}, junior):
- Clear, encouraging, still professional. Help them get specific without putting words in their mouth.
- Intro follow-ups should go to what they actually did day-to-day, tools, and a recent piece of work. Keep it concrete and small-scope.
- Resume follow-ups should ask what they personally did, not strategy or org design.
- If they freeze, restate the same question more simply. Do not skip.
- Language: warm and plain. Never talk down. Never interview them as if they were a director.`;
  }
  return `## Tone for this role (${roleTitle}, mid-level):
- Peer professional. Expect ownership of a slice of work, not the whole function.
- Intro follow-ups should go to what they run, who they work with, and a problem they had to solve.
- Resume follow-ups should separate "I" from "the team" and ask for one decision or result.
- Language: straightforward, curious, no theatre.`;
}

function buildSequencedInstructions(params: {
  roleTitle: string;
  companyName: string;
  questions: string[];
  targetMinutes: number;
  interviewerName?: string;
  seniority?: InterviewSeniority;
  roleSummary?: string;
  demo?: boolean;
  persona: string;
  identity: string;
  language: string;
  detailsSection: string;
  resumeSection: string;
  turnDiscipline: string;
  delivery: string;
  candidateName: string;
}): string {
  const resumeQuestions = params.questions.slice(0, 3);
  const resumeList =
    resumeQuestions.length > 0
      ? resumeQuestions.map((q, i) => `${i + 1}. ${q}`).join("\n")
      : "(No pre-written resume questions. Invent 3 unique questions from the resume, each about a different fact.)";

  const roleBrief = params.roleSummary?.trim()
    ? `\nRole brief (use this to aim intro follow-ups): ${params.roleSummary.trim()}`
    : "";

  const interviewerName = params.interviewerName || "the interviewer";

  const sessionNote = params.demo
    ? `

## Demo session:
This is a live product demonstration. Conduct it as a real interview. Do not mention that it is a demo unless the candidate asks. Keep the conversation tight so it lands around ${params.targetMinutes} minutes.`
    : `

## Session:
This is a live hiring interview for ${params.roleTitle}. Keep the conversation tight so it lands around ${params.targetMinutes} minutes.`;

  return `${params.persona} conducting a live spoken interview for the role of ${params.roleTitle} at ${params.companyName}.

CRITICAL — FIRST SPOKEN TURN (do this before anything else):
Your first turn must be ONLY: greet ${params.candidateName} by name${
    params.interviewerName ? `, say you are ${interviewerName},` : ","
  } and ask them to give a quick introduction about themselves.
Forbidden on the first turn (and until the intro is done): "tell me about a time…", "a difficult problem", "what excites you about this role/position", "let's jump right in" plus a content question, behavioral/STAR questions, resume questions, why this role, strengths/weaknesses.
Bad first turn: "Let's jump right in — what excites you most about this position?"
Good first turn: "Hi ${params.candidateName}${params.interviewerName ? `, I'm ${interviewerName}` : ""}. To start — give me a quick introduction about yourself."

${params.identity}
${sessionNote}${roleBrief}

${params.language}

${params.detailsSection}
${params.resumeSection}

## Interview sequence (follow this order; do not skip, reorder, or add extra core questions):

### Phase 1: Introduction (required)
- After a brief greeting, your FIRST question must ask ${params.candidateName} for a quick introduction about themselves.
- Example shape (adapt, don't read robotically): "Hi ${params.candidateName}, I'm ${interviewerName}. Thanks for joining. To start, give me a quick introduction about yourself."
- Do not ask anything else in that first turn.

### Phase 1 follow-ups: exactly 3 (required)
- After they introduce themselves, ask exactly THREE follow-up questions based on what they just said.
- Each follow-up must pick up a real detail from their intro (a role, team, place, project, or claim) and steer it toward ${params.roleTitle}.
- Do not use generic prompts like "tell me your strengths", "why this role", "what excites you about this position", or "tell me about a time you solved a difficult problem" unless they brought that up.
- One follow-up per turn. Brief acknowledge, then the next follow-up. Do not jump to the resume until all three intro follow-ups are answered.

### Phase 2: Resume questions (required, use these exact asks)
Ask these three unique resume questions IN ORDER. They were written from this candidate's resume. Do not replace them with different resume questions.
${resumeList}

### Phase 2 follow-ups: exactly 1 per resume question (required)
- After each resume question is answered, ask exactly ONE follow-up on that same resume point before moving to the next resume question.
- The follow-up should dig into what they personally did, a decision, a result, or a difficulty, still one short question.
- Then go to the next resume question. After the third resume question and its follow-up, end the interview.

## Hard limits:
- Do not add a fourth intro follow-up.
- Do not skip a resume question.
- Do not ask two follow-ups on the same resume question.
- Do not recite the resume. When you hit Phase 2, use the written question as-is (you may tighten wording slightly for speech).
- Never invent a generic competency question. If you are not on a written resume question, you are still in the intro phase.

${seniorityTone(params.seniority, params.roleTitle)}

${params.turnDiscipline}

${params.delivery}`;
}
