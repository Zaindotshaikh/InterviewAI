import type { CandidateContext } from "../lib/candidate";

export type InterviewSession = {
  id: string;
  candidateName: string;
  roleTitle: string;
  questions: string[];
  instructions: string;
  candidateContext?: CandidateContext;
  transcriptionKeywords?: string[];
  interviewerName?: string;
  interviewerTitle?: string;
  demo?: boolean;
  /** Mock pipeline candidate id for TA status updates */
  pipelineCandidateId?: string;
};

export type Scorecard = {
  overall_score: number;
  recommendation: string;
  strengths: string[];
  gaps: string[];
  per_question_notes: { question: string; note: string }[];
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
