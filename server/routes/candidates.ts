import { Router } from "express";
import { v4 as uuidv4 } from "uuid";
import {
  createCandidate,
  getCandidate,
  listCandidates,
  listRoles,
  updateCandidate,
} from "../lib/store.js";

const router = Router();

function optionalString(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

router.get("/", async (_req, res) => {
  try {
    const candidates = await listCandidates();
    res.json(candidates);
  } catch (err) {
    console.error("List candidates error:", err);
    res.status(500).json({ error: "Failed to list candidates" });
  }
});

router.get("/:id", async (req, res) => {
  const candidate = await getCandidate(req.params.id);
  if (!candidate) {
    res.status(404).json({ error: "Candidate not found" });
    return;
  }
  res.json(candidate);
});

/** TA "Add Candidate": persists all filled fields for later interview start. */
router.post("/", async (req, res) => {
  try {
    const body = req.body as {
      name?: string;
      roleId?: string;
      email?: string;
      noticePeriod?: string;
      currentCompany?: string;
      yearsOfExperience?: string;
      resumeText?: string;
    };

    if (!body.name?.trim() || !body.roleId) {
      res.status(400).json({ error: "name and roleId are required" });
      return;
    }

    const roles = await listRoles();
    const role = roles.find((r) => r.id === body.roleId);
    if (!role) {
      res.status(404).json({ error: "Role not found" });
      return;
    }

    const candidate = await createCandidate({
      id: uuidv4(),
      name: body.name.trim(),
      roleId: role.id,
      roleAppliedFor: role.title,
      email: optionalString(body.email),
      noticePeriod: optionalString(body.noticePeriod),
      currentCompany: optionalString(body.currentCompany),
      yearsOfExperience: optionalString(body.yearsOfExperience),
      resumeText: optionalString(body.resumeText),
      createdAt: new Date().toISOString(),
    });

    res.status(201).json(candidate);
  } catch (err) {
    console.error("Create candidate error:", err);
    res.status(500).json({ error: "Failed to create candidate" });
  }
});

router.patch("/:id", async (req, res) => {
  try {
    const body = req.body as Record<string, unknown>;
    const patch: Record<string, string | undefined> = {};

    for (const key of [
      "name",
      "email",
      "noticePeriod",
      "currentCompany",
      "yearsOfExperience",
      "resumeText",
    ] as const) {
      if (key in body) patch[key] = optionalString(body[key]);
    }

    if (typeof body.roleId === "string") {
      const roles = await listRoles();
      const role = roles.find((r) => r.id === body.roleId);
      if (!role) {
        res.status(404).json({ error: "Role not found" });
        return;
      }
      patch.roleId = role.id;
      patch.roleAppliedFor = role.title;
    }

    const updated = await updateCandidate(req.params.id, patch);
    if (!updated) {
      res.status(404).json({ error: "Candidate not found" });
      return;
    }
    res.json(updated);
  } catch (err) {
    console.error("Update candidate error:", err);
    res.status(500).json({ error: "Failed to update candidate" });
  }
});

export default router;
