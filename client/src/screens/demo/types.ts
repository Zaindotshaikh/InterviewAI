export type DemoSeniority = "senior" | "mid" | "junior";

export type DemoSampleResume = {
  label: string;
  yearsOfExperience: string;
  currentCompany: string;
  text: string;
};

export type DemoRole = {
  id: string;
  seniority: DemoSeniority;
  title: string;
  summary: string;
  responsibilities: string[];
  requirements: string[];
  questions: string[];
  criteria: string[];
  sampleResume: DemoSampleResume;
};

export type DemoIndustry = {
  id: string;
  label: string;
  blurb: string;
  roles: DemoRole[];
};

export type DemoCatalog = {
  interviewer: { name: string; title: string };
  industries: DemoIndustry[];
};

export type DemoProspect = {
  name: string;
  email: string;
  company: string;
  industry: string;
};

export const SENIORITY_LABEL: Record<DemoSeniority, string> = {
  senior: "Senior",
  mid: "Mid-level",
  junior: "Junior",
};

export const SENIORITY_ORDER: DemoSeniority[] = ["senior", "mid", "junior"];
