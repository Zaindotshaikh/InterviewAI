import type { CandidateContext } from "../../lib/candidateContext.js";

/** BCP-47-ish language codes supported by the v2 Indic interview flow. */
export type InterviewLanguageCode =
  | "en-IN"
  | "hi-IN"
  | "ta-IN"
  | "te-IN"
  | "kn-IN"
  | "ml-IN"
  | "mr-IN"
  | "bn-IN"
  | "gu-IN"
  | "pa-IN"
  | "od-IN";

export type InterviewPlanStepKind =
  | "greeting"
  | "intro"
  | "intro_followup"
  | "resume_question"
  | "resume_followup"
  | "screening"
  | "clinical"
  | "closing";

export type InterviewPlanStep = {
  id: string;
  kind: InterviewPlanStepKind;
  /** Exact question when pre-authored (resume questions). Empty for improvised follow-ups. */
  prompt: string;
  /** Max follow-ups allowed after this step before advancing. */
  maxFollowUps: number;
};

export type InterviewPlan = {
  /** 2 = goal-driven flow: the agent runs the interview from lueprint; steps is only an outline. */
  version: 1 | 2;
  interviewId: string;
  language: InterviewLanguageCode;
  /** Prefer codemix ASR when the candidate may mix English. */
  sttMode: "transcribe" | "codemix";
  targetMinutes: number;
  companyName: string;
  interviewerName: string;
  roleTitle: string;
  criteria: string[];
  candidateContext: CandidateContext;
  keyterms: string[];
  glossaryHints: string[];
  steps: InterviewPlanStep[];
  systemPrompt: string;
  /** Role blueprint (screening fields, care duties, clinical rubric, tiers). Shipped whole to the agent. */
  blueprint?: InterviewBlueprint;
};

export type V2ControllerState = {
  stepIndex: number;
  followUpsUsed: number;
  consecutiveNoise: number;
  consecutiveWeak: number;
  language: InterviewLanguageCode;
  startedAt: string;
  lastTurnAt: string | null;
  completed: boolean;
  recordingConsent: boolean;
  /** Serialised agent FlowState: slots, care stances, clinical progress, contradictions. Enables resume + scoring. */
  flow?: InterviewFlowState;
};

/** Loose view of the blueprint JSON (the agent owns the full schema). */
export type InterviewBlueprint = {
  id: string;
  role_family?: string;
  limits: Record<string, number>;
  screening: Record<string, unknown>;
  clinical: { areas: { id: string; title: string; tags: string[]; levels: unknown[] }[] } & Record<string, unknown>;
  tiers: { id: string; name: string; description: string; criteria: string[] }[];
  faq?: unknown;
};

/** Loose view of the agent FlowState JSON (see agent/interview/flow_state.py). */
export type InterviewFlowState = {
  stage: string;
  language: string;
  turns: number;
  elapsed_s: number;
  slots: Record<string, { value: unknown; status: string; confidence?: number; turn?: number }>;
  care: Record<string, { stance: string; persuasions: number; reason?: string }>;
  gate_failed: string | null;
  experience_level: string;
  areas: Record<
    string,
    {
      area_id: string;
      level: number;
      status: string;
      outcome: string;
      covered: string[];
      missing: string[];
      red_flags: string[];
      dont_knows: number;
      evidence: { turn: number; level: number; quality: string; quote?: string; summary?: string }[];
    }
  >;
  area_order: string[];
  contradictions: { claim_a?: string; claim_b?: string; note?: string; resolved?: boolean; resolution?: string }[];
  unclear_total: number;
  dont_know_total: number;
  repeat_requests: number;
  nervous_events: number;
  interruptions: number;
  outcome: string | null;
};

export type V2Event = {
  ts: string;
  type: string;
  data?: Record<string, unknown>;
};

export type V2InterviewExtras = {
  pipeline: "v2";
  language: InterviewLanguageCode;
  plan: InterviewPlan;
  controller: V2ControllerState;
  events: V2Event[];
  roomName: string;
  providerMode: string;
  recordingConsent: boolean;
  avatar?: boolean;
  /** Per-interview TTS override (e.g. "elevenlabs" for the test route). */
  ttsProvider?: string;
  englishTranscript?: { role: "user" | "assistant"; text: string; timestamp: string }[];
};

export const SUPPORTED_LANGUAGES: {
  code: InterviewLanguageCode;
  label: string;
  sttMode: "transcribe" | "codemix";
  ttsSpeaker: string;
}[] = [
  { code: "en-IN", label: "English (India)", sttMode: "transcribe", ttsSpeaker: "ishita" },
  { code: "hi-IN", label: "Hindi / Hinglish", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "ta-IN", label: "Tamil / Tanglish", sttMode: "codemix", ttsSpeaker: "ishita" },
  { code: "te-IN", label: "Telugu", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "kn-IN", label: "Kannada", sttMode: "codemix", ttsSpeaker: "ishita" },
  { code: "ml-IN", label: "Malayalam", sttMode: "codemix", ttsSpeaker: "pooja" },
  { code: "mr-IN", label: "Marathi", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "bn-IN", label: "Bengali", sttMode: "codemix", ttsSpeaker: "roopa" },
  { code: "gu-IN", label: "Gujarati", sttMode: "codemix", ttsSpeaker: "priya" },
  { code: "pa-IN", label: "Punjabi", sttMode: "codemix", ttsSpeaker: "roopa" },
  { code: "od-IN", label: "Odia", sttMode: "codemix", ttsSpeaker: "ritu" },
];
