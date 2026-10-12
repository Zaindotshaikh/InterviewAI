export type CandidateContext = {
  name: string;
  roleAppliedFor: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  resumeText: string;
};

/** Keep only fields that were actually filled in. */
export function buildCandidateContext(input: {
  name: string;
  roleAppliedFor: string;
  resumeText: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
}): CandidateContext {
  const ctx: CandidateContext = {
    name: input.name.trim(),
    roleAppliedFor: input.roleAppliedFor.trim(),
    resumeText: input.resumeText.trim(),
  };

  const email = input.email?.trim();
  const noticePeriod = input.noticePeriod?.trim();
  const currentCompany = input.currentCompany?.trim();
  const yearsOfExperience = input.yearsOfExperience?.trim();

  if (email) ctx.email = email;
  if (noticePeriod) ctx.noticePeriod = noticePeriod;
  if (currentCompany) ctx.currentCompany = currentCompany;
  if (yearsOfExperience) ctx.yearsOfExperience = yearsOfExperience;

  return ctx;
}

const DETAIL_LABELS: { key: keyof CandidateContext; label: string }[] = [
  { key: "email", label: "Email" },
  { key: "currentCompany", label: "Current Company" },
  { key: "yearsOfExperience", label: "Years of Experience" },
  { key: "noticePeriod", label: "Notice Period" },
];

/** Prompt block for interviewer / question generator. Omits empty fields. */
export function formatCandidateDetailsSection(ctx: CandidateContext): string {
  const lines = [
    `Name: ${ctx.name}`,
    `Role Applied For: ${ctx.roleAppliedFor}`,
  ];

  for (const { key, label } of DETAIL_LABELS) {
    const value = ctx[key];
    if (typeof value === "string" && value.trim()) {
      lines.push(`${label}: ${value.trim()}`);
    }
  }

  return `## Candidate Details:
${lines.join("\n")}`;
}
