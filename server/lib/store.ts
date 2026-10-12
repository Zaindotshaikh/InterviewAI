import { readFile, writeFile, mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";
import type { CandidateContext } from "./candidateContext.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, "..", "data");
const rolesPath = path.join(__dirname, "..", "config", "roles.json");
const candidatesPath = path.join(dataDir, "candidates.json");
const demoLeadsPath = path.join(dataDir, "demo-leads.json");

export type RoleConfig = {
  id: string;
  title: string;
  questions: string[];
  criteria: string[];
};

export type TranscriptTurn = {
  role: "user" | "assistant";
  text: string;
  timestamp: string;
};

/** Pipeline candidate saved from TA "Add Candidate" form. */
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

export type InterviewRecord = {
  id: string;
  candidateName: string;
  roleId: string;
  roleTitle: string;
  criteria: string[];
  questions: string[];
  resumeText?: string;
  candidateContext?: CandidateContext;
  candidateId?: string;
  instructions: string;
  createdAt: string;
  transcript: TranscriptTurn[];
  summary: unknown | null;
  integrity?: {
    available: boolean;
    events: Array<{
      type: "no_face" | "multiple_faces" | "looked_away";
      startTime: string;
      endTime: string;
      durationSeconds: number;
    }>;
  } | null;
};

async function ensureDataDir() {
  await mkdir(dataDir, { recursive: true });
}

function interviewPath(id: string) {
  return path.join(dataDir, `${id}.json`);
}

export async function listRoles(): Promise<RoleConfig[]> {
  const raw = await readFile(rolesPath, "utf-8");
  return JSON.parse(raw) as RoleConfig[];
}

export async function createInterview(interview: InterviewRecord): Promise<InterviewRecord> {
  await ensureDataDir();
  await writeFile(interviewPath(interview.id), JSON.stringify(interview, null, 2), "utf-8");
  return interview;
}

export async function getInterview(id: string): Promise<InterviewRecord | null> {
  try {
    const raw = await readFile(interviewPath(id), "utf-8");
    return JSON.parse(raw) as InterviewRecord;
  } catch {
    return null;
  }
}

export async function appendTranscriptTurn(id: string, turn: TranscriptTurn): Promise<void> {
  const interview = await getInterview(id);
  if (!interview) throw new Error("Interview not found");
  interview.transcript.push(turn);
  await writeFile(interviewPath(id), JSON.stringify(interview, null, 2), "utf-8");
}

export async function saveSummary(id: string, summary: unknown): Promise<void> {
  const interview = await getInterview(id);
  if (!interview) throw new Error("Interview not found");
  interview.summary = summary;
  await writeFile(interviewPath(id), JSON.stringify(interview, null, 2), "utf-8");
}

export async function saveIntegrity(
  id: string,
  integrity: NonNullable<InterviewRecord["integrity"]>,
): Promise<void> {
  const interview = await getInterview(id);
  if (!interview) throw new Error("Interview not found");
  interview.integrity = integrity;
  await writeFile(interviewPath(id), JSON.stringify(interview, null, 2), "utf-8");
}

async function readCandidates(): Promise<CandidateRecord[]> {
  try {
    const raw = await readFile(candidatesPath, "utf-8");
    return JSON.parse(raw) as CandidateRecord[];
  } catch {
    return [];
  }
}

async function writeCandidates(candidates: CandidateRecord[]): Promise<void> {
  await ensureDataDir();
  await writeFile(candidatesPath, JSON.stringify(candidates, null, 2), "utf-8");
}

export async function listCandidates(): Promise<CandidateRecord[]> {
  return readCandidates();
}

export async function getCandidate(id: string): Promise<CandidateRecord | null> {
  const all = await readCandidates();
  return all.find((c) => c.id === id) ?? null;
}

export async function createCandidate(
  candidate: CandidateRecord,
): Promise<CandidateRecord> {
  const all = await readCandidates();
  all.unshift(candidate);
  await writeCandidates(all);
  return candidate;
}

export async function updateCandidate(
  id: string,
  patch: Partial<CandidateRecord>,
): Promise<CandidateRecord | null> {
  const all = await readCandidates();
  const idx = all.findIndex((c) => c.id === id);
  if (idx < 0) return null;
  all[idx] = { ...all[idx], ...patch, id };
  await writeCandidates(all);
  return all[idx];
}

/** Prospect who started a public live demo. */
export type DemoLeadRecord = {
  id: string;
  name: string;
  email: string;
  company: string;
  industry: string;
  roleId?: string;
  roleTitle?: string;
  interviewId?: string;
  createdAt: string;
};

async function readDemoLeads(): Promise<DemoLeadRecord[]> {
  try {
    const raw = await readFile(demoLeadsPath, "utf-8");
    return JSON.parse(raw) as DemoLeadRecord[];
  } catch {
    return [];
  }
}

async function writeDemoLeads(leads: DemoLeadRecord[]): Promise<void> {
  await ensureDataDir();
  await writeFile(demoLeadsPath, JSON.stringify(leads, null, 2), "utf-8");
}

export async function createDemoLead(lead: DemoLeadRecord): Promise<DemoLeadRecord> {
  const all = await readDemoLeads();
  all.unshift(lead);
  await writeDemoLeads(all);
  return lead;
}

export async function updateDemoLead(
  id: string,
  patch: Partial<DemoLeadRecord>,
): Promise<DemoLeadRecord | null> {
  const all = await readDemoLeads();
  const idx = all.findIndex((l) => l.id === id);
  if (idx < 0) return null;
  all[idx] = { ...all[idx], ...patch, id };
  await writeDemoLeads(all);
  return all[idx];
}
