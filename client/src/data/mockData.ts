import { COMPANY_NAME } from "../config/brand";

export type CandidateStatus =
  | "Not Invited"
  | "Invited"
  | "In Progress"
  | "Completed"
  | "Reviewed"
  | "Shortlisted"
  | "Rejected";

export type MockScorecard = {
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

export type MockCandidate = {
  id: string;
  roleId: string;
  name: string;
  email: string;
  status: CandidateStatus;
  dateInvited: string | null;
  inviteToken: string | null;
  score: number | null;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
  resumeText?: string;
  /** Live interview id when completed in this session */
  interviewId?: string;
  scorecard?: MockScorecard | null;
};

export type MockRole = {
  id: string;
  title: string;
  criteria: string[];
  openHeadcount: number;
  candidateCount: number;
  completedCount: number;
};

export const MOCK_ROLES: MockRole[] = [
  {
    id: "staff-nurse",
    title: "Staff Nurse",
    criteria: [
      "Safe bedside care and vital-sign judgement",
      "Medication safety and documentation",
      "Comfort with essential patient-care duties",
      "Clear communication under pressure",
    ],
    openHeadcount: 4,
    candidateCount: 4,
    completedCount: 1,
  },
  {
    id: "icu-nurse",
    title: "ICU / Critical Care Nurse",
    criteria: [
      "Critical-care monitoring and alarm response",
      "Airway, ventilation and emergency basics",
      "High-alert medication safety",
      "Team communication during deterioration",
    ],
    openHeadcount: 2,
    candidateCount: 3,
    completedCount: 1,
  },
  {
    id: "home-care-nurse",
    title: "Home Care Nurse",
    criteria: [
      "Independent judgement in a home setting",
      "Hands-on personal care including hygiene and incontinence care",
      "Patient and family communication",
      "Early recognition of deterioration",
    ],
    openHeadcount: 3,
    candidateCount: 3,
    completedCount: 1,
  },
];

export const MOCK_CANDIDATES: MockCandidate[] = [
  {
    id: "c-sn-1",
    roleId: "staff-nurse",
    name: "Priya Sharma",
    email: "priya.sharma@email.com",
    status: "Completed",
    dateInvited: "2026-08-01",
    inviteToken: "tok_priya_sn",
    score: 8,
    currentCompany: "Manipal Hospitals",
    yearsOfExperience: "4",
    noticePeriod: "30 days",
    scorecard: {
      overall_score: 8,
      recommendation:
        "Strong hire for ward staff nurse. Clear escalation stories and comfortable with essential bedside care.",
      strengths: ["Early recognition of deterioration", "Calm family communication"],
      gaps: ["Could go deeper on documentation discipline"],
      per_question_notes: [{ question: "Deterioration", note: "Noticed NEWS change and escalated with SBAR." }],
    },
  },
  {
    id: "c-sn-2",
    roleId: "staff-nurse",
    name: "Rahul Mehta",
    email: "rahul.mehta@email.com",
    status: "In Progress",
    dateInvited: "2026-08-05",
    inviteToken: "tok_rahul_sn",
    score: null,
    currentCompany: "Fortis",
    yearsOfExperience: "3",
  },
  {
    id: "c-sn-3",
    roleId: "staff-nurse",
    name: "Ananya Iyer",
    email: "ananya.iyer@email.com",
    status: "Invited",
    dateInvited: "2026-08-06",
    inviteToken: "tok_ananya_sn",
    score: null,
    yearsOfExperience: "2",
  },
  {
    id: "c-sn-4",
    roleId: "staff-nurse",
    name: "Vikram Singh",
    email: "vikram.singh@email.com",
    status: "Not Invited",
    dateInvited: null,
    inviteToken: null,
    score: null,
    currentCompany: "Apollo Hospitals",
    yearsOfExperience: "5",
    noticePeriod: "60 days",
  },
  {
    id: "c-icu-1",
    roleId: "icu-nurse",
    name: "Neha Banerjee",
    email: "neha.banerjee@email.com",
    status: "Completed",
    dateInvited: "2026-08-03",
    inviteToken: "tok_neha_icu",
    score: 8,
    currentCompany: "Apollo Hospitals",
    yearsOfExperience: "6",
    scorecard: {
      overall_score: 8,
      recommendation: "Ready for ICU with orientation. Solid ventilator and emergency response examples.",
      strengths: ["Ventilator alarm response", "Medication five-rights"],
      gaps: ["Limited independent charge experience"],
      per_question_notes: [],
    },
  },
  {
    id: "c-icu-2",
    roleId: "icu-nurse",
    name: "Imran Qureshi",
    email: "imran.qureshi@email.com",
    status: "Invited",
    dateInvited: "2026-08-07",
    inviteToken: "tok_imran_icu",
    score: null,
    yearsOfExperience: "4",
    noticePeriod: "30 days",
  },
  {
    id: "c-icu-3",
    roleId: "icu-nurse",
    name: "Sneha Kapoor",
    email: "sneha.kapoor@email.com",
    status: "Not Invited",
    dateInvited: null,
    inviteToken: null,
    score: null,
    currentCompany: "Narayana Health",
    yearsOfExperience: "7",
  },
  {
    id: "c-hc-1",
    roleId: "home-care-nurse",
    name: "Meera Joshi",
    email: "meera.joshi@email.com",
    status: "Completed",
    dateInvited: "2026-08-02",
    inviteToken: "tok_meera_hc",
    score: 7,
    currentCompany: "Portea",
    yearsOfExperience: "3",
    scorecard: {
      overall_score: 7,
      recommendation: "Good home-care fit. Comfortable with personal care; needs support on lone-worker escalation.",
      strengths: ["Hygiene and incontinence care", "Family education"],
      gaps: ["Could be clearer on when to call the doctor vs wait"],
      per_question_notes: [],
    },
  },
  {
    id: "c-hc-2",
    roleId: "home-care-nurse",
    name: "Pooja Reddy",
    email: "pooja.reddy@email.com",
    status: "Invited",
    dateInvited: "2026-08-06",
    inviteToken: "tok_pooja_hc",
    score: null,
  },
  {
    id: "c-hc-3",
    roleId: "home-care-nurse",
    name: "Karan Desai",
    email: "karan.desai@email.com",
    status: "Not Invited",
    dateInvited: null,
    inviteToken: null,
    score: null,
    currentCompany: "Nightingales",
    yearsOfExperience: "2",
  },
];

export const DASHBOARD_STATS = {
  openRoles: MOCK_ROLES.length,
  candidatesInPipeline: MOCK_CANDIDATES.length,
  interviewsCompletedThisWeek: 4,
  avgTimeToScreenDays: 2.4,
  company: COMPANY_NAME,
};
