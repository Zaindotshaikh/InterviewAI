import { Link, useNavigate, useParams } from "react-router-dom";
import ThemeToggle from "../components/ThemeToggle";
import { COMPANY_NAME } from "../config/brand";
import { useTAStore } from "../context/TAStore";

export default function CandidateInviteLanding() {
  const { token = "" } = useParams();
  const { getCandidateByToken, getRole } = useTAStore();
  const candidate = getCandidateByToken(token);
  const role = candidate ? getRole(candidate.roleId) : undefined;
  const navigate = useNavigate();

  if (!candidate || !role) {
    return (
      <div className="relative grid min-h-screen place-items-center px-6">
        <div className="fixed top-5 right-5 z-40">
          <ThemeToggle />
        </div>
        <div className="max-w-md text-center">
          <h1 className="text-2xl text-[var(--color-fg)]">Invite not found</h1>
          <p className="mt-2 text-[var(--color-muted)]">
            This interview link is invalid or expired.
          </p>
          <Link to="/login" className="mt-6 inline-block text-sm text-[var(--color-accent)]">
            TA Portal
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="relative mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6 py-16">
      <div className="fixed top-5 right-5 z-40">
        <ThemeToggle />
      </div>
      <p className="text-sm font-medium tracking-[0.18em] text-[var(--color-accent)] uppercase">
        {COMPANY_NAME}
      </p>
      <h1 className="mt-3 font-[family-name:var(--font-display)] text-4xl leading-tight text-[var(--color-fg)]">
        You&apos;ve been invited to an AI interview for {role.title} at {COMPANY_NAME}.
      </h1>
      <p className="mt-4 text-[var(--color-muted)]">
        Hi {candidate.name.split(" ")[0]}. This is a live spoken interview with our AI interviewer.
        Plan for about 10 minutes in a quiet space with a working microphone.
      </p>
      <ul className="mt-6 space-y-2 text-sm text-[var(--color-muted)]">
        <li>• Allow microphone access when prompted</li>
        <li>• Speak naturally. No push-to-talk</li>
        <li>• Have your resume ready to upload or paste</li>
        <li>
          • This interview uses your camera to verify your presence throughout the session
        </li>
      </ul>
      <button
        type="button"
        onClick={() => navigate(`/i/${token}/setup`)}
        className="mt-10 w-full rounded-xl bg-[var(--color-accent)] px-4 py-3.5 font-semibold text-[var(--color-on-accent)]"
      >
        Begin
      </button>
    </div>
  );
}
