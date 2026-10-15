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

export type V2LanguageOption = {
  code: InterviewLanguageCode;
  label: string;
  sttMode: "transcribe" | "codemix";
  ttsSpeaker: string;
};

export type V2StartResponse = {
  id: string;
  pipeline: "v2";
  candidateName: string;
  roleTitle: string;
  language: InterviewLanguageCode;
  questions: string[];
  interviewerName: string;
  interviewerTitle: string;
  targetMinutes: number;
  roomName: string;
  livekit: { url: string; token: string; agentName: string } | null;
  livekitConfigured: boolean;
  providerMode: string;
  avatar?: boolean;
  ttsProvider?: string;
  voiceProvider?: string;
  planStepCount: number;
};

export type V2TierId = "tier_1" | "tier_2" | "tier_3" | "not_eligible" | "needs_review";

export type V2TierEvidence = { area: string; point: string; quote: string; verified: boolean };

export type V2ClinicalArea = {
  id: string;
  title: string;
  outcome: "strong" | "adequate" | "weak" | "unsafe" | "unknown" | string;
  level: number;
  covered: string[];
  missing: string[];
  red_flags: string[];
  dont_knows: number;
  evidence: { quality: string; quote: string; summary: string }[];
};

export type V2Scorecard = {
  /** null when the interview needs a human to review it. */
  overall_score: number | null;
  recommendation: string;
  strengths: string[];
  gaps: string[];
  per_question_notes: { question: string; note: string }[];
  pipeline?: string;
  language?: string;
  // Classification (interviews run on the goal-driven flow)
  tier?: V2TierId;
  tier_name?: string;
  tier_confidence?: number;
  tier_reasoning?: string;
  tier_method?: "rule" | "model" | "rule_override";
  tier_evidence?: V2TierEvidence[];
  flags?: string[];
  screening?: Record<string, unknown>;
  clinical_areas?: V2ClinicalArea[];
  contradictions?: { claim_a?: string; claim_b?: string; note?: string; resolved?: boolean; resolution?: string }[];
  outcome?: string | null;
  integrity?: {
    available: boolean;
    events: {
      type: "no_face" | "multiple_faces" | "looked_away";
      startTime: string;
      endTime: string;
      durationSeconds: number;
    }[];
  };
};
