export type CandidateGender = "male" | "female" | "unspecified";

export type CandidateContext = {
  name: string;
  roleAppliedFor: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  /** 10-digit Indian mobile, when the candidate typed it before the call. */
  phone?: string;
  /** How the interviewer should address them. Omitted on routes that do not ask. */
  gender?: CandidateGender;
  resumeText: string;
};

/** Keep only fields that were actually filled in. */
/** Keep a typed Indian mobile, or drop anything that is not 10 digits starting 6–9. */
export function normalizeIndianMobile(raw: string | undefined | null): string | undefined {
  if (!raw) return undefined;
  let digits = raw.replace(/\D/g, "");
  if (digits.startsWith("0091") && digits.length >= 14) digits = digits.slice(4);
  else if (digits.startsWith("091") && digits.length === 13) digits = digits.slice(3);
  else if (digits.startsWith("91") && digits.length === 12) digits = digits.slice(2);
  else if (digits.startsWith("0") && digits.length === 11) digits = digits.slice(1);
  return /^[6-9]\d{9}$/.test(digits) ? digits : undefined;
}

export function normalizeCandidateGender(raw: string | undefined | null): CandidateGender | undefined {
  const value = raw?.trim().toLowerCase();
  if (value === "male" || value === "female" || value === "unspecified") return value;
  return undefined;
}

export function buildCandidateContext(input: {
  name: string;
  roleAppliedFor: string;
  resumeText: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  phone?: string;
  gender?: string;
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
  const phone = normalizeIndianMobile(input.phone);
  const gender = normalizeCandidateGender(input.gender);

  if (email) ctx.email = email;
  if (noticePeriod) ctx.noticePeriod = noticePeriod;
  if (currentCompany) ctx.currentCompany = currentCompany;
  if (yearsOfExperience) ctx.yearsOfExperience = yearsOfExperience;
  if (phone) ctx.phone = phone;
  if (gender) ctx.gender = gender;

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

  if (ctx.gender === "female") lines.push("Gender: Female");
  else if (ctx.gender === "male") lines.push("Gender: Male");
  else if (ctx.gender === "unspecified") lines.push("Gender: Not specified");

  return `## Candidate Details:
${lines.join("\n")}`;
}
