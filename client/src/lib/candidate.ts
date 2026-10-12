export type CandidateContext = {
  name: string;
  roleAppliedFor: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  resumeText: string;
};

export type CandidateRecord = {
  id: string;
  name: string;
  roleId: string;
  roleAppliedFor: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  resumeText?: string;
  createdAt: string;
};

export function buildClientCandidateContext(input: {
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
  if (input.email?.trim()) ctx.email = input.email.trim();
  if (input.noticePeriod?.trim()) ctx.noticePeriod = input.noticePeriod.trim();
  if (input.currentCompany?.trim()) ctx.currentCompany = input.currentCompany.trim();
  if (input.yearsOfExperience?.trim()) ctx.yearsOfExperience = input.yearsOfExperience.trim();
  return ctx;
}
