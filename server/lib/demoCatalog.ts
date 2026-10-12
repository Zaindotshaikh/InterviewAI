import { readFile } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import type { RoleConfig } from "./store.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const catalogPath = path.join(__dirname, "..", "config", "demoCatalog.json");

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

export async function loadDemoCatalog(): Promise<DemoCatalog> {
  const raw = await readFile(catalogPath, "utf-8");
  return JSON.parse(raw) as DemoCatalog;
}

export async function findDemoRole(roleId: string): Promise<DemoRole | null> {
  const catalog = await loadDemoCatalog();
  for (const industry of catalog.industries) {
    const role = industry.roles.find((r) => r.id === roleId);
    if (role) return role;
  }
  return null;
}

export function demoRoleAsConfig(role: DemoRole): RoleConfig {
  return {
    id: role.id,
    title: role.title,
    questions: role.questions,
    criteria: role.criteria,
  };
}
