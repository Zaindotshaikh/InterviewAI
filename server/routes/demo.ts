import { Router } from "express";
import { v4 as uuidv4 } from "uuid";
import { loadDemoCatalog } from "../lib/demoCatalog.js";
import { createDemoLead, updateDemoLead } from "../lib/store.js";

const router = Router();

router.get("/catalog", async (_req, res) => {
  try {
    const catalog = await loadDemoCatalog();
    res.json(catalog);
  } catch (err) {
    console.error("Failed to load demo catalog:", err);
    res.status(500).json({ error: "Failed to load demo catalog" });
  }
});

router.post("/leads", async (req, res) => {
  const body = req.body as {
    name?: string;
    email?: string;
    company?: string;
    industry?: string;
  };

  const name = body.name?.trim() ?? "";
  const email = body.email?.trim() ?? "";
  const company = body.company?.trim() ?? "";
  const industry = body.industry?.trim() ?? "";

  if (!name || !email || !company || !industry) {
    res.status(400).json({ error: "name, email, company, and industry are required" });
    return;
  }

  try {
    const lead = await createDemoLead({
      id: uuidv4(),
      name,
      email,
      company,
      industry,
      createdAt: new Date().toISOString(),
    });
    res.json(lead);
  } catch (err) {
    console.error("Failed to save demo lead:", err);
    res.status(500).json({ error: "Failed to save demo lead" });
  }
});

router.patch("/leads/:id", async (req, res) => {
  const body = req.body as {
    roleId?: string;
    roleTitle?: string;
    interviewId?: string;
  };

  try {
    const updated = await updateDemoLead(req.params.id, {
      roleId: body.roleId,
      roleTitle: body.roleTitle,
      interviewId: body.interviewId,
    });
    if (!updated) {
      res.status(404).json({ error: "Lead not found" });
      return;
    }
    res.json(updated);
  } catch (err) {
    console.error("Failed to update demo lead:", err);
    res.status(500).json({ error: "Failed to update demo lead" });
  }
});

export default router;
