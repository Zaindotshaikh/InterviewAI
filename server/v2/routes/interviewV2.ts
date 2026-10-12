import { Router } from "express";
import { v4 as uuidv4 } from "uuid";
import OpenAI from "openai";
import { buildCandidateContext, type CandidateContext } from "../../lib/candidateContext.js";
import { listRoles } from "../../lib/store.js";
import { demoRoleAsConfig, findDemoRole, loadDemoCatalog } from "../../lib/demoCatalog.js";
import { buildResumeQuestionsPrompt } from "../../prompts/resumeQuestions.js";
import { buildScorecardPrompt } from "../../prompts/scorecard.js";
import { inferSeniority, type InterviewSeniority } from "../../prompts/interviewer.js";
import { buildInterviewPlan } from "../lib/planBuilder.js";
import { blueprintTargetMinutes, loadBlueprint } from "../lib/blueprint.js";
import {
  buildClassificationPrompt,
  finalizeModelTier,
  precheck,
  screeningFacts,
  summarizeAreas,
} from "../lib/classification.js";
import {
  createCandidateToken,
  ensureRoomAndDispatch,
  isLiveKitConfigured,
  roomNameForInterview,
} from "../lib/livekit.js";
import {
  createV2Interview,
  getV2Interview,
  saveEnglishTranscript,
  saveV2Summary,
} from "../lib/v2Store.js";
import { withV2StartSlot } from "../lib/concurrency.js";
import { startInterviewRecording } from "../lib/recording.js";
import { SUPPORTED_LANGUAGES, type InterviewLanguageCode } from "../lib/types.js";

const router = Router();

function parseCandidateContext(body: {
  candidateContext?: Partial<CandidateContext>;
  candidateName?: string;
  roleTitle?: string;
  resumeText?: string;
  email?: string;
  noticePeriod?: string;
  currentCompany?: string;
  yearsOfExperience?: string;
}, opts: { requireResume?: boolean } = {}): CandidateContext | null {
  const nested = body.candidateContext;
  const name = (nested?.name ?? body.candidateName ?? "").trim();
  const roleAppliedFor = (nested?.roleAppliedFor ?? body.roleTitle ?? "").trim();
  const resumeText = (nested?.resumeText ?? body.resumeText ?? "").trim();
  if (!name || !roleAppliedFor) return null;
  // The v2 flow runs from the role blueprint; a resume is optional background.
  if (opts.requireResume && !resumeText) return null;
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

function isLanguage(value: unknown): value is InterviewLanguageCode {
  return typeof value === "string" && SUPPORTED_LANGUAGES.some((l) => l.code === value);
}

router.get("/languages", (_req, res) => {
  res.json({ languages: SUPPORTED_LANGUAGES });
});

router.get("/health", (_req, res) => {
  res.json({
    ok: true,
    pipeline: "v2",
    livekitConfigured: isLiveKitConfigured(),
    providerMode: process.env.PROVIDER_MODE || "openai",
    hasOpenAI: Boolean(process.env.OPENAI_API_KEY),
    hasSarvam: Boolean(process.env.SARVAM_API_KEY),
    hasTavus: Boolean(process.env.TAVUS_API_KEY),
  });
});

router.post("/generate-questions", async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "OPENAI_API_KEY not configured" });
    return;
  }

  try {
    const body = req.body as {
      candidateContext?: Partial<CandidateContext>;
      roleCriteria?: string[];
      seniority?: InterviewSeniority;
      candidateName?: string;
      roleTitle?: string;
      resumeText?: string;
    };
    const candidateContext = parseCandidateContext(body, { requireResume: true });
    if (!candidateContext) {
      res.status(400).json({ error: "candidateContext (name, roleAppliedFor, resumeText) is required" });
      return;
    }

    const criteria = Array.isArray(body.roleCriteria) ? body.roleCriteria : [];
    const seniority =
      body.seniority === "senior" || body.seniority === "mid" || body.seniority === "junior"
        ? body.seniority
        : undefined;

    const openai = new OpenAI({ apiKey });
    const completion = await openai.chat.completions.create({
      model: process.env.CHAT_MODEL || "gpt-4o",
      temperature: 0.4,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: "You prepare resume-specific interview questions. Return ONLY valid JSON matching the requested schema.",
        },
        {
          role: "user",
          content: buildResumeQuestionsPrompt({
            roleTitle: candidateContext.roleAppliedFor,
            criteria,
            candidateContext,
            seniority,
          }),
        },
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
    console.error("[v2] generate-questions error:", err);
    res.status(500).json({ error: "Failed to generate resume questions" });
  }
});

router.post("/start", async (req, res) => {
  try {
    const body = req.body as {
      roleId?: string;
      language?: string;
      resumeQuestions?: string[];
      candidateId?: string;
      candidateContext?: Partial<CandidateContext>;
      candidateName?: string;
      roleTitle?: string;
      resumeText?: string;
      email?: string;
      noticePeriod?: string;
      currentCompany?: string;
      yearsOfExperience?: string;
      recordingConsent?: boolean;
      demo?: boolean;
      avatar?: boolean;
      /** Opt-in TTS override for A/B routes (e.g. "elevenlabs"). */
      ttsProvider?: string;
    };

    if (!body.roleId) {
      res.status(400).json({ error: "roleId is required" });
      return;
    }
    if (!isLanguage(body.language)) {
      res.status(400).json({
        error: "language is required",
        supported: SUPPORTED_LANGUAGES.map((l) => l.code),
      });
      return;
    }

    const candidateContext = parseCandidateContext(body);
    if (!candidateContext) {
      res.status(400).json({ error: "candidateContext (name, roleAppliedFor) is required" });
      return;
    }
    // body.resumeQuestions is accepted for older clients and ignored: the agent decides what to ask.

    const roles = await listRoles();
    let role = roles.find((r) => r.id === body.roleId) ?? null;
    let interviewerName = process.env.INTERVIEWER_NAME || "Aven";
    let interviewerTitle = "Senior Interview Partner";

    if (!role) {
      const demoRole = await findDemoRole(body.roleId);
      if (demoRole) {
        role = demoRoleAsConfig(demoRole);
        const catalog = await loadDemoCatalog();
        interviewerName = catalog.interviewer.name;
        interviewerTitle = catalog.interviewer.title;
      }
    }

    if (!role) {
      res.status(404).json({ error: `Role not found: ${body.roleId}` });
      return;
    }

    const interviewId = uuidv4();
    const roomName = roomNameForInterview(interviewId);
    const companyName = process.env.COMPANY_NAME || "Kreeda Labs";
    const blueprint = await loadBlueprint();
    const targetMinutes = blueprintTargetMinutes(blueprint);
    const providerMode = process.env.PROVIDER_MODE || "openai";

    const plan = await buildInterviewPlan({
      interviewId,
      language: body.language,
      companyName,
      interviewerName,
      roleTitle: role.title,
      criteria: role.criteria,
      candidateContext,
      targetMinutes,
    });

    const now = new Date().toISOString();
    const recordingConsent = Boolean(body.recordingConsent);
    const avatar = Boolean(body.avatar);
    const ttsProvider =
      typeof body.ttsProvider === "string" && body.ttsProvider.trim()
        ? body.ttsProvider.trim().toLowerCase()
        : undefined;

    await createV2Interview(
      {
        id: interviewId,
        candidateName: candidateContext.name,
        roleId: role.id,
        roleTitle: role.title,
        criteria: role.criteria,
        questions: [],
        resumeText: candidateContext.resumeText,
        candidateContext,
        candidateId: body.candidateId,
        instructions: plan.systemPrompt,
        createdAt: now,
        transcript: [],
        summary: null,
      },
      {
        pipeline: "v2",
        language: body.language,
        plan,
        controller: {
          stepIndex: 0,
          followUpsUsed: 0,
          consecutiveNoise: 0,
          consecutiveWeak: 0,
          language: body.language,
          startedAt: now,
          lastTurnAt: null,
          completed: false,
          recordingConsent,
        },
        events: [
          {
            ts: now,
            type: "interview.created",
            data: { language: body.language, providerMode, avatar, ttsProvider },
          },
        ],
        roomName,
        providerMode,
        recordingConsent,
        avatar,
        ttsProvider,
      },
    );

    let livekit: { url: string; token: string; agentName: string } | null = null;
    if (isLiveKitConfigured()) {
      console.info(`[v2] start interview=${interviewId} avatar=${avatar} tts=${ttsProvider || "default"}`);
      // Stagger room/dispatch creation to avoid Sarvam/LiveKit connection bursts
      livekit = await withV2StartSlot(async () => {
        await ensureRoomAndDispatch({ roomName, interviewId, avatar, ttsProvider });
        if (recordingConsent) {
          await startInterviewRecording({ roomName, interviewId });
        }
        const tok = await createCandidateToken({
          roomName,
          identity: `candidate-${interviewId.slice(0, 8)}`,
          interviewId,
          avatar,
          ttsProvider,
          metadata: { language: body.language, recordingConsent, avatar, ttsProvider },
        });
        return { url: tok.url, token: tok.token, agentName: tok.agentName };
      });
    }

    res.json({
      id: interviewId,
      pipeline: "v2",
      candidateName: candidateContext.name,
      roleTitle: role.title,
      language: body.language,
      questions: [],
      interviewerName,
      interviewerTitle,
      targetMinutes,
      roomName,
      livekit,
      livekitConfigured: isLiveKitConfigured(),
      providerMode,
      avatar,
      ttsProvider,
      planStepCount: plan.steps.length,
      seniority: inferSeniority(role.title),
    });
  } catch (err) {
    console.error("[v2] start error:", err);
    res.status(500).json({ error: "Failed to start v2 interview" });
  }
});

router.get("/:id", async (req, res) => {
  try {
    const record = await getV2Interview(req.params.id);
    if (!record) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }
    res.json({
      id: record.interview.id,
      candidateName: record.interview.candidateName,
      roleTitle: record.interview.roleTitle,
      language: record.extras.language,
      controller: record.extras.controller,
      transcriptLength: record.interview.transcript.length,
      completed: record.extras.controller.completed,
      summary: record.interview.summary,
      roomName: record.extras.roomName,
      providerMode: record.extras.providerMode,
    });
  } catch (err) {
    console.error("[v2] get error:", err);
    res.status(500).json({ error: "Failed to load interview" });
  }
});

router.post("/:id/summary", async (req, res) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "OPENAI_API_KEY not configured" });
    return;
  }

  try {
    const record = await getV2Interview(req.params.id);
    if (!record) {
      res.status(404).json({ error: "Interview not found" });
      return;
    }

    const transcript = record.interview.transcript;
    if (!transcript.length) {
      res.status(400).json({ error: "No transcript available to score" });
      return;
    }

    const openai = new OpenAI({ apiKey });

    // English-normalize non-English turns for TA scorecards
    const needsTranslate = record.extras.language !== "en-IN";
    let scoringTranscript = transcript;

    if (needsTranslate) {
      const translateCompletion = await openai.chat.completions.create({
        model: process.env.CHAT_MODEL || "gpt-4o",
        temperature: 0.2,
        response_format: { type: "json_object" },
        messages: [
          {
            role: "system",
            content:
              "Translate interview turns to clear English for a hiring scorecard. Preserve meaning. Return JSON { turns: [{ role, text, timestamp }] }.",
          },
          {
            role: "user",
            content: JSON.stringify({
              sourceLanguage: record.extras.language,
              turns: transcript,
            }),
          },
        ],
      });
      const raw = translateCompletion.choices[0]?.message?.content ?? "{}";
      const parsed = JSON.parse(raw) as {
        turns?: { role: "user" | "assistant"; text: string; timestamp: string }[];
      };
      if (Array.isArray(parsed.turns) && parsed.turns.length) {
        scoringTranscript = parsed.turns;
        await saveEnglishTranscript(req.params.id, parsed.turns);
      }
    }

    const flow = record.extras.controller.flow;
    if (flow && record.extras.plan.version >= 2) {
      const bp = record.extras.plan.blueprint ?? (await loadBlueprint());
      let tier = precheck(flow, bp);
      let model: Record<string, unknown> = {};
      if (!tier) {
        const completion = await openai.chat.completions.create({
          model: process.env.CLASSIFIER_MODEL || process.env.CHAT_MODEL || "gpt-4o",
          temperature: 0.1,
          response_format: { type: "json_object" },
          messages: [
            {
              role: "system",
              content:
                "You classify nursing candidates for a hiring team from interview evidence. Return ONLY valid JSON matching the requested schema.",
            },
            {
              role: "user",
              content: buildClassificationPrompt({
                roleTitle: record.interview.roleTitle,
                candidateName: record.interview.candidateName,
                bp,
                flow,
              }),
            },
          ],
        });
        model = JSON.parse(completion.choices[0]?.message?.content ?? "{}") as Record<string, unknown>;
        const haystacks = [
          ...transcript.map((t) => t.text),
          ...scoringTranscript.map((t) => t.text),
          ...Object.values(flow.areas ?? {}).flatMap((a) =>
            (a.evidence ?? []).flatMap((e) => [e.quote ?? "", e.summary ?? ""]),
          ),
        ];
        tier = finalizeModelTier(model, flow, bp, haystacks);
      }

      const areas = summarizeAreas(flow, bp);
      const scoreByTier: Record<string, number | null> = {
        tier_1: 9,
        tier_2: 7,
        tier_3: 5,
        not_eligible: 2,
        needs_review: null,
      };
      const modelScore = Number(model.overall_score);
      const strList = (v: unknown) => (Array.isArray(v) ? v.filter((s): s is string => typeof s === "string") : []);
      const payload = {
        // Legacy scorecard fields, so existing dashboards keep working.
        overall_score:
          tier.method === "model" && Number.isFinite(modelScore)
            ? Math.min(10, Math.max(1, Math.round(modelScore)))
            : (scoreByTier[tier.tier] ?? null),
        recommendation: `${tier.tier_name}. ${tier.reasoning}`,
        strengths: strList(model.strengths),
        gaps: strList(model.gaps),
        per_question_notes: areas.map((a) => ({
          question: a.title,
          note: `${a.outcome}${a.evidence.length ? `. ${a.evidence.map((e) => e.summary).filter(Boolean).join(" ")}` : ""}`,
        })),
        // Classification with reasoning and evidence.
        tier: tier.tier,
        tier_name: tier.tier_name,
        tier_confidence: tier.confidence,
        tier_reasoning: tier.reasoning,
        tier_method: tier.method,
        tier_evidence: tier.evidence,
        flags: tier.flags,
        screening: screeningFacts(flow),
        clinical_areas: areas,
        contradictions: flow.contradictions ?? [],
        outcome: flow.outcome,
        pipeline: "v2",
        language: record.extras.language,
        integrity: record.interview.integrity ?? { available: false, events: [] },
      };
      await saveV2Summary(req.params.id, payload);
      res.json(payload);
      return;
    }

    const prompt = buildScorecardPrompt({
      roleTitle: record.interview.roleTitle,
      candidateName: record.interview.candidateName,
      criteria: record.interview.criteria,
      transcript: scoringTranscript,
    });

    const completion = await openai.chat.completions.create({
      model: process.env.CHAT_MODEL || "gpt-4o",
      temperature: 0.3,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: "You score completed job interviews. Return ONLY valid JSON matching the requested schema.",
        },
        { role: "user", content: prompt },
      ],
    });

    const summary = JSON.parse(completion.choices[0]?.message?.content ?? "{}") as Record<string, unknown>;
    const payload = {
      ...summary,
      pipeline: "v2",
      language: record.extras.language,
      integrity: record.interview.integrity ?? { available: false, events: [] },
    };
    await saveV2Summary(req.params.id, payload);
    res.json(payload);
  } catch (err) {
    console.error("[v2] summary error:", err);
    res.status(500).json({ error: "Failed to generate scorecard" });
  }
});

export default router;
