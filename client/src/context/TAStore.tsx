import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { MOCK_TA_USER } from "../config/brand";
import {
  MOCK_CANDIDATES,
  MOCK_ROLES,
  type MockCandidate,
  type MockRole,
  type MockScorecard,
  type CandidateStatus,
} from "../data/mockData";

type TaUser = typeof MOCK_TA_USER | null;

type TAStoreValue = {
  user: TaUser;
  roles: MockRole[];
  candidates: MockCandidate[];
  login: (email?: string) => void;
  logout: () => void;
  getRole: (roleId: string) => MockRole | undefined;
  getCandidatesForRole: (roleId: string) => MockCandidate[];
  getCandidate: (id: string) => MockCandidate | undefined;
  getCandidateByToken: (token: string) => MockCandidate | undefined;
  inviteCandidate: (candidateId: string) => { token: string; link: string };
  addCandidate: (input: {
    roleId: string;
    name: string;
    email: string;
    noticePeriod?: string;
    currentCompany?: string;
    yearsOfExperience?: string;
    resumeText?: string;
  }) => MockCandidate;
  markInterviewInProgress: (candidateId: string) => void;
  updateCandidateDetails: (
    candidateId: string,
    patch: Partial<
      Pick<
        MockCandidate,
        | "name"
        | "email"
        | "noticePeriod"
        | "currentCompany"
        | "yearsOfExperience"
        | "resumeText"
        | "roleId"
      >
    > & { roleAppliedFor?: string },
  ) => void;
  completeLiveInterview: (input: {
    candidateId: string;
    interviewId: string;
    scorecard: MockScorecard;
    candidateName?: string;
  }) => void;
  updateCandidateStatus: (candidateId: string, status: CandidateStatus) => void;
  roleStats: (roleId: string) => { candidates: number; completed: number };
};

const TAStoreContext = createContext<TAStoreValue | null>(null);

const CANDIDATES_KEY = "interviewai.ta.candidates.v1";

function newToken() {
  return `tok_${Math.random().toString(36).slice(2, 10)}`;
}

function persistCandidates(list: MockCandidate[]) {
  try {
    localStorage.setItem(CANDIDATES_KEY, JSON.stringify(list));
  } catch {
    // ignore quota / private mode
  }
}

function loadCandidates(): MockCandidate[] {
  try {
    const raw = localStorage.getItem(CANDIDATES_KEY);
    if (!raw) return MOCK_CANDIDATES;
    const parsed = JSON.parse(raw) as MockCandidate[];
    if (!Array.isArray(parsed)) return MOCK_CANDIDATES;

    // Merge persisted state with seed data so new mock roles/candidates still appear
    const byId = new Map<string, MockCandidate>();
    for (const c of MOCK_CANDIDATES) byId.set(c.id, c);
    for (const c of parsed) byId.set(c.id, { ...byId.get(c.id), ...c });
    return Array.from(byId.values());
  } catch {
    return MOCK_CANDIDATES;
  }
}

export function TAStoreProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<TaUser>(null);
  const [roles] = useState<MockRole[]>(MOCK_ROLES);
  const [candidates, setCandidates] = useState<MockCandidate[]>(() => loadCandidates());

  useEffect(() => {
    persistCandidates(candidates);
  }, [candidates]);

  // Keep other tabs in sync when an invite is created
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== CANDIDATES_KEY || !e.newValue) return;
      try {
        const parsed = JSON.parse(e.newValue) as MockCandidate[];
        if (Array.isArray(parsed)) setCandidates(parsed);
      } catch {
        // ignore
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const login = useCallback((_email?: string) => {
    setUser(MOCK_TA_USER);
  }, []);

  const logout = useCallback(() => setUser(null), []);

  const getRole = useCallback((roleId: string) => roles.find((r) => r.id === roleId), [roles]);

  const getCandidatesForRole = useCallback(
    (roleId: string) => candidates.filter((c) => c.roleId === roleId),
    [candidates],
  );

  const getCandidate = useCallback(
    (id: string) => candidates.find((c) => c.id === id),
    [candidates],
  );

  const getCandidateByToken = useCallback(
    (token: string) => {
      const normalized = decodeURIComponent(token).trim();
      return candidates.find((c) => c.inviteToken === normalized);
    },
    [candidates],
  );

  const inviteCandidate = useCallback(
    (candidateId: string) => {
      const existing = candidates.find((c) => c.id === candidateId);
      const token = existing?.inviteToken ?? newToken();

      setCandidates((prev) => {
        const next = prev.map((c) =>
          c.id === candidateId
            ? {
                ...c,
                status: c.status === "Not Invited" ? ("Invited" as const) : c.status,
                dateInvited: c.dateInvited ?? new Date().toISOString().slice(0, 10),
                inviteToken: token,
              }
            : c,
        );
        // Write immediately so a newly opened invite tab can resolve the token
        persistCandidates(next);
        return next;
      });

      return { token, link: `${window.location.origin}/i/${token}` };
    },
    [candidates],
  );

  const addCandidate = useCallback(
    (input: {
      roleId: string;
      name: string;
      email: string;
      noticePeriod?: string;
      currentCompany?: string;
      yearsOfExperience?: string;
      resumeText?: string;
    }) => {
      const candidate: MockCandidate = {
        id: `c-live-${Date.now()}`,
        roleId: input.roleId,
        name: input.name.trim(),
        email: input.email.trim(),
        status: "Not Invited",
        dateInvited: null,
        inviteToken: null,
        score: null,
        noticePeriod: input.noticePeriod,
        currentCompany: input.currentCompany,
        yearsOfExperience: input.yearsOfExperience,
        resumeText: input.resumeText,
      };
      setCandidates((prev) => {
        const next = [candidate, ...prev];
        persistCandidates(next);
        return next;
      });
      return candidate;
    },
    [],
  );

  const markInterviewInProgress = useCallback((candidateId: string) => {
    setCandidates((prev) => {
      const next = prev.map((c) =>
        c.id === candidateId && (c.status === "Invited" || c.status === "Not Invited")
          ? { ...c, status: "In Progress" as const }
          : c,
      );
      persistCandidates(next);
      return next;
    });
  }, []);

  const updateCandidateDetails = useCallback(
    (
      candidateId: string,
      patch: Partial<
        Pick<
          MockCandidate,
          | "name"
          | "email"
          | "noticePeriod"
          | "currentCompany"
          | "yearsOfExperience"
          | "resumeText"
          | "roleId"
        >
      > & { roleAppliedFor?: string },
    ) => {
      setCandidates((prev) => {
        const next = prev.map((c) => {
          if (c.id !== candidateId) return c;
          return {
            ...c,
            ...patch,
            name: patch.name?.trim() || c.name,
          };
        });
        persistCandidates(next);
        return next;
      });
    },
    [],
  );

  const completeLiveInterview = useCallback(
    (input: {
      candidateId: string;
      interviewId: string;
      scorecard: MockScorecard;
      candidateName?: string;
    }) => {
      setCandidates((prev) => {
        const next = prev.map((c) =>
          c.id === input.candidateId
            ? {
                ...c,
                name: input.candidateName?.trim() || c.name,
                status: "Completed" as const,
                interviewId: input.interviewId,
                score: input.scorecard.overall_score,
                scorecard: input.scorecard,
              }
            : c,
        );
        persistCandidates(next);
        return next;
      });
    },
    [],
  );

  const updateCandidateStatus = useCallback((candidateId: string, status: CandidateStatus) => {
    setCandidates((prev) => {
      const next = prev.map((c) => (c.id === candidateId ? { ...c, status } : c));
      persistCandidates(next);
      return next;
    });
  }, []);

  const roleStats = useCallback(
    (roleId: string) => {
      const list = candidates.filter((c) => c.roleId === roleId);
      return {
        candidates: list.length,
        completed: list.filter((c) =>
          ["Completed", "Reviewed", "Shortlisted", "Rejected"].includes(c.status),
        ).length,
      };
    },
    [candidates],
  );

  const value = useMemo(
    () => ({
      user,
      roles,
      candidates,
      login,
      logout,
      getRole,
      getCandidatesForRole,
      getCandidate,
      getCandidateByToken,
      inviteCandidate,
      addCandidate,
      markInterviewInProgress,
      updateCandidateDetails,
      completeLiveInterview,
      updateCandidateStatus,
      roleStats,
    }),
    [
      user,
      roles,
      candidates,
      login,
      logout,
      getRole,
      getCandidatesForRole,
      getCandidate,
      getCandidateByToken,
      inviteCandidate,
      addCandidate,
      markInterviewInProgress,
      updateCandidateDetails,
      completeLiveInterview,
      updateCandidateStatus,
      roleStats,
    ],
  );

  return <TAStoreContext.Provider value={value}>{children}</TAStoreContext.Provider>;
}

export function useTAStore() {
  const ctx = useContext(TAStoreContext);
  if (!ctx) throw new Error("useTAStore must be used within TAStoreProvider");
  return ctx;
}
