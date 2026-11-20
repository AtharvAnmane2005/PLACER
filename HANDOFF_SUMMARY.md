# PLACER — Project Handoff Summary

**Purpose of this document:** let a new maintainer continue the project without
re-deriving decisions. It reflects the **current implemented codebase**, not the
original phase plan.

| Field | Value |
|---|---|
| Project | PLACER — AI-Powered Campus Recruitment & Placement Assistance System |
| Repository root | `PLACER/` |
| Stack | FastAPI + MongoDB backend; Next.js 15 + React 19 frontend |
| Status | All feature phases implemented; Phase 17 deployment documented but not provisioned; 331 backend tests collected |
| Canonical quickstart | [`README.md`](./README.md) |
| End-to-end behaviour | [`docs/SYSTEM_FLOW.md`](./docs/SYSTEM_FLOW.md) |
| Detailed design | [`docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md`](./docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md) |
| Formulas | [`docs/PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md`](./docs/PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md) |
| Seed dataset | [`docs/SEED_DATA.md`](./docs/SEED_DATA.md) |
| Local logins | [`credentials.md`](./credentials.md) (git-ignored) |

---

## 1. What the system is

PLACER supports campus placement end to end for three roles:

- **Students** build a profile, upload and parse a resume, browse eligible
  drives, see match scores, apply, take assessments, and read AI coaching.
- **TPOs** create and publish drives, attach a standardized assessment, screen
  applicants, shortlist/reject, and monitor analytics, market demand, and skill
  gaps.
- **Admins** own the question bank, assessment templates and placement-paper
  generation, platform analytics, the cross-drive applications workspace, RAG
  knowledge ingest, and LLM observability.

There are exactly three roles (`student`, `tpo`, `admin`). Admin accounts are
created only with `backend/scripts/create_admin.py`; there is no public admin
registration route.

---

## 2. Current architecture

```text
Browser (Next.js :3000)
  └─ /api/backend/*  →  rewrite  →  FastAPI :8000 /api/v1/*
                                     ├─ routers/        HTTP, auth guards, validation
                                     ├─ services/       business logic, orchestration
                                     ├─ repositories/   one class per collection
                                     ├─ ml/             parsing/OCR, matching, LLM, RAG
                                     └─ core/           config, DB, security, deps, limiter
                                     ▼
                                  MongoDB 7 :27017 / placer_db
                                     ▲
Optional external providers: LLM chat + embeddings, Google Identity, Cloudinary
Optional judge container: internal judge_net, no published port
```

Key request path: axios wrapper → Next.js same-origin rewrite →
`RequestIdMiddleware` → CORS → `get_current_user` / `require_role(...)` → router
→ service → repository → MongoDB. A `401` triggers one refresh-and-retry.

**Layering rules**
- Routers stay thin; business logic lives in `app/services/`.
- One repository per collection; services do not query Motor directly.
- LLMs narrate already-computed values and never invent scores.
- AI failures fail soft: deterministic fallbacks or a clear `503`.

---

## 3. Implemented feature inventory

### Auth and identity
- Student/TPO registration, login, refresh rotation, logout, forgot/reset
  password, Google Sign-In, `/auth/me`.
- JWT access token in memory (15 min), rotating httpOnly refresh cookie (7 days),
  RBAC at the dependency layer.
- Separate `users` auth identity and `students` / `tpos` / `admins` profiles.
  Operational records use the **profile** `_id`, not `users._id`.

### Resume and profile
- PDF upload with size cap, `%PDF` check, SHA-256 dedupe, versioning, one active
  resume per student.
- Synchronous parse: PyMuPDF → pdfplumber → PaddleOCR → regex sections → spaCy →
  LLM skill extraction with regex fallback.
- Parsed preview, download, reparse, autofill suggestion and apply.
- Shared 135-skill / 235-alias taxonomy.

### Matching and AI
- Fine-tuned bi-encoder retrieval → cross-encoder reranking → Platt calibration.
- Hybrid score: `0.40·semantic + 0.30·skills + 0.20·experience + 0.10·assessment`.
  Assessment term is `1.0` when no assessment is required or not yet scored.
- Cached resume/JD embeddings; drive edits invalidate the JD embedding.
- Grounded LLM/RAG narratives for application explanation, JD match explanation,
  student insights, and attempt gap analysis.
- MongoDB cosine knowledge store; LLM/embedding metrics at
  `GET /admin/observability/llm`.

### Drives, applications, screening
- Drive CRUD, clone, open/close, JD, required skills, eligibility (CGPA,
  department, batch), deadline, linked standardized assessment.
- Opening a drive requires a required assessment; removing it from an open drive
  is blocked (`ASSESSMENT_REQUIRED_FOR_PUBLISH`).
- Apply with eligibility gate; unique `(drive_id, student_id)`.
- Screening recomputes match scores, reconciles assessment pass/fail, and never
  changes shortlist/reject automatically.
- Recommended shortlist, bulk status updates, CSV export.
- Canonical statuses: `applied`, `shortlisted`, `rejected`; legacy `selected`
  is mapped to `shortlisted` at read time.

### Assessments and grading
- Adaptive practice papers and standardized drive papers.
- Standardized papers: 5 sections, 20 questions, 6/10/4 difficulty quota,
  1/3/5 marks, 30-minute timer in seeded drives, 56 marks, pass 28.
- Templates and presets, placement generation/revision/participation.
- Attempt lifecycle: start → one-question-at-a-time answers → finish → results.
- Grading: MCQ exact match, multiple-select all-or-nothing, coding all tests
  pass, descriptive manual/API-only.
- Negative marking only on standardized assessments, only for wrong
  auto-gradable answers.
- Knowledge tracing uses an EMA heuristic, not full BKT.
- Anti-cheat: session token, server timer, auto-submit, randomized options,
  violation logging, configurable threshold.
- Coding execution: Python/JS subprocess runner, local or isolated judge.

### Analytics and insight
- Student dashboard, applications, results, mastery, insights; per-attempt gap
  analysis is API-only.
- TPO analytics: applications, drive funnels, departments, companies,
  participation, assessment ranking, skill gaps.
- Market Insights: 7,469 postings, demand, momentum, filters, comparison,
  import-run provenance.
- Admin analytics and activity summary, cross-drive applications workspace.

### Question bank and admin
- 500 seeded questions across 13 categories: 420 MCQ, 60 coding, 20
  descriptive; 150 easy / 225 medium / 125 hard.
- CRUD, categories, stats, Excel/CSV preview + commit, error report, exports.
- Coding questions store visible and hidden tests; hidden tests and reference
  solutions never reach the browser.
- Assessment templates and standardized generation.

---

## 4. Data model essentials

24 collections in `placer_db`. The important relationships:

```text
users 1──1 students | tpos | admins          (by user_id)
students 1──* resumes                         (by student profile _id)
students 1──* applications                    (by student profile _id)
placement_drives 1──* applications             (by drive_id)
placement_drives *──1 companies                (by company_id)
assessments 1──* assessment_attempts           (by assessment_id)
students 1──* knowledge_states                 (by student_id, skill_tag)
```

Collections: `users`, `refresh_tokens`, `password_reset_tokens`, `students`,
`tpos`, `admins`, `resumes`, `placement_drives`, `companies`, `applications`,
`question_categories`, `questions`, `assessments`, `assessment_templates`,
`assessment_attempts`, `knowledge_states`, `activity_logs`, `notifications`
(index-only/unused), `unmapped_skill_suggestions`, `knowledge_chunks`,
`insights_narrative_cache`, `job_market_postings`, `market_skill_catalog`,
`market_import_runs`.

**Most common bug source:** confusing `users._id` with the profile `_id`. Always
resolve through `StudentRepository.get_by_user_id()` (or the TPO/admin
equivalent) before writing operational records.

Seeded documents carry `data_origin`, `is_synthetic`, and `synthetic_batch`.
These are internal audit fields, not user-facing labels.

---

## 5. Environment and commands

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m spacy download en_core_web_sm
copy .env.example .env
# set JWT_SECRET_KEY

# Admin (one-time)
.venv\Scripts\python.exe -m scripts.create_admin

# Seed (optional, recommended)
.venv\Scripts\python.exe -m scripts.reset_db --yes
.venv\Scripts\python.exe -m scripts.seed.run_all
.venv\Scripts\python.exe -m scripts.seed.run_all --verify-only

# Tests
.venv\Scripts\python.exe -m pytest -q        # 331 tests

# Run
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
# Frontend
cd frontend
npm install
copy .env.local.example .env.local
npm run dev                                   # http://localhost:3000
```

```powershell
# Full stack + judge
docker compose build
docker compose up -d
docker compose ps
```

Seeded logins use password **`Placer@2026`** by default:

| Role | Email |
|---|---|
| Admin | `admin@placer.edu` |
| TPO | `tpo@placer.edu` |
| Students | `student01@placer.edu` … `student50@placer.edu` |

Model weights: place `model.safetensors` under
`backend/app/ml/matching/artifacts/bi_encoder/` and
`backend/app/ml/matching/artifacts/cross_encoder/`. Without them the app runs
and match endpoints return `503`.

LLM/embeddings are optional. Set a hosted provider key, or run Ollama with
`LLM_USE_LOCAL_OLLAMA=true`. Deterministic fallbacks apply when unavailable.

---

## 6. Key decisions to preserve

1. **Profile ID, not user ID.** Operational collections reference the student
   profile `_id`. Resolve through repositories.
2. **Never write Pydantic model instances straight into Mongo.** Use
   `.model_dump(mode="json")` when appending fetched model objects to list
   fields.
3. **Repository pattern throughout.** `BaseRepository[ModelT]` provides CRUD;
   services never touch Motor directly.
4. **Auth token split.** Access token in memory only; refresh token in an
   httpOnly cookie that rotates on every use.
5. **Storage abstraction.** Local disk or Cloudinary selected by
   `STORAGE_BACKEND`; the DB stores `local://` pseudo-URLs, never absolute paths.
6. **Parsing degrades gracefully.** spaCy is optional at runtime; OCR is
   config-gated; LLM skill extraction falls back to regex.
7. **Knowledge tracing is EMA, not BKT.** Chosen because calibrated BKT
   parameters need real usage data the project does not have.
8. **Adaptive assessment** starts at Medium, steps up on correct and down on
   wrong, with fallback when a difficulty pool is exhausted.
9. **Grading boundaries.** MCQ automatic, coding via the runner/judge,
   descriptive stored ungraded for manual/API review.
10. **Anti-cheat is partially server-side.** Timers and violations are recorded;
    fullscreen and fingerprint are not enforced server-side.
11. **Question sourcing is local.** No web scraping or trivia API; manual bulk
    import is the supported path.
12. **AI never invents numbers.** Prompts receive computed values and narrate
    them; fallbacks preserve deterministic data.
13. **Provenance is internal.** `data_origin` / `is_synthetic` support audit but
    are not rendered as demo labels (the Market Insights source banner is the
    deliberate exception).

---

## 7. Known limitations

- Live deployment (Vercel/Render/Atlas) is documented but not provisioned.
- Matching needs external model weights; otherwise match endpoints `503`.
- LLM/RAG needs provider keys or Ollama; deterministic fallbacks otherwise.
- The local code runner is not a hardened sandbox — use the judge service for
  shared environments.
- Descriptive grading is API-only; the TPO Descriptive Review page was removed.
- Anti-cheat fullscreen/fingerprint checks are not backend-enforced.
- `notifications` is index-only; no notification UI or read/write path.
- The admin applications workspace supports cross-drive records, analytics, and
  status updates, but company CRUD and some admin management screens are not
  implemented.
- Drive deletion does not cascade-delete applications.
- `password_reset_tokens`, `knowledge_chunks`, and
  `insights_narrative_cache` lack explicit startup indexes/TTLs.
- Rate limiting is applied only to selected routes.

The authoritative gap list is
`docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md` §16.

---

## 8. Where to start as the next maintainer

1. Read [`README.md`](./README.md) and run the backend tests.
2. Read [`docs/SYSTEM_FLOW.md`](./docs/SYSTEM_FLOW.md) for behaviour, then the
   detailed design doc for page-by-page flows.
3. Use [`credentials.md`](./credentials.md) to verify each role locally.
4. Before changing a formula, check
   `docs/PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md` and the formula-to-code
   map.
5. Keep the docs in sync: `README.md`, `docs/SYSTEM_FLOW.md`, the design doc,
   the formulas doc, and `docs/SEED_DATA.md` are the current documentation set.

**Useful source-of-truth files**
- `backend/app/main.py` — router registration and middleware.
- `backend/app/core/config.py` — every feature flag.
- `backend/app/services/matching_service.py` — hybrid score.
- `backend/app/services/assessment_service.py` — attempt lifecycle/grading.
- `backend/app/services/screening_service.py` — applicant reconciliation.
- `backend/app/models/assessment.py` — placement sections/quotas/marks.
- `frontend/app/(student|tpo|admin)/layout.tsx` — role navigation.
- `backend/scripts/seed/` — deterministic dataset.
