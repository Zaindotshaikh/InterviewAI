export function buildScorecardPrompt(params: {
  roleTitle: string;
  candidateName: string;
  criteria: string[];
  transcript: { role: string; text: string }[];
}): string {
  const criteriaList = params.criteria.map((c) => `- ${c}`).join("\n");
  const transcriptText = params.transcript
    .map((t) => `${t.role === "user" ? "Candidate" : "Interviewer"}: ${t.text}`)
    .join("\n\n");

  return `You are scoring a completed job interview transcript for the role of ${params.roleTitle}.
The candidate's name is ${params.candidateName}. In the recommendation and notes, refer to them only as ${params.candidateName}. Never substitute another name.

Evaluation criteria for this role:
${criteriaList}

Given the full transcript below, return ONLY valid JSON in this shape:
{
  "overall_score": <1-10>,
  "recommendation": "<2-3 sentence hire/no-hire style recommendation referring to ${params.candidateName} by that name only>",
  "strengths": ["...", "..."],
  "gaps": ["...", "..."],
  "per_question_notes": [
    { "question": "...", "note": "..." }
  ]
}

Transcript:
${transcriptText}`;
}
