import { Router } from "express";
import { v4 as uuidv4 } from "uuid";
import OpenAI from "openai";
import { buildCandidateContext, type CandidateContext } from "../lib/candidateContext.js";
import { createInterview, getCandidate, getInterview, listRoles } from "../lib/store.js";
import { demoRoleAsConfig, findDemoRole, loadDemoCatalog } from "../lib/demoCatalog.js";
import { extractTranscriptionKeywords } from "../lib/transcriptionKeywords.js";
import { buildInterviewerInstructions, inferSeniority, type InterviewSeniority } from "../prompts/interviewer.js";
import { buildResumeQuestionsPrompt } from "../prompts/resumeQuestions.js";

const router = Router();

function parseCandidateContextFromBody(body: {
  candidateContext?: Partial<CandidateContext>;
  candidateName?: string;
  roleTitle?: string;
  resumeText?: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
}): CandidateContext | null {
  const nested = body.candidateContext;
  const name = (nested?.name ?? body.candidateName ?? "").trim();
  const roleAppliedFor = (nested?.roleAppliedFor ?? body.roleTitle ?? "").trim();
  const resumeText = (nested?.resumeText ?? body.resumeText ?? "").trim();

  if (!name || !roleAppliedFor || !resumeText) return null;

  return buildCandidateContext({
    name,
    roleAppliedFor,
    resumeText,
    email: nested?.email ?? body.email,
    noticePeriod: nested?.noticePeriod ?? body.noticePeriod,
    currentCompany: nested?.currentCompany ?? body.currentCompany,
    yearsOfExperience: nested?.yearsOfExperience ?? body.yearsOfExperience,
  });
}

router.post("/generate-questions", async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "OPENAI_API_KEY not configured" });
    return;
  }

  try {
    const body = req.body as {
      candidateContext?: Partial<CandidateContext>;
      resumeText?: string;
      roleTitle?: string;
      roleCriteria?: string[];
      seniority?: InterviewSeniority;
      candidateName?: string;
    };

    const candidateContext = parseCandidateContextFromBody(body);
    if (!candidateContext) {
      res.status(400).json({
        error: "candidateContext (name, roleAppliedFor, resumeText) is required",
      });
      return;
    }

    const criteria = Array.isArray(body.roleCriteria) ? body.roleCriteria : [];
    const seniority =
      body.seniority === "senior" || body.seniority === "mid" || body.seniority === "junior"
        ? body.seniority
        : undefined;
    const prompt = buildResumeQuestionsPrompt({
      roleTitle: candidateContext.roleAppliedFor,
      criteria,
      candidateContext,
      seniority,
    });

    const openai = new OpenAI({ apiKey });
    const model = process.env.CHAT_MODEL || "gpt-4o";

    const completion = await openai.chat.completions.create({
      model,
      temperature: 0.4,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content:
            "You prepare resume-specific interview questions. Return ONLY valid JSON matching the requested schema.",
        },
        { role: "user", content: prompt },
      ],
    });

    const raw = completion.choices[0]?.message?.content ?? "{}";
    const parsed = JSON.parse(raw) as { resume_questions?: unknown };
    const resumeQuestions = Array.isArray(parsed.resume_questions)
      ? parsed.resume_questions.filter((q): q is string => typeof q === "string" && q.trim().length > 0)
      : [];

    if (resumeQuestions.length < 3) {
      res.status(502).json({ error: "Model returned fewer than 3 resume questions" });
      return;
    }

    res.json({ resume_questions: resumeQuestions.slice(0, 3) });
  } catch (err) {
    console.error("Generate questions error:", err);
    res.status(500).json({ error: "Failed to generate resume questions" });
  }
});

router.post("/start", async (req, res) => {
  try {
    const body = req.body as {
      candidateName?: string;
      roleId?: string;
      resumeText?: string;
      resumeQuestions?: string[];
      candidateId?: string;
      candidateContext?: Partial<CandidateContext>;
      email?: string;
      noticePeriod?: string;
      currentCompany?: string;
      yearsOfExperience?: string;
      demo?: boolean;
    };

    if (!body.roleId) {
      res.status(400).json({ error: "roleId is required" });
      return;
    }

    const roles = await listRoles();
    let role = roles.find((r) => r.id === body.roleId) ?? null;
    let interviewerName: string | undefined;
    let interviewerTitle: string | undefined;
    let seniority: InterviewSeniority | undefined;
    let roleSummary: string | undefined;

    if (!role) {
      const demoRole = await findDemoRole(body.roleId);
      if (demoRole) {
        role = demoRoleAsConfig(demoRole);
        seniority = demoRole.seniority;
        roleSummary = demoRole.summary;
        const catalog = await loadDemoCatalog();
        interviewerName = catalog.interviewer.name;
        interviewerTitle = catalog.interviewer.title;
      }
    }

    if (!role) {
      res.status(404).json({ error: "Role not found" });
      return;
    }

    // Optional server-backed candidate. Mock pipeline IDs won't exist here.
    // Never block interview start if the client already sent a full candidateContext.
    let fromRecord: {
      name?: string;
      email?: string;
      noticePeriod?: string;
      currentCompany?: string;
      yearsOfExperience?: string;
      resumeText?: string;
    } = {};
    let resolvedCandidateId = body.candidateId;

    if (body.candidateId) {
      const record = await getCandidate(body.candidateId);
      if (record) {
        fromRecord = {
          name: record.name,
          email: record.email,
          noticePeriod: record.noticePeriod,
          currentCompany: record.currentCompany,
          yearsOfExperience: record.yearsOfExperience,
          resumeText: record.resumeText,
        };
      } else {
        console.warn(
          `candidateId ${body.candidateId} not in server store; using request candidateContext`,
        );
        resolvedCandidateId = undefined;
      }
    }

    const candidateContext = parseCandidateContextFromBody({
      candidateContext: {
        name: body.candidateContext?.name ?? body.candidateName ?? fromRecord.name,
        roleAppliedFor:
          body.candidateContext?.roleAppliedFor ?? role.title,
        resumeText:
          body.candidateContext?.resumeText ?? body.resumeText ?? fromRecord.resumeText,
        email: body.candidateContext?.email ?? body.email ?? fromRecord.email,
        noticePeriod:
          body.candidateContext?.noticePeriod ?? body.noticePeriod ?? fromRecord.noticePeriod,
        currentCompany:
          body.candidateContext?.currentCompany ??
          body.currentCompany ??
          fromRecord.currentCompany,
        yearsOfExperience:
          body.candidateContext?.yearsOfExperience ??
          body.yearsOfExperience ??
          fromRecord.yearsOfExperience,
      },
      roleTitle: role.title,
    });

    if (!candidateContext) {
      res.status(400).json({
        error: "candidate name and resumeText are required (via candidateContext or fields)",
      });
      return;
    }

    const extraQuestions = Array.isArray(body.resumeQuestions)
      ? body.resumeQuestions.filter((q) => typeof q === "string" && q.trim()).map((q) => q.trim())
      : [];

    const questions = extraQuestions.slice(0, 3);
    if (questions.length < 3) {
      res.status(400).json({ error: "At least 3 resume questions are required" });
      return;
    }

    const isDemo = Boolean(body.demo);
    const companyName = process.env.COMPANY_NAME || "Kreeda Labs";
    const targetMinutes = isDemo
      ? Number(process.env.DEMO_TARGET_MINUTES) || 10
      : Number(process.env.TARGET_MINUTES) || 10;
    const id = uuidv4();

    if (!interviewerName) {
      const catalog = await loadDemoCatalog();
      interviewerName = catalog.interviewer.name;
      interviewerTitle = catalog.interviewer.title;
    }

    if (!seniority) {
      seniority = inferSeniority(role.title);
    }

    const instructions = buildInterviewerInstructions({
      roleTitle: role.title,
      companyName,
      questions,
      targetMinutes,
      candidateContext,
      interviewerName,
      demo: isDemo,
      seniority,
      roleSummary,
    });

    console.info(
      `[interview] started ${id} instructions=${instructions.length}c resume=${candidateContext.resumeText.length}c questions=${questions.length} demo=${isDemo}`,
    );

    const transcriptionKeywords = extractTranscriptionKeywords({
      roleTitle: role.title,
      criteria: role.criteria,
      questions,
      resumeText: candidateContext.resumeText,
    });

    const interview = await createInterview({
      id,
      candidateName: candidateContext.name,
      roleId: role.id,
      roleTitle: role.title,
      criteria: role.criteria,
      questions,
      resumeText: candidateContext.resumeText,
      candidateContext,
      candidateId: resolvedCandidateId,
      instructions,
      createdAt: new Date().toISOString(),
      transcript: [],
      summary: null,
    });

    res.json({
      id: interview.id,
      candidateName: interview.candidateName,
      roleTitle: interview.roleTitle,
      questions: interview.questions,
      instructions: interview.instructions,
      candidateContext: interview.candidateContext,
      transcriptionKeywords,
      model: process.env.REALTIME_MODEL || "gpt-realtime",
      interviewerName,
      interviewerTitle,
      demo: isDemo,
    });
  } catch (err) {
    console.error("Start interview error:", err);
    res.status(500).json({ error: "Failed to start interview" });
  }
});

router.get("/:id", async (req, res) => {
  const interview = await getInterview(req.params.id);
  if (!interview) {
    res.status(404).json({ error: "Interview not found" });
    return;
  }
  res.json(interview);
});

export default router;
