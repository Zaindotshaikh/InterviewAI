import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import TALayout from "./components/ta/TALayout";
import { TAStoreProvider } from "./context/TAStore";
import { ThemeProvider } from "./context/Theme";
import LoginScreen from "./screens/LoginScreen";
import DashboardScreen from "./screens/DashboardScreen";
import RoleDetailScreen from "./screens/RoleDetailScreen";
import TAScorecardScreen from "./screens/TAScorecardScreen";
import CandidateInviteLanding from "./screens/CandidateInviteLanding";
import CandidateInterviewFlow from "./screens/CandidateInterviewFlow";
import CandidateThankYou from "./screens/CandidateThankYou";
import DemoFlow from "./screens/demo/DemoFlow";
import V2TestPage from "./v2/V2TestPage";
import V2InviteFlow from "./v2/V2InviteFlow";
import V2ThankYou from "./v2/V2ThankYou";

export type { InterviewSession, Scorecard } from "./types/session";

export default function App() {
  return (
    <ThemeProvider>
      <TAStoreProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/" element={<Navigate to="/login" replace />} />
            <Route path="/login" element={<LoginScreen />} />
            <Route path="/demo" element={<DemoFlow />} />

            <Route element={<TALayout />}>
              <Route path="/dashboard" element={<DashboardScreen />} />
              <Route path="/roles/:roleId" element={<RoleDetailScreen />} />
              <Route path="/candidates/:candidateId/scorecard" element={<TAScorecardScreen />} />
            </Route>

            <Route path="/i/:token" element={<CandidateInviteLanding />} />
            <Route path="/i/:token/setup" element={<CandidateInterviewFlow />} />
            <Route path="/i/:token/thanks" element={<CandidateThankYou />} />

            {/* Parallel Indic voice pipeline — does not replace /i/* */}
            <Route path="/v2/test" element={<V2TestPage />} />
            <Route path="/avatar-interviewer" element={<V2TestPage avatar />} />
            <Route path="/elevenlabs-interviewer" element={<V2TestPage ttsProvider="elevenlabs" />} />
            <Route path="/v2/i/:token" element={<V2InviteFlow />} />
            <Route path="/v2/i/:token/thanks" element={<V2ThankYou />} />

            <Route path="*" element={<Navigate to="/login" replace />} />
          </Routes>
        </BrowserRouter>
      </TAStoreProvider>
    </ThemeProvider>
  );
}
