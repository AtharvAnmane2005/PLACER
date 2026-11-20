# PLACER — System Design and Data Flow

**System:** PLACER — AI-Powered Campus Recruitment & Placement Assistance System
**Document type:** System design, interface inventory, data flow, API reference, deployment
**Status:** Describes the implemented codebase. Features that are partial, API-only, or not implemented are explicitly marked.
**Audience:** Final-year project evaluation, maintainers, reviewers, and future contributors.

| Field | Value |
|---|---|
| Backend | FastAPI (Python 3.12), Motor async MongoDB driver |
| Frontend | Next.js 15.5.18 (App Router), React 19, TypeScript, Tailwind, Recharts 2.15.4 |
| Database | MongoDB 7 (`placer_db`) |
| API prefix | `/api/v1` |
| Default ports | Frontend `3000`, backend `8000`, MongoDB `27017` |
| Repository root | `PLACER/` |

### Companion documents

This document is one of four project documents. They are designed to be read together:

| Document | What it answers |
|---|---|
| [`SYSTEM_FLOW.md`](./SYSTEM_FLOW.md) | How the system behaves end to end: actors, request lifecycle, resume/OCR/matching, drives/applications/screening, assessments/judge/grading, analytics/market/skill gaps/insights, RAG/LLM, and data stores. Start here for behaviour. |
| [`PLACER_SYSTEM_ARCHITECTURE.mmd`](./PLACER_SYSTEM_ARCHITECTURE.mmd) | What the system looks like: architecture, ER model, physical schema, DFD, role workflows, AI model flow (diagram groups A–F). |
| [`PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md`](./PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md) | How every number is computed: formulas, variables, worked examples, implementation status, formula-to-code map. |
| **This document** | How data moves: pages → hooks → endpoints → collections, lifecycles, per-chart processing, API reference, deployment, security. |

Cross-references in this document use the form:

- **Architecture §** → a diagram group in `PLACER_SYSTEM_ARCHITECTURE.mmd` (A–F).
- **Formulas §N** → a numbered section of `PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md`.

> **Rendering note.** GitHub does not render a standalone `.mmd` file, and the groups in it are not meant to be rendered as one combined document because they use different Mermaid diagram types. Each group is a complete, standalone definition: copy the block you need into a Mermaid renderer (mermaid.live, the VS Code Mermaid extension, or `mermaid-cli`). This Markdown document cross-references the groups by letter but does not duplicate them.

---

## 0. How to read this document

1. **§1–§2** give the system and data-store overview.
2. **§3–§5** document the three role interfaces page by page (Student, TPO, Admin). Each page lists its hooks, the exact API calls it makes, and the collections it touches.
3. **§6–§9** describe the write paths and lifecycles: ingestion, the resume/AI pipeline, drive + assessment lifecycle, and application status lifecycle.
4. **§10** explains, chart by chart, how each dashboard number is produced.
5. **§11** is the complete API reference (all 104 route decorators, plus the `/health` alias).
6. **§12–§14** cover MongoDB lifecycle, deployment/runtime, and error handling/security.
7. **§15** is a single end-to-end example, clearly marked as illustrative.
8. **§16** lists every known gap and partial feature.

**Terminology used consistently throughout:**

| Term | Meaning |
|---|---|
| **Drive** | A placement drive (a company hiring for one role), stored in `placement_drives`. |
| **Application** | One student's application to one drive, stored in `applications`. Unique per `(drive_id, student_id)`. |
| **Assessment** | A question set in `assessments`. Either `adaptive` (legacy engine) or `standardized` (fixed question set, used for drive assessments). |
| **Attempt** | One student's run of an assessment, stored in `assessment_attempts`. |
| **Screening** | The TPO action that computes match scores and reconciles assessment outcomes for a drive's applications. |
| **Shortlisting** | Setting an application's status to `shortlisted`. It is **not** a placement/offer record. |
| **Under review** | The `applied` status, displayed as "Applied / Under review". |

**Status vocabulary (enforced):** the only live application statuses are `applied`, `shortlisted`, and `rejected`. The enum still contains the legacy value `selected` for old documents, but no current code path produces it and every read path maps it to `shortlisted` for display and analytics. See §9.3.

---

## 1. System overview

### 1.1 Product purpose and actors

PLACER supports campus placement end to end:

- **Students** build a profile, upload a resume, browse drives, check eligibility and match score, apply, take drive assessments, and read AI-generated coaching.
- **TPOs (Training & Placement Officers)** create and publish drives, attach a standardized assessment, screen applicants, shortlist/reject, and monitor department, company, and drive-level analytics plus market demand.
- **Admins** own the question bank, assessments, templates, drive-assessment generation, platform-wide analytics, and the cross-drive applications workspace.

There are exactly three roles, defined in `backend/app/models/user.py` as `UserRole`: `student`, `tpo`, `admin`. There is **no public admin registration route**; admin accounts are created with `backend/scripts/create_admin.py`.

### 1.2 Runtime topology

```text
Browser
  │  fetch/axios to /api/backend/<path>
  ▼
Next.js server (port 3000)
  │  next.config.mjs rewrite:
  │  /api/backend/:path*  →  ${NEXT_PUBLIC_API_URL}/api/v1/:path*
  ▼
FastAPI (uvicorn, port 8000)
  ├── routers/            HTTP boundary, auth guards, validation
  ├── services/           business logic, aggregation, orchestration
  ├── repositories/       MongoDB access (one class per collection)
  ├── ml/                 parsing, matching, LLM, RAG
  └── core/               config, database, security, deps, limiter, request IDs
  ▼
MongoDB (port 27017, database placer_db)

External providers (optional, config-gated):
  LLM chat (primary + fallback, OpenAI-compatible)
  Embeddings (ollama or OpenAI-compatible)
  Cloudinary (only when STORAGE_BACKEND=cloudinary)
  Google Identity (Sign in with Google)
```

The rewrite exists so the browser sees a same-origin API. That keeps the httpOnly refresh-token cookie same-site and avoids CORS in normal operation. `CORS_ORIGINS` is still configured on the backend for direct access and local tooling.

### 1.3 Technology stack

| Layer | Component | Version / detail |
|---|---|---|
| UI framework | Next.js App Router | 15.5.18 |
| UI runtime | React | 19 |
| Charts | Recharts | 2.15.4 |
| Styling | Tailwind CSS + shadcn-style primitives | `components/ui/*` |
| HTTP client | axios wrapper `lib/api-client.ts` | Access token injected from memory |
| API framework | FastAPI | Python 3.12 |
| ASGI server | uvicorn | `app.main:app` |
| ODM/driver | Motor (async) + Pydantic v2 | `AsyncIOMotorDatabase` |
| Auth | JWT access token + opaque refresh cookie | `core/security.py`, `core/deps.py` |
| Password hashing | bcrypt | `BCRYPT_ROUNDS=12` default |
| Rate limiting | slowapi | Only on selected routes (§14.4) |
| PDF parsing | PyMuPDF (`fitz`) | `app/ml/parsing/parser.py` |
| OCR fallback | PaddleOCR PP-OCRv4 | Config-gated, `OCR_ENABLED` |
| Resume matching | fine-tuned bi-encoder + cross-encoder + Platt calibrator | `app/ml/matching/` |
| LLM | OpenAI-compatible client with primary/fallback | `app/ml/llm/client.py` |
| RAG store | MongoDB cosine similarity | `KNOWLEDGE_STORE_BACKEND=mongodb_cosine` |
| Code execution | Local subprocess runner (Python/JS) | **Not a hardened sandbox** |

### 1.4 Request lifecycle

Every authenticated request follows the same path:

1. **Client.** A hook calls `apiClient`. The access token is read from `lib/token-store.ts` (memory only) and attached as `Authorization: Bearer …`.
2. **Edge.** `next.config.mjs` rewrites `/api/backend/*` to `/api/v1/*` on the backend.
3. **Middleware.** `RequestIdMiddleware` reads or mints `X-Request-ID`, binds it to a context variable, and logs one access line. `CORSMiddleware` applies.
4. **Auth dependency.** `get_current_user` (in `core/deps.py`) decodes the JWT and loads the user; `require_role(...)` enforces the role. Unauthorized → `401`; wrong role → `403`.
5. **Router.** Validates the request with Pydantic, then calls a service.
6. **Service.** Applies business rules, calls repositories and/or ML components.
7. **Repository.** Reads/writes MongoDB through Motor.
8. **Response.** Pydantic response models serialize; errors become `HTTPException` or the global 500 handler.
9. **Client retry.** On `401`, `lib/api-client.ts` calls `/auth/refresh` once and retries the original request. On failure it rejects and the page guard redirects to `/login`.

**Architecture §A** shows this path as layered subgraphs.

### 1.5 Architectural principles and boundaries

- **Routers stay thin.** Business rules live in `services/`; MongoDB queries live in `repositories/`.
- **One collection, one repository.** Repository classes declare `collection_name`.
- **Read-time normalization.** Legacy `selected` status and non-canonical department strings are normalized when read, not rewritten in the database.
- **Provenance is internal.** Documents carry `data_origin` (`"genuine"`, `"mock"`, …) and `is_synthetic`. These fields drive internal audit counts but are **not** rendered as user-facing "demo/synthetic" labels. The one deliberate exception is the Market Insights data-source banner, which describes the imported posting dataset, not fake analytics (§10.6).
- **AI never invents numbers.** LLM services receive already-computed values and narrate them. The system prompt in `application_explanation_service.py` states this explicitly.
- **Fail soft on AI.** Every LLM call has a deterministic fallback (regex skills, template narrative, `503`).

---

## 2. Data stores at a glance

MongoDB database `placer_db`. The startup routine `ensure_indexes()` in `backend/app/core/database.py` creates indexes idempotently. There are **24 collections**.

### 2.1 Collection inventory

| # | Collection | Purpose | Primary writer(s) | Primary reader(s) | Lifecycle notes |
|---|---|---|---|---|---|
| 1 | `users` | Auth identity only: `email`, `password_hash`, `role`, `auth_provider`, `google_sub`, `is_active`, `last_login` | `AuthService` | `AuthService`, `get_current_user` | Unique index on `email`. Profile data is **not** stored here. |
| 2 | `refresh_tokens` | Hashed opaque refresh tokens: `token_hash`, `user_id`, `expires_at`, `revoked` | `AuthService` | `AuthService` | Unique `token_hash`; TTL index on `expires_at` (`expireAfterSeconds=0`). Rotated on every refresh. |
| 3 | `password_reset_tokens` | Hashed reset tokens | `AuthService` | `AuthService` | **No explicit index/TTL created at startup** (see §12.2). |
| 4 | `students` | Student profile: `user_id`, `name`, `department`, `batch_year`, `cgpa`, links, `skills`, `achievements`, `certificates`, `active_resume_id`, `profile_completeness_pct` | `AuthService`, `ProfileAutofillService`, `students` router | Nearly every student-facing service | Unique `user_id`. |
| 5 | `tpos` | TPO profile: `user_id`, `name`, `department_scope` | `AuthService` | `DriveService`, analytics | Unique `user_id`. |
| 6 | `admins` | Admin profile: `user_id`, `name` | `AuthService` (CLI only) | Admin flows | Unique `user_id`. |
| 7 | `resumes` | Versioned resume metadata: `student_id`, `version`, `original_filename`, `file_url`, `file_hash`, `file_size_bytes`, `parsed`, `resume_text`, `skill_set`, `experience_years`, `resume_embedding`, `is_active` | `ResumeService`, `ResumeParsingService`, `MatchingService` | Resume UI, matching, screening, explanation | Indexes on `(student_id,is_active)` and `(student_id,version desc)`. Exactly one active version per student. |
| 8 | `placement_drives` | Drive + JD + eligibility + assessment linkage: `company_id`, `job_title`, `description`, `jd_text`, `jd_embedding`, `required_skills`, `experience_required_years`, `eligibility`, `deadline`, `selection_process`, `status`, `created_by`, `required_assessment_id`, `assessment_min_score_pct`, `assessment_deadline` | `DriveService` | Drive lists, screening, matching, analytics | `status` ∈ `open`/`closed`. Indexes on `(status,deadline)`, `created_by`, `drive_id` for assessments. |
| 9 | `companies` | Company record: `name`, `description`, `website`, `industry` | `DriveService._get_or_create_company` | Drive summaries, analytics, market comparison | Index on `name`. Created on demand; **no company CRUD UI**. |
| 10 | `applications` | One row per `(drive, student)`: status, eligibility result, matching scores, assessment link, rejection reasons, `applied_at`, `decision_at` | `DriveService.apply_to_drive`, screening, status updates | Every analytics endpoint, applications pages | Unique `(drive_id, student_id)`. Index on `(drive_id, final_score desc)`, `student_id`, sparse `assessment_attempt_id`. |
| 11 | `question_categories` | Category tree: `name`, `parent_category_id` | `questions` router | Question bank, placement section resolution | — |
| 12 | `questions` | Question bank: category, skill tags, difficulty, type, text, options, correct answer, coding fields, marks, topic/skill/status/explanation | `questions` router, seed scripts | Assessment generation, attempt questions, grading | Indexes on `(category_id,difficulty)`, `status`, `topic`, `skill`, `type`, `updated_at`. |
| 13 | `assessments` | Assessment definition: type, drive link, question pool, standardized fields (`format`, `status`, `question_ids`, `sections`, `total_marks`, `passing_marks`, `negative_marks`, `allow_retake`, `randomize_options`) | `assessments` router, `PlacementAssessmentService` | Attempt start, TPO linkage, ranking | Indexes on `drive_id` (sparse), `(format,status)`. |
| 14 | `assessment_templates` | Reusable config: sections, difficulty distribution, question types, topics, skills, totals, status, `preset_key` | `assessments` templates routes | Admin template UI, placement generation | Indexes on `status`, sparse `preset_key`. |
| 15 | `assessment_attempts` | Attempt: `assessment_id`, `student_id`, `session_token`, `asked_question_ids`, `answers`, `violations`, `status`, timestamps, `ip_address`, `fingerprint_hash` | `AssessmentService` | Results, ranking, analytics, gap analysis | Indexes on `(student_id,started_at desc)`, `assessment_id`, `(assessment_id,student_id)`, `(assessment_id,student_id,status)`. |
| 16 | `knowledge_states` | Per-student, per-skill mastery: `mastery_pct`, `confidence`, `attempts_count`, `history` | `AssessmentService` finalize | Knowledge-state endpoints, insights | Unique `(student_id, skill_tag)`. |
| 17 | `activity_logs` | Audit events: `user_id`, `action`, `entity`, `entity_id`, `metadata`, `ip_address`, `timestamp` | `ActivityLogRepository` | Admin activity feed | Indexes on `(user_id,timestamp desc)`, `(entity,entity_id)`. |
| 18 | `notifications` | **Index only, unused.** No read/write code exists. | — | — | Index on `(user_id,read,created_at desc)`. Flagged in §16. |
| 19 | `unmapped_skill_suggestions` | LLM-found skill phrases outside the 50-term vocabulary; admin review queue (`reviewed=false`) | `UnmappedSkillRepository` | Intended admin review (no UI) | De-duplicated per source. |
| 20 | `knowledge_chunks` | RAG chunks + embeddings for coach narratives | `knowledge_admin` ingest, seed script | `KnowledgeStore` | **No explicit index created at startup** (see §12.2). |
| 21 | `insights_narrative_cache` | Cached LLM narratives keyed by student/context | `StudentInsightsService` | `StudentInsightsService` | **No explicit index created at startup.** |
| 22 | `job_market_postings` | Imported historical postings for Market Insights | `seed_job_market.py`, `import_job_market.py` | `MarketAnalyticsService`, `SkillGapService` | Many indexes; see §12.2. |
| 23 | `market_skill_catalog` | Skill slug/name/category catalog | Seed/import scripts | Market + skill-gap services | Unique `slug`. |
| 24 | `market_import_runs` | Metadata for each import run | Import script | Market meta banner | — |

### 2.2 Identity model

```text
users (auth)  1 ──── 1  students | tpos | admins   (by user_id)
students      1 ──── *  resumes                   (by student_id = student profile _id)
students      1 ──── *  applications              (by student_id = student profile _id)
placement_drives 1 ── * applications              (by drive_id)
placement_drives * ── 1 companies                 (by company_id)
assessments   1 ──── *  assessment_attempts       (by assessment_id)
students      1 ──── *  knowledge_states          (by student_id, skill_tag)
```

**Critical ID distinction:** `users._id` is the auth identity. `students._id`, `tpos._id`, and `admins._id` are profile identities. Everything operational (applications, attempts, resumes, knowledge states) is keyed by the **profile** `_id`, not the user `_id`. Services such as `AssessmentService._resolve_student_id()` and `DriveService` translate between them. Mixing the two is the most common source of "not found" bugs in this codebase.

**Architecture §B** is the ER diagram; **Architecture §C** is the physical schema.

### 2.3 Provenance fields

`MongoBaseModel` in `backend/app/models/base.py` gives every document:

- `data_origin: str = "genuine"`
- `is_synthetic: bool = False`

Seed scripts set these so imported/demo records can be audited. Analytics responses expose internal counters such as `synthetic_application_count` and `legacy_selected`, but the UI does not render "demo", "synthetic", or "dummy" labels. Provenance is an internal audit signal only.

---

## 3. Interface A — Student

The student shell is `frontend/app/(student)/layout.tsx`, with navigation and a client-side role backstop. `middleware.ts` also redirects unauthenticated or wrong-role users before render.

### 3.1 Route map

| # | Route | Purpose |
|---|---|---|
| 1 | `/dashboard` | Overview: resume state, application funnel, domain radar, assessment trend |
| 2 | `/dashboard/drives` | Browse open drives + recommended drives |
| 3 | `/dashboard/drives/[id]` | Drive detail, eligibility, match score, apply |
| 4 | `/dashboard/applications` | My applications: summary, filters, status, explanations |
| 5 | `/dashboard/assessments` | Available practice + drive assessments |
| 6 | `/dashboard/assessments/[attemptId]/take` | Assessment runner |
| 7 | `/dashboard/assessments/results/[attemptId]` | Attempt result and question breakdown |
| 8 | `/dashboard/insights` | AI coach narrative + focus areas |
| 9 | `/dashboard/resume` | Upload, versions, parsed data, autofill |
| 10 | `/dashboard/profile` | Profile details and skills |

Plus `/login` and `/register` in the `(auth)` group, and `/` (marketing landing).

### 3.2 Page-by-page data flow

#### 3.2.1 `/dashboard` — student overview

| Aspect | Detail |
|---|---|
| Hooks | `use-analytics`, `use-assessments`, `use-drives`, `use-resumes`, `use-student-profile` |
| Endpoints | `GET /analytics/student/me`; `GET /assessments`; `GET /assessments/knowledge-states/me`; `GET /drives/applications/me`; `GET /resumes/history`; `GET /students/me` |
| Collections | `applications`, `assessment_attempts`, `assessments`, `knowledge_states`/questions (for domain scores), `resumes`, `students` |
| Components | `StatCard`, `ChartCard`, `DonutChart`, `DomainRadarChart`, `TrendLineChart` |
| Cards | Resume status; Applications; Shortlisted; Avg. assessment score; Profile completeness; Knowledge tracing snapshot |
| Charts | **Application status** donut (Applied / Shortlisted / Rejected); **Domain readiness** radar (5 domains, 0–100); **Assessment score trend** line |

Notes:
- "Applied / Under review" is the `applied` count. The donut plots only the three live statuses; `selected` is never plotted.
- A brand-new student with no attempts gets a radar with five zero-value domains and `answered=0`; the chart is shown with an empty-state message rather than fabricated scores.

#### 3.2.2 `/dashboard/drives` — drive discovery

| Aspect | Detail |
|---|---|
| Hooks | `use-drives`, `use-matching` |
| Endpoints | `GET /drives`; `GET /matching/recommended-drives` |
| Collections | `placement_drives`, `companies`, `applications` (for "already applied"), `resumes` (for recommendations) |
| Behaviour | Lists open drives with company, role, package, location, deadline, required skills. Recommended drives are ranked by the hybrid match score. |

#### 3.2.3 `/dashboard/drives/[id]` — drive detail and apply

| Aspect | Detail |
|---|---|
| Hooks | `use-drives`, `use-matching`, `use-student-profile`, `use-toast` |
| Endpoints | `GET /drives/{drive_id}`; `GET /matching/drives/{drive_id}/score`; `GET /students/me`; `POST /drives/{drive_id}/apply` |
| Collections | `placement_drives`, `companies`, `resumes`, `students`, `applications` |
| Components | `MatchScoreCard` |
| Behaviour | Shows eligibility criteria, selection process, assessment linkage, and the four matching sub-scores. Apply is disabled when ineligible, when no active resume exists, or when already applied. |

Apply-time validation in `DriveService.apply_to_drive()`:

1. Student profile must exist.
2. An active resume must exist (`students.active_resume_id`).
3. `_check_eligibility()` must pass (CGPA, department, batch year).
4. No existing application for `(drive, student)`.

On success the application is inserted with `status="applied"`, `eligibility_passed=true`, scores `null`, and `assessment_status="pending"` when the drive has a required assessment, else `"not_required"`.

#### 3.2.4 `/dashboard/applications` — my applications

| Aspect | Detail |
|---|---|
| Hooks | `use-drives`, `use-assessments`, `use-explanation` |
| Endpoints | `GET /drives/applications/me`; `GET /applications/{application_id}/explanation`; `GET /assessments` |
| Collections | `applications`, `placement_drives`, `companies`, `resumes`, `assessment_attempts`, `assessments`, `knowledge_chunks` (RAG) |
| Components | `StatCard`, `ApplicationStatusBadge`, `MarkdownText` |
| Cards | Total applications; Applied / Under review; Shortlisted; Rejected |
| Table | Drive, company, applied date, status, assessment status, action |
| Filters | Status, company, drive, assessment, date range |
| Notes | Explanations are fetched on demand, not for every row. `MarkdownText` renders the coach text safely. |

#### 3.2.5 `/dashboard/assessments` — assessment catalogue

| Aspect | Detail |
|---|---|
| Hooks | `use-assessments`, `use-drives`, `use-toast` |
| Endpoints | `GET /assessments`; `GET /drives/applications/me`; `POST /assessments/{assessment_id}/start` |
| Collections | `assessments`, `applications`, `placement_drives`, `assessment_attempts` |
| Tabs | Practice assessments; drive assessments |
| Behaviour | A drive assessment is startable only when it is published, linked to one of the student's applications, and not already submitted when `allow_retake=false`. |

#### 3.2.6 `/dashboard/assessments/[attemptId]/take` — runner

| Aspect | Detail |
|---|---|
| Hooks | `use-assessments`, `use-toast` |
| Endpoints | `GET /assessments/attempts/{attempt_id}/questions`; `POST /assessments/attempts/{attempt_id}/answer`; `POST /assessments/attempts/{attempt_id}/finish`; `POST /assessments/attempts/{attempt_id}/run-code`; `POST /assessments/attempts/{attempt_id}/violation` |
| Collections | `assessment_attempts`, `assessments`, `questions` |
| Behaviour | One question at a time with a palette. Answers are persisted per question. Coding answers can be dry-run. Fullscreen/violation events are reported. Finish grades and returns the result. |

**Important nuance:** option order is always shuffled at delivery by `to_student_view()`, regardless of the stored `randomize_options` flag. The attempt stores the answers as submitted, so grading is unaffected.

#### 3.2.7 `/dashboard/assessments/results/[attemptId]` — results

| Aspect | Detail |
|---|---|
| Hooks | `use-assessments` |
| Endpoints | `GET /assessments/attempts/{attempt_id}/results` |
| Collections | `assessment_attempts`, `assessments`, `questions` |
| Behaviour | Shows score, pass/fail against `passing_marks`, and a per-question breakdown. Grading detail is in **Formulas §2**. |

#### 3.2.8 `/dashboard/insights` — AI coach

| Aspect | Detail |
|---|---|
| Hooks | `use-assessments` |
| Endpoints | `GET /insights/me`; `GET /assessments/knowledge-states/me` |
| Collections | `assessment_attempts`, `knowledge_states`, `questions`, `insights_narrative_cache`, `knowledge_chunks` |
| Components | `MarkdownText`, `StatCard`, progress bars |
| Behaviour | Produces focus areas and a grounded narrative. The narrative is cached. If the LLM is unavailable, the deterministic focus list is still returned; the narrative may be a placeholder. **Partially testable locally** (see §16). |

#### 3.2.9 `/dashboard/resume` — resume

| Aspect | Detail |
|---|---|
| Hooks | `use-resumes`, `use-toast` |
| Endpoints | `GET /resumes/history`; `POST /resumes`; `GET /resumes/{resume_id}`; `POST /resumes/{resume_id}/reparse`; `GET /resumes/{resume_id}/autofill-suggestion`; `POST /resumes/{resume_id}/autofill-apply`; `GET /resumes/{resume_id}/download` |
| Collections | `resumes`, `students`, `unmapped_skill_suggestions` |
| Behaviour | Upload (PDF, ≤ 5 MB), version history, parsed data, re-parse, autofill suggestion/apply, download. See §7. |

#### 3.2.10 `/dashboard/profile` — profile

| Aspect | Detail |
|---|---|
| Hooks | `use-student-profile`, `use-toast` |
| Endpoints | `GET /students/me`; `PUT /students/me` |
| Collections | `students`, `users` |
| Behaviour | Partial update of name, department (canonical combobox), batch year, CGPA, contact links, skills, achievements, certificates. |

### 3.3 Student API surface (summary)

| Method | Path | Purpose |
|---|---|---|
| GET | `/analytics/student/me` | Overview analytics |
| GET | `/drives` | Open drives |
| GET | `/drives/{drive_id}` | Drive detail |
| POST | `/drives/{drive_id}/apply` | Apply |
| GET | `/drives/applications/me` | My applications |
| GET | `/matching/recommended-drives` | Recommended drives |
| GET | `/matching/drives/{drive_id}/score` | Match score |
| GET | `/assessments` | Assessment catalogue |
| POST | `/assessments/{assessment_id}/start` | Start attempt |
| GET/POST | `/assessments/attempts/{attempt_id}/…` | Questions, answer, finish, run-code, violation, results |
| GET | `/assessments/knowledge-states/me` | My mastery |
| GET | `/insights/me` | AI coach |
| GET | `/assessments/attempts/{attempt_id}/gap-analysis` | Skill gap for one attempt (**API-only; no UI calls it**) |
| GET | `/drives/{drive_id}/match-explanation` | JD explanation (**API-only; no UI calls it**) |
| GET | `/applications/{application_id}/explanation` | Application explanation |
| GET/POST | `/resumes…` | Resume lifecycle |
| GET/PUT | `/students/me` | Profile |

**Cross-reference:** the same `applications`, `assessment_attempts`, and `knowledge_states` records feed TPO (§4) and Admin (§5) analytics. Student actions are therefore visible upward without duplication.

---

## 4. Interface B — TPO

The TPO shell is `frontend/app/(tpo)/layout.tsx`.

### 4.1 Route map

| # | Route | Purpose |
|---|---|---|
| 1 | `/tpo/dashboard` | Operational overview + application analytics |
| 2 | `/tpo/dashboard/drives` | My drives |
| 3 | `/tpo/dashboard/drives/new` | Create drive |
| 4 | `/tpo/dashboard/drives/[id]` | Drive detail + edit/clone/delete |
| 5 | `/tpo/dashboard/drives/[id]/applicants` | Applicant management & screening |
| 6 | `/tpo/dashboard/analytics` | Funnel, departments, companies, drives, domain radar, ranking |
| 7 | `/tpo/dashboard/analytics/trending` | Market Insights (imported postings) |
| 8 | `/tpo/dashboard/analytics/skill-gaps` | Skill-gap analysis |

### 4.2 Page-by-page data flow

#### 4.2.1 `/tpo/dashboard` — TPO overview

| Aspect | Detail |
|---|---|
| Hooks | `use-analytics`, `use-tpo-drives` |
| Endpoints | `GET /analytics/tpo`; `GET /analytics/tpo/applications`; `GET /analytics/tpo/applications/records`; `GET /drives/mine` |
| Collections | `placement_drives`, `companies`, `applications`, `assessment_attempts`, `students`, `questions` |
| Cards | Total drives; Open; Closed; Total students; Active drives; Total applications; Shortlisted |
| Charts | Application status donut; **Recruitment progress**; **Company-wise applications** (horizontal bars); **Department-wise applications and shortlisting** (grouped bars); **Drive-wise applications and shortlisting** (grouped bars); **Monthly Application Trends** (grouped bars); application records panel |
| Filters | Date-from / date-to; company sort; top-N |
| Notes | When all applications fall in one month, the monthly chart renders a single grouped/stacked column plus a range note. It never invents extra months. |

#### 4.2.2 `/tpo/dashboard/drives` — my drives

| Aspect | Detail |
|---|---|
| Hooks | `use-tpo-drives` |
| Endpoints | `GET /drives/mine` |
| Collections | `placement_drives`, `companies`, `applications` (counts) |
| Behaviour | Lists only drives created by the logged-in TPO (`created_by = tpo profile _id`). |

#### 4.2.3 `/tpo/dashboard/drives/new` — create drive

| Aspect | Detail |
|---|---|
| Hooks | `use-tpo-drives`, `use-assessments`, `use-toast` |
| Endpoints | `POST /drives`; `GET /assessments` (for assessment linkage) |
| Collections | `placement_drives`, `companies`, `assessments` |
| Validation | Zod form: role, company, JD, skills, experience, package, location, deadline, eligibility (CGPA/departments/batch years), selection process, **required assessment** |
| Notes | The form requires an assessment before a drive can be published. Backend enforces the same rule via `ASSESSMENT_REQUIRED_FOR_PUBLISH`. |

#### 4.2.4 `/tpo/dashboard/drives/[id]` — drive detail

| Aspect | Detail |
|---|---|
| Hooks | `use-drives`, `use-tpo-drives`, `use-assessments`, `use-toast` |
| Endpoints | `GET /drives/{drive_id}`; `PUT /drives/{drive_id}`; `DELETE /drives/{drive_id}`; `POST /drives/{drive_id}/clone`; `GET /assessments` |
| Collections | `placement_drives`, `companies`, `applications`, `assessments` |
| Behaviour | Edit fields, open/close, clone, delete. Changing text-affecting fields invalidates `jd_embedding`. |

#### 4.2.5 `/tpo/dashboard/drives/[id]/applicants` — screening

| Aspect | Detail |
|---|---|
| Hooks | `use-tpo-drives`, `use-assessments`, `use-resumes`, `use-toast` |
| Endpoints | `GET /drives/{drive_id}/applications`; `GET /drives/{drive_id}/screening-summary`; `POST /drives/{drive_id}/screen`; `GET /drives/{drive_id}/recommended-shortlist`; `PATCH /drives/{drive_id}/applications/{application_id}`; `PATCH /drives/{drive_id}/applications/bulk-status`; `GET /drives/{drive_id}/applications/export`; `GET /resumes/{resume_id}/download`; `GET /assessments/placement/{drive_id}/participation` |
| Collections | `applications`, `students`, `resumes`, `placement_drives`, `assessment_attempts`, `assessments` |
| Cards | Total Applicants; Eligible; Test Passed; Test Pending; Recommended; Shortlisted |
| Table | Student, department, CGPA, applied date, match score, assessment, status, actions |
| Actions | Screen; shortlist/reject (single or bulk); export CSV; download resume; view participation |

#### 4.2.6 `/tpo/dashboard/analytics` — analytics

| Aspect | Detail |
|---|---|
| Hooks | `use-analytics` |
| Endpoints | `GET /analytics/tpo`; `GET /analytics/tpo/applications`; `GET /analytics/tpo/drives/{drive_id}/ranking`; `GET /analytics/tpo/drives/{drive_id}/applicants`; `GET /analytics/tpo/drives/{drive_id}/participants` |
| Collections | `placement_drives`, `applications`, `assessment_attempts`, `students`, `questions` |
| Cards | Total drives; Open drives; Total applications |
| Charts | **Application funnel** card (`StatusBreakdownChart`); **Domain readiness across your drives** radar (aggregated `domain_scores`); **Drive breakdown** (per-drive panels for Rankings, Applied students, Test participants) |
| Notes | The radar aggregates graded answers from students in the TPO's drives. With no evidence it returns `[]` and the page shows an empty state (not five fake zeros). |

#### 4.2.7 `/tpo/dashboard/analytics/trending` — Market Insights

| Aspect | Detail |
|---|---|
| Hooks | `use-market-analytics` |
| Endpoints | `GET /analytics/tpo/market`; `GET /analytics/tpo/market/filters`; `GET /analytics/tpo/market/comparison` |
| Collections | `job_market_postings`, `market_skill_catalog`, `market_import_runs` |
| Components | Summary cards, trend charts, emerging skills, company analytics, job-family section, comparison section, filter panel, `MarketDataBanner` |
| Notes | This is the one place a data-source banner is intentional: it states whether the imported posting dataset is demo, real, or mixed (`data_origin`). That is a genuine source disclosure, not a synthetic label on computed analytics. |

#### 4.2.8 `/tpo/dashboard/analytics/skill-gaps` — skill gaps

| Aspect | Detail |
|---|---|
| Hooks | `use-skill-gaps` |
| Endpoints | `GET /analytics/tpo/skill-gaps`; `GET /analytics/tpo/skill-gaps/filters`; `GET /analytics/tpo/skill-gaps/{skill_id}/students` |
| Collections | `job_market_postings`, `market_skill_catalog`, `questions`, `assessment_attempts`, `students`, `resumes`, `placement_drives`, `assessments` |
| Components | Summary cards, demand-vs-proficiency chart, priority gaps table, skill detail panel, students panel, training recommendations |
| Notes | Student evidence comes only from graded attempts on questions tagged with the skill. Self-reported profile/resume skills are reported separately. Thresholds are in the response meta, not hardcoded in the UI. |

### 4.3 TPO API surface (summary)

| Method | Path | Purpose |
|---|---|---|
| POST | `/drives` | Create drive |
| GET | `/drives/mine` | My drives |
| PUT/DELETE | `/drives/{drive_id}` | Update/delete |
| POST | `/drives/{drive_id}/clone` | Clone |
| GET | `/drives/{drive_id}/applications` | Applications |
| GET | `/drives/{drive_id}/screening-summary` | Screening counts |
| POST | `/drives/{drive_id}/screen` | Run screening |
| GET | `/drives/{drive_id}/recommended-shortlist` | Recommended shortlist |
| PATCH | `/drives/{drive_id}/applications/{application_id}` | Set status |
| PATCH | `/drives/{drive_id}/applications/bulk-status` | Bulk status |
| GET | `/drives/{drive_id}/applications/export` | CSV export |
| GET | `/analytics/tpo` | Drive/funnel analytics |
| GET | `/analytics/tpo/applications` | Application analytics |
| GET | `/analytics/tpo/applications/records` | Paged records |
| GET | `/analytics/tpo/drives/{drive_id}/ranking` | Assessment ranking |
| GET | `/analytics/tpo/drives/{drive_id}/applicants` | Applicants |
| GET | `/analytics/tpo/drives/{drive_id}/participants` | Assessment participants |
| GET | `/analytics/tpo/skill-gaps…` | Skill gaps |
| GET | `/analytics/tpo/market…` | Market insights |
| GET | `/matching/drives/{drive_id}/ranked-applicants` | ML-ranked applicants |
| GET | `/assessments/placement/{drive_id}/participation` | Placement assessment participation |
| GET | `/assessments/knowledge-states/{student_id}` | A student's mastery |
| GET | `/questions`, `/questions/categories`, `/questions/stats` | Read-only question bank access |

**Cross-reference:** TPO analytics reads the same `applications` and `assessment_attempts` rows created by students (§3) and uses `students` profiles created at registration (§6.1). Admin (§5) can read the same drives and applications through `admin`-scoped endpoints.

---

## 5. Interface C — Admin

The admin shell is `frontend/app/(admin)/layout.tsx`.

### 5.1 Route map

| # | Route | Purpose |
|---|---|---|
| 1 | `/admin/dashboard` | Platform overview (analytics, activity, assessment performance) |
| 2 | `/admin/dashboard/drives` | Applications workspace (cross-drive) |
| 3 | `/admin/dashboard/questions` | Question bank |
| 4 | `/admin/dashboard/questions/new` | New question |
| 5 | `/admin/dashboard/assessments` | Assessments list |
| 6 | `/admin/dashboard/assessments/new` | New assessment (adaptive or standardized; templates managed in a dialog, placement generation inline) |

> The applications workspace lives at `/admin/dashboard/drives` because the original route was preserved. Its visible title is **Applications**. The nav label is **Applications**.
>
> There are no separate `/admin/dashboard/analytics`, `/templates`, or `/placement` routes. Platform analytics render on the overview page; templates and Drive Assessment generation are dialogs/sections on `/admin/dashboard/assessments/new`. The template and placement **API** endpoints still exist (§5.3).

### 5.2 Page-by-page data flow

#### 5.2.1 `/admin/dashboard` — platform overview

| Aspect | Detail |
|---|---|
| Hooks | `useAdminAnalytics`, `useAdminActivity` |
| Endpoints | `GET /analytics/admin`; `GET /analytics/admin/activity` |
| Collections | `users`, `students`, `tpos`, `admins`, `placement_drives`, `applications`, `companies`, `assessments`, `assessment_attempts`, `questions`, `question_categories` |
| Cards | Students; Companies; Drives (open/closed split); Applications; TPOs |
| Charts | **Platform snapshot** (students, companies, drives, students with applications); **User distribution** donut (students/TPOs/admins); **Assessment performance** metric grid (assessments, attempts, submitted, average score, completion rate, questions, categories) |
| Notes | This page is the only admin analytics surface; there is no separate `/admin/dashboard/analytics` route. `GET /analytics/admin/activity` also returns monthly activity and department counts, but the page currently renders only `user_distribution`. The former "Placement snapshot" is absent because no placement-offer collection exists; `placed_students`/`placement_rate_pct` remain legacy API fields and are not shown as a placement metric. |

#### 5.2.2 Admin analytics (no separate page)

Platform analytics are rendered on `/admin/dashboard` (§5.2.1). The `GET /analytics/admin` payload also exposes `application_breakdown`, `skill_mastery_overview`, and assessment totals, but the overview page does not currently chart the status breakdown or the skill-mastery list. They remain available to API clients and future UI work.

#### 5.2.3 `/admin/dashboard/drives` — Applications workspace

| Aspect | Detail |
|---|---|
| Hooks | `useAdminApplications`, `useAdminApplicationFilters`, `useUpdateApplicationStatusForDrive`, `use-toast` |
| Endpoints | `GET /analytics/admin/applications`; `GET /analytics/admin/applications/filters`; `PATCH /drives/{drive_id}/applications/{application_id}` |
| Collections | `applications`, `students`, `placement_drives`, `companies`, `assessments`, `assessment_attempts` |
| Cards | Total applications; Applied / Under review; Shortlisted; Rejected |
| Filters | Company; drive; department; status; assessment; date range |
| Table | Student, department, company, drive, assessment, score, rank, status, applied date |
| Notes | This is a **cross-drive** workspace. Rows use the effective (legacy-normalized) status. Status changes go through the same `DriveService.update_application_status()` used by TPOs. |

#### 5.2.4 `/admin/dashboard/questions` — question bank

| Aspect | Detail |
|---|---|
| Hooks | `use-admin-questions`, `use-toast` |
| Endpoints | `GET /questions`; `GET /questions/stats`; `GET /questions/categories`; `POST /questions/categories`; `PUT /questions/{question_id}`; `PATCH /questions/{question_id}/status`; `DELETE /questions/{question_id}`; `POST /questions/import/preview`; `POST /questions/import/commit`; `POST /questions/import`; `POST /questions/import/error-report`; `GET /questions/export`; `GET /questions/export/excel`; `GET /questions/export/template` |
| Collections | `questions`, `question_categories` |
| Tabs | Questions; Categories; Import; Standardized sections; Import safety |
| Filters | Search, category, difficulty, type, status, topic, skill |

#### 5.2.5 `/admin/dashboard/questions/new` — new question

| Aspect | Detail |
|---|---|
| Hooks | `use-admin-questions`, `use-toast` |
| Endpoints | `GET /questions/categories`; `POST /questions` |
| Collections | `questions`, `question_categories` |

#### 5.2.6 `/admin/dashboard/assessments` — assessments

| Aspect | Detail |
|---|---|
| Hooks | `use-assessments` |
| Endpoints | `GET /assessments` |
| Collections | `assessments`, `placement_drives`, `companies` |
| Behaviour | Read-only list of all assessments with type, status, totals, drive linkage. |

#### 5.2.7 `/admin/dashboard/assessments/new` — new assessment

| Aspect | Detail |
|---|---|
| Hooks | `useCreateAssessment`, `useCategories`, `useTemplates`, `useGeneratePlacementAssessment`, `useDrives`, `use-toast`; the template dialog adds `useTemplatePresets`, `useCreateTemplate`, `useUpdateTemplate`, `useDuplicateTemplate`, `useSetTemplateStatus` |
| Endpoints | `POST /assessments`; `GET /questions/categories`; `GET /assessments/templates`; `GET /drives`; `POST /assessments/placement/generate`; template dialog: `GET /assessments/templates/presets`, `GET /assessments/templates/{id}`, `POST /assessments/templates`, `PUT /assessments/templates/{id}`, `POST /assessments/templates/{id}/duplicate`, `PATCH /assessments/templates/{id}/status`, `DELETE /assessments/templates/{id}` |
| Collections | `assessments`, `questions`, `assessment_templates`, `placement_drives` |
| Modes | `adaptive` (legacy pool) and `standardized` (generated through the placement endpoint) |
| Notes | `POST /assessments` rejects `format=standardized` with `400`; standardized assessments must be generated via `POST /assessments/placement/generate`. The **Manage templates** button opens `TemplateManagerDialog`; there is no separate templates route. |

#### 5.2.8 Assessment templates (dialog, no route)

Templates are created, edited, duplicated, activated/deactivated, and deleted inside the template dialog on `/admin/dashboard/assessments/new`. The full template API (§5.3) is unchanged. The `custom` preset is a blank starting point and is not persisted by the seed.

#### 5.2.9 Drive Assessment generator (inline, no route)

Standardized Drive Assessment generation happens in the **Standardized placement assessment** mode of `/admin/dashboard/assessments/new`. It calls `POST /assessments/placement/generate` (and can revise via `POST /assessments/placement/{assessment_id}/revise`). Participation is read through `GET /assessments/placement/{drive_id}/participation`.

| Rule | Detail |
|---|---|
| Sections | Five: Quantitative Aptitude, Logical Reasoning, Verbal Ability, Technical Knowledge, Coding/Problem Solving |
| Questions | 20 total; 4 per section; 6 easy / 10 medium / 4 hard |
| Marks | 1 / 3 / 5 by difficulty; 56 total for seeded drives |
| Selection | Deterministic; deficits are reported explicitly rather than padded |
| Naming | "Drive Assessment" is the UI name; the old label "Placement Generator" is no longer used. |

### 5.3 Admin API surface (summary)

| Method | Path | Purpose |
|---|---|---|
| GET | `/analytics/admin` | Platform analytics |
| GET | `/analytics/admin/activity` | Monthly activity + distributions |
| GET | `/analytics/admin/applications` | Cross-drive application workspace |
| GET | `/analytics/admin/applications/filters` | Workspace filter options |
| GET | `/analytics/tpo/drives/{drive_id}/ranking` | Ranking (admin allowed) |
| POST | `/assessments` | Create adaptive assessment |
| POST | `/assessments/placement/eligibility` | Check question-bank sufficiency |
| POST | `/assessments/placement/generate` | Generate standardized drive assessment |
| POST | `/assessments/placement/{assessment_id}/revise` | Revise generated assessment |
| GET | `/assessments/placement/{drive_id}/participation` | Participation |
| GET/POST/PUT/PATCH/DELETE | `/assessments/templates…` | Templates |
| GET/POST/PUT/PATCH/DELETE | `/questions…` | Question bank |
| POST/DELETE/GET | `/admin/knowledge…` | RAG chunk ingest/stats |
| GET | `/admin/observability/llm` | LLM provider metrics |

### 5.4 Admin capability gaps (explicit)

The admin UI does **not** include:

- User, student, TPO, or admin management pages.
- Company CRUD.
- A notification center.
- An activity-log viewer page (activity is exposed only as aggregated analytics).
- A placement-offer/placement-record screen (no collection exists).

These are gaps in the current product, not hidden features. They are listed again in §16.

**Cross-reference:** admin analytics consumes the same `users`, `students`, `placement_drives`, and `applications` written by the student (§3) and TPO (§4) interfaces. The admin applications workspace and the TPO applicant page both call `DriveService.update_application_status()`, so status changes are consistent across roles.

---

## 6. Data ingestion

There are six ingestion paths.

### 6.1 Registration and authentication

| Flow | Endpoint | What is written |
|---|---|---|
| Student registration | `POST /auth/register/student` | `users` (role `student`, bcrypt hash) + `students` profile |
| TPO registration | `POST /auth/register/tpo` | `users` (role `tpo`) + `tpos` profile |
| Admin creation | `backend/scripts/create_admin.py` (no HTTP route) | `users` (role `admin`) + `admins` profile |
| Local login | `POST /auth/login` | Updates `users.last_login`; inserts `refresh_tokens` |
| Google login | `POST /auth/google` | Verifies Google ID token; creates or links `users` (`auth_provider="google"`, `google_sub`) |
| Refresh | `POST /auth/refresh` | Rotates `refresh_tokens` (revoke old, insert new) |
| Logout | `POST /auth/logout` | Revokes the refresh token |
| Forgot/reset password | `POST /auth/forgot-password`, `POST /auth/reset-password` | `password_reset_tokens`; updates `users.password_hash` |

**Department canonicalization.** Registration and profile updates normalize department strings to the 10 canonical labels in `backend/app/core/departments.py`. The frontend combobox uses the identical list in `frontend/lib/departments.ts`. Drive eligibility departments are normalized on write in `DriveService.create_drive()`/`update_drive()`. A dry-run-first audit script exists at `backend/scripts/normalize_departments.py`.

### 6.2 Resume upload

`POST /resumes` (`multipart/form-data`). Pipeline:

1. **Cap read.** `read_upload_capped()` streams the upload in 1 MiB blocks and aborts over `MAX_RESUME_SIZE_MB` (5 MB) with `413`.
2. **Signature check.** Content must start with `%PDF`; otherwise `400`.
3. **Hash and dedupe.** SHA-256 of the bytes. If the active resume has the same hash, the upload is rejected as a duplicate.
4. **Version.** `get_next_version_number()` assigns `version`.
5. **Deactivate old.** Prior versions are set `is_active=false` before insert, so at most one active resume exists.
6. **Store.** `StorageService.save_pdf()` writes to local disk (`STORAGE_BACKEND=local`, under `LOCAL_STORAGE_PATH`) or Cloudinary.
7. **Parse synchronously.** `ResumeParsingService.parse_and_store()` runs inline (no background queue).
8. **Autofill.** `ProfileAutofillService.build_suggestion()` merges name, phone, skills, etc. into the student profile.

### 6.3 Question-bank import/export

`backend/app/services/question_import_service.py`.

- Accepted: `.xlsx` and `.csv`; signature checked in addition to extension.
- Caps: 10 MB file, 5,000 rows, 20,000 characters per cell.
- Header aliases map spreadsheet columns to canonical fields. Required: `text`, `question_type`, `category`, `difficulty`, `correct_answer`.
- Two-step import: `POST /questions/import/preview` parses and reports errors, `POST /questions/import/commit` writes.
- Export neutralizes CSV formula injection by prefixing leading `= + - @` with `'`.
- Formulas are never evaluated (`data_only=True`, `read_only=True`).

### 6.4 Market data import

- `backend/scripts/seed_job_market.py` seeds `job_market_postings` and `market_skill_catalog`.
- `backend/scripts/import_job_market.py` imports additional postings and records a row in `market_import_runs`.
- Each run produces metadata used by the Market Insights banner (`data_origin`: `mock` / `real` / `mixed`).

### 6.5 Knowledge-store ingest (RAG)

- `POST /api/v1/admin/knowledge/chunks` ingests text chunks and embeddings into `knowledge_chunks`.
- `DELETE /api/v1/admin/knowledge/{source_id}` removes a source.
- `GET /api/v1/admin/knowledge/stats` reports store statistics.
- `backend/scripts/seed_knowledge_store.py` seeds baseline content.

### 6.6 Seed and operational scripts

| Script | Purpose |
|---|---|
| `seed_question_bank.py` | Questions and categories |
| `seed_assessments.py` | Assessment definitions |
| `seed_mock_drives.py` | Drives/companies for development |
| `seed_synthetic_demo.py` | Provenance-marked demo dataset |
| `seed_verbal_ability.py` | Verbal-ability questions |
| `seed_job_market.py` | Market postings + catalog |
| `seed_knowledge_store.py` | RAG chunks |
| `import_job_market.py` | Incremental market import |
| `normalize_departments.py` | Dry-run-first department audit/repair |
| `create_admin.py` | Admin account creation |
| `compare_models.py` | Matching model comparison |
| `probe_student_insights.py` | Insights diagnostics |

---

## 7. Resume and AI pipeline

### 7.1 Stage overview

```text
PDF bytes
  → validation (size, magic, hash, duplicate)
  → storage (local / Cloudinary)
  → text extraction (PyMuPDF)
  → OCR fallback (PaddleOCR, if text is too short/noisy)
  → regex structural parse (contact, education, experience, projects, skills)
  → LLM skill extraction (with regex fallback)
  → profile autofill (merge into students)
  → bi-encoder embedding (cached on the resume document)
  → match scoring against drives (retrieve → rerank → calibrate → hybrid)
  → explanation / insights / gap analysis (grounded LLM, RAG)
```

### 7.2 Text extraction and OCR

`app/ml/parsing/parser.py`:

- Extracts text per page with PyMuPDF.
- Triggers OCR when extracted characters fall below `OCR_TRIGGER_MIN_CHARS` (default 50) or when the alphanumeric ratio is below `OCR_MIN_ALPHANUMERIC_RATIO` (default 0.5).
- OCR renders pages at `OCR_RENDER_DPI` (default 150), uses `OCR_LANG`, optional angle classification, and `OCR_CONFIDENCE_THRESHOLD`.
- OCR is disabled entirely with `OCR_ENABLED=false`.

`parse_resume()` returns a `ParsedResumeData`, the raw text, regex skills, and an experience-years estimate.

### 7.3 LLM skill extraction

`app/ml/parsing/llm_skill_extractor.py`:

- Sends resume text to the LLM with a constrained vocabulary of 50 terms.
- Unknown phrases are returned as suggestions and queued in `unmapped_skill_suggestions` (unreviewed).
- If the LLM is unavailable, the function **returns the regex skills** rather than failing.
- The service never ships an empty skill set when regex already found something.

### 7.4 Profile autofill

`ProfileAutofillService`:

- Builds a suggestion from the parsed resume (name, phone, links, department, batch year, CGPA, skills, achievements).
- Only fills fields that are empty or clearly derived; the student can review and apply.
- `POST /resumes/{resume_id}/autofill-apply` persists the accepted suggestion.

### 7.5 Matching pipeline

Artifacts live in `backend/app/ml/matching/artifacts/`:

- `bi_encoder/` — fine-tuned `all-MiniLM-L6-v2` in sentence-transformers format.
- `cross_encoder/` — fine-tuned `cross-encoder/stsb-roberta-base`.
- `calibrator.pkl` — sklearn `LogisticRegression` (Platt scaling).

`app/ml/matching/inference.py` loads these with plain `transformers` (`AutoModel`, `AutoModelForSequenceClassification`) and implements the math directly:

1. **Embed.** Tokenize, run the bi-encoder, mean-pool with the attention mask, L2-normalize.
2. **Retrieve.** Cosine similarity between the resume/JD vectors.
3. **Rerank.** Cross-encoder scores each candidate pair; raw logits go through sigmoid.
4. **Calibrate.** `calibrator.predict_proba(...)[:, 1]` produces the calibrated match probability.

`MatchingService` builds the canonical texts:

- Resume text: `"Technical skills: <skills>. Experience years: <n>."`
- JD text: role, company, description, required skills, required experience.

Then it computes:

```text
skills_score     = |resume_skills ∩ jd_required_skills| / max(1, |jd_required_skills|)
experience_score = clamp(resume_years / jd_years, 0, 1)      # 1.0 if jd_years = 0
final_score      = 0.40·semantic + 0.30·skills + 0.20·experience + 0.10·(assessment_pct/100)
```

The full derivation, worked example, and edge cases are in **Formulas §8 (Resume–Job Matching)**. The transformer internals are in **Formulas §9**.

**Caching.** `resume_embedding` is stored on `resumes`; `jd_embedding` is stored on `placement_drives`. `DriveService` invalidates `jd_embedding` whenever `job_title`, `description`, `jd_text`, `required_skills`, or `experience_required_years` changes. Re-parsing a resume recomputes its embedding.

**Retrieval pool.** `DEFAULT_RETRIEVER_POOL = 100` candidates go to the cross-encoder.

### 7.6 Explanations, insights, and gap analysis (RAG)

| Service | Endpoint | Grounding |
|---|---|---|
| `ApplicationExplanationService` | `GET /applications/{application_id}/explanation` | Eligibility result, matching breakdown, assessment result, decision/rejection reasons, retrieved knowledge chunks |
| `JDExplanationService` | `GET /drives/{drive_id}/match-explanation` | Already-computed match score + JD text |
| `StudentInsightsService` | `GET /insights/me` | Attempts, mastery, focus ranking; cached narrative |
| `GapAnalysisService` | `GET /assessments/attempts/{attempt_id}/gap-analysis` | Per-skill correct/answered counts; weak-mastery threshold 50.0 |

All four use `llm_client` and `KnowledgeStore`. The prompts explicitly forbid inventing scores or criteria. If retrieval or the LLM fails, the deterministic data is still returned and the narrative degrades gracefully.

### 7.7 LLM client behavior

`app/ml/llm/client.py`:

- **Providers.** Primary then fallback, both OpenAI-compatible. Provider is only a config value.
- **Local mode.** `LLM_USE_LOCAL_OLLAMA=true` uses a single Ollama provider and no fallback.
- **Retries.** Transient failures only (`429`, `5xx`, connection, timeout). `LLM_MAX_RETRIES=2`, exponential backoff `base·2^N` with `LLM_RETRY_BACKOFF_SECONDS=1.5`.
- **Timeout.** `LLM_REQUEST_TIMEOUT_SECONDS` (90 s in the example env).
- **No retry on 4xx.** Auth/validation errors fail immediately.
- **Failure.** Raises `LLMUnavailableError`; callers fall back or return `503`.
- **Metrics.** Per-provider calls, failures, retries, tokens, average latency, last error, plus embedding and cache metrics, exposed at `GET /api/v1/admin/observability/llm`.
- **Thinking mode.** Chosen per call site via the `thinking=` kwarg and translated to `enable_thinking` (qwen) or `reasoning_effort` (Gemini).

**Architecture §F** shows the AI model architecture and inference flow.

---

## 8. Drive and assessment lifecycle

### 8.1 Drive state machine

```text
            create (TPO)
                │
                ▼
        ┌───────────────┐   status=open    ┌───────────────┐
        │     DRAFT     │ ───────────────► │     OPEN      │
        │ (pre-publish) │                  │               │
        └───────────────┘                  └───────┬───────┘
                                                   │ status=closed
                                                   ▼
                                           ┌───────────────┐
                                           │    CLOSED     │
                                           └───────┬───────┘
                                                   │ status=open
                                                   └──────────► OPEN
```

Notes:

- `DriveStatus` has only `open` and `closed`. There is no separate `draft` enum value; "publish" means setting `status=open`.
- A drive may be created with `status=closed` and opened later, but **opening requires a `required_assessment_id`**. Removing the assessment from an open drive is also blocked. The fixed message is `ASSESSMENT_REQUIRED_FOR_PUBLISH`.
- Deleting a drive is a hard delete of the drive document. Applications are not cascade-deleted by the service; they remain and are filtered by the missing drive in read paths. This is a known gap (§16).

### 8.2 Eligibility gate

`EligibilityCriteria`:

- `min_cgpa` (nullable)
- `departments` (empty = all)
- `batch_years` (empty = all)

`DriveService._check_eligibility(student, drive)` returns `(is_eligible, reasons)`. A failed check returns `403` with the joined reasons. Department comparison uses canonical labels on both sides.

### 8.3 Assessment creation paths

| Path | Who | Endpoint | Format |
|---|---|---|---|
| Adaptive assessment | Admin | `POST /assessments` | `adaptive` only |
| Standardized drive assessment | Admin | `POST /assessments/placement/generate` | `standardized` |
| Template-derived | Admin | `POST /assessments/templates…` then placement generation | `standardized` |

Standardized placement rules (`backend/app/models/assessment.py`):

- `PLACEMENT_SECTIONS` — five sections: Quantitative Aptitude, Logical Reasoning, Verbal Ability, Technical Knowledge, Coding/Problem Solving.
- `PLACEMENT_SECTION_SIZE = 4`, `PLACEMENT_TOTAL_QUESTIONS = 20`.
- `PLACEMENT_DIFFICULTY_QUOTA = {easy: 6, medium: 10, hard: 4}`.
- `DIFFICULTY_MARKS = {easy: 1, medium: 3, hard: 5}`.
- Selection is deterministic, oldest-first by `(created_at, id)`.
- If the bank cannot supply a quota, generation returns `422` with explicit `deficits`; it never pads with fabricated questions.

`PlacementAssessmentService` also supports revision (`/assessments/placement/{assessment_id}/revise`) and participation reporting (`/assessments/placement/{drive_id}/participation`).

### 8.4 Attempt lifecycle and grading

```text
POST /assessments/{assessment_id}/start
   │  validates: assessment exists, published (standardized), retake policy
   ▼
assessment_attempts: status=in_progress
   │  questions delivered one at a time (adaptive or fixed set)
   │  answers persisted per question
   │  violations appended
   ▼
POST /assessments/attempts/{attempt_id}/finish
   │  grades every answer
   │  updates knowledge_states
   │  status=submitted, submitted_at set
   ▼
GET /assessments/attempts/{attempt_id}/results
```

Grading rules (detail in **Formulas §2**):

- MCQ / true-false: exact match against `correct_answer`.
- Multiple-select: all-or-nothing against the correct set.
- Coding: all test cases must pass; legacy questions fall back to one empty-input case.
- Descriptive: stored, flagged for manual review, not auto-graded.
- Negative marking: on standardized assessments only, a wrong auto-gradable answer gets a flat `-abs(negative_marks)` (not proportional to question marks). Descriptive answers are never penalized.
- Standardized percentage: `_attempt_score_pct` uses answered-only marks; results view uses `assessment.total_marks`, clamped.

Anti-cheat:

- `anti_cheat_config` stores `max_violations` and `require_fullscreen`.
- `POST /assessments/attempts/{attempt_id}/violation` appends events.
- `fingerprint_hash` and `ip_address` are stored but **never compared**. Fullscreen is not backend-enforced. This is a known limitation (§16).

### 8.5 Screening

`POST /drives/{drive_id}/screen` (`ScreeningService`):

1. Requires the drive to belong to the TPO.
2. Reconciles expired assessments (`assessment_status="expired"` when past `assessment_deadline`).
3. For each application: loads the student and resume, computes the hybrid match score, persists `final_score`, `semantic_score`, `skills_score`, `experience_score`, `matched_skills`, `missing_skills`.
4. Reconciles assessment status (`pending` → `passed`/`failed` based on `assessment_min_score_pct`).
5. Never changes the application's shortlist/reject status automatically.

`GET /drives/{drive_id}/screening-summary` returns counts, including `recommended_shortlist` = eligible AND assessment passed/not-required AND `final_score >= 0.65`.

`GET /drives/{drive_id}/recommended-shortlist` returns the top N with `min_score=0.60` default.

---

## 9. Application status lifecycle

### 9.1 Canonical statuses

`ApplicationStatus` in `backend/app/models/drive.py`:

| Value | Display | Meaning |
|---|---|---|
| `applied` | Applied / Under review | Application received; no decision yet |
| `shortlisted` | Shortlisted | Advanced to the next stage |
| `rejected` | Rejected | Not advancing |
| `selected` | *(legacy only)* | Retained in the enum for old documents; **never produced** |

`MANAGED_APPLICATION_STATUSES = {applied, shortlisted, rejected}`.

### 9.2 Transitions

`DriveService.update_application_status()` allows free movement among the three managed statuses:

```text
applied ⇄ shortlisted
applied ⇄ rejected
shortlisted ⇄ rejected
```

Rules:

- The drive must belong to the acting TPO, or the actor must be an admin.
- Rejecting accepts `rejection_reasons` (from `RejectionReason`) and `rejection_note` (≤ 1000 chars).
- `decision_at` is set when leaving `applied`.
- Every change writes an `activity_logs` entry with actor, role, previous/new status, reasons, and IP.
- The method **never sets `selected`**.

`VALID_STATUS_TRANSITIONS` is declared but the service does not use it to forbid transitions; it is a documentation/validation aid. Flagged in §16.

### 9.3 Legacy `selected` mapping (read time only)

Legacy documents may still contain `status="selected"`. The system reconciles them **at read time**:

| Context | Mapping |
|---|---|
| `StatusBreakdownChart` / donut | `selected` → `shortlisted` |
| `ApplicationStatusBadge` | `selected` → renders "Shortlisted" |
| Student analytics counts | `selected` → `shortlisted`; `legacy_selected` counter increments |
| TPO `status_breakdown` | `selected` → `shortlisted`; `legacy_selected` counter |
| Admin `application_breakdown` | `selected` → `shortlisted`; `legacy_selected` counter |
| Admin workspace rows | `_effective_status` maps `selected` → `shortlisted` |
| TPO department/month/company/drive rows | **Raw `_status_value`** — legacy `selected` is excluded from these rows. Only `status_breakdown` reconciles. This is a known inconsistency (§16). |

No database writes and no deletions are performed for legacy rows.

**Invariant:** for the reconciled breakdown, `applied + shortlisted + rejected = total applications`. The current live dataset satisfies this (28 + 14 + 38 = 80, with `legacy_selected = 0`).

### 9.4 What the system does *not* claim

- Shortlisting is **not** placement. There is no offer/placement collection, so no confirmed-offer rate exists.
- "Placed Students" is not displayed anywhere.
- The admin API still computes `placed_students` and `placement_rate_pct` from legacy `selected` rows for backward compatibility, but the UI does not surface them.

---

## 10. Analytics data processing, chart by chart

### 10.1 Shared rules

1. **Effective status.** All breakdowns map legacy `selected` → `shortlisted` and keep a separate `legacy_selected` count.
2. **No fabricated points.** Monthly trends contain only months that have applications.
3. **No median/percentile/stddev.** The analytics services use arithmetic mean, ratio, max/min, sum/count, and `round(x, 1)` (market `_trend_score` uses 2 dp). **Formulas §11** is the full inventory.
4. **Assessment evidence.** Domain and skill scores come only from graded submitted attempts. Self-reported skills are reported separately.
5. **Empty states.** No-evidence radar returns zeros (student) or `[]` (TPO), and the UI shows an empty state.

### 10.2 Student dashboard (`/dashboard`)

| Chart | Source | Processing |
|---|---|---|
| Resume status card | `GET /resumes/history` | `is_active` resume exists or not |
| Applications card | `GET /analytics/student/me` → `total_applications` | Count of applications for the student profile |
| Shortlisted card | same → `applications.shortlisted` | Effective status count |
| Avg. assessment score | same → `average_score_pct` | Mean of submitted attempt percentages; `null` when no attempts |
| Profile completeness | `GET /students/me` → `profile_completeness_pct` | Stored percentage |
| Knowledge tracing snapshot | `GET /assessments/knowledge-states/me` | Per-skill `mastery_pct` from adaptive attempts |
| Application status donut | same → `applications` | Applied / Shortlisted / Rejected; `selected` folded into shortlisted |
| Domain readiness radar | same → `domain_scores` | Per domain: difficulty-weighted marks / maximum marks × 100, over answered questions in submitted attempts. Five fixed domains; zeros when no answers. |
| Assessment trend line | same → `assessment_trend` | One point per submitted attempt, ordered by `submitted_at`, `score_pct` |

Domain definitions and the weighting formula are in **Formulas §4**.

### 10.3 Student applications and insights

| UI element | Source | Processing |
|---|---|---|
| Summary cards | `GET /drives/applications/me` (client aggregation) | Counts by effective status |
| Applications table | same | Paged/filtered client-side |
| Status badge | `ApplicationStatusBadge` | `selected` → "Shortlisted" |
| Explanation panel | `GET /applications/{id}/explanation` | On-demand; Markdown rendered safely |
| Insights focus areas | `GET /insights/me` | Deterministic ranking of weak skills/domains |
| Mastery bars | `GET /assessments/knowledge-states/me` | `mastery_pct` per skill |

### 10.4 TPO dashboard (`/tpo/dashboard`)

| Chart | Source | Processing |
|---|---|---|
| Drive cards | `GET /analytics/tpo` | `total_drives`, `open_drives`, `closed_drives` |
| Student/application cards | `GET /analytics/tpo/applications` | `total_students`, `active_drives`, `total_applications`, `status_breakdown` |
| Application status donut | same → `status_breakdown` | Reconciled three-way split |
| Monthly Application Trends | same → `monthly_trend` | Grouped by `YYYY-MM` from `applied_at`, with applied/shortlisted/rejected/total. Single month → one column + note. |
| Department-wise applications and shortlisting | same → `departments` | Grouped bars by canonical student department; raw status counts |
| Company-wise applications | same → `companies` | Top-N by `company_sort` (`applications` / `shortlisted` / `name`); `company_count` reports distinct companies before truncation |
| Drive-wise applications and shortlisting | same → `drives` | Per-drive counts, grouped bars |
| Recruitment progress | same → `status_breakdown` | Progress bars: each status count and its share of total applications |
| Records panel | `GET /analytics/tpo/applications/records` | Paged, filterable by status/company/department |

**Rate cards.** `applied_rate_pct`, `shortlisting_rate_pct`, and `rejection_rate_pct` are each `count / total_applications × 100`, rounded to 1 dp. They are not mutually exclusive denominators across stages; see **Formulas §1**.

### 10.5 TPO analytics page

| Chart | Source | Processing |
|---|---|---|
| Application funnel card | `GET /analytics/tpo/applications` → `status_breakdown` | `StatusBreakdownChart`: reconciled three-way split across all the TPO's drives |
| Domain readiness radar | `GET /analytics/tpo/applications` → `domain_scores` | Aggregated across the TPO's drives from graded answers; `[]` when no evidence, and the chart shows an empty state |
| Drive breakdown | `GET /analytics/tpo/applications` → `drives` | Per-drive status counts |
| Drive detail panel — Rankings | `GET /analytics/tpo/drives/{drive_id}/ranking` | Ordered by `score_pct` desc; denominator uses answered-only marks |
| Drive detail panel — Applied students | `GET /analytics/tpo/drives/{drive_id}/applicants` | Paged applicants |
| Drive detail panel — Test participants | `GET /analytics/tpo/drives/{drive_id}/participants` | Unique students who started the drive assessment, with attempt status |

The per-drive Ranking / Applied students / Test participants panels live inside `components/analytics/drive-breakdown.tsx` and open per drive. `submitted_attempt_count` counts graded submitted attempts only. `participant_count` counts unique students who **started**; `submitted_participant_count` counts unique students with a submitted attempt. Drive-level funnel figures (`DriveFunnel`) come from `GET /analytics/tpo` and are shown on the TPO dashboard, not this page.

### 10.6 TPO Market Insights (`/tpo/dashboard/analytics/trending`)

| Chart | Source field | Processing |
|---|---|---|
| Summary cards | `GET /analytics/tpo/market` → summary | Posting counts, company counts, skill counts, current-period most-demanded skill, complete-year YoY growth with `yoy_growth_basis` |
| Historical trends | `historical_trends` | Postings per year/month on the comparable window |
| Trending skills | `trending_skills` | Ranked by demand-share momentum (`momentum_pct`); declining skills last |
| Emerging skills | `emerging_skills` | Growth comparison across comparable windows |
| Company analytics | `companies` | Posting counts and skill mix per company |
| Job-family section | `job_families` | Distribution by job family |
| Comparison | `GET /analytics/tpo/market/comparison` | Side-by-side skill demand across selected dimensions |
| Filters | `GET /analytics/tpo/market/filters` | Live years/companies/locations/sources |

All market figures are computed from `job_market_postings`. `data_origin` reports `mock`/`real`/`mixed`, and the banner states it. **Formulas §6** defines the growth and trend scores.

### 10.7 TPO skill gaps (`/tpo/dashboard/analytics/skill-gaps`)

| Element | Source field | Processing |
|---|---|---|
| Summary cards | `summary` | Skills analysed, high-priority gaps, student population, lacking demonstrated skills |
| Demand vs proficiency | `skills[]` | `demand_pct` (market) vs `demonstrated_pct` (assessment) |
| Priority gaps table | `skills[]` | `priority_score` from demand, gap, and trend weights; `priority_class` thresholds from `meta.thresholds` |
| Skill detail | `skills[]` | `top_companies`, `top_job_families`, `years`, growth |
| Students panel | `GET …/{skill_id}/students` | Per-student classification: demonstrated / developing / not demonstrated / insufficient evidence |
| Training recommendations | derived in UI | Skills with the largest demonstrated gaps |

Student evidence uses only graded attempts on questions tagged with the skill. Self-reported skills are separate (`students_reported`, `students_reported_only`). Thresholds: `min_graded_answers`, `demonstrated_min_pct`, `developing_min_pct`. **Formulas §5**.

### 10.8 Admin dashboard (`/admin/dashboard`)

| Chart | Source | Processing |
|---|---|---|
| Platform cards | `GET /analytics/admin` | Students, companies, drives (+ open/closed), applications, TPOs |
| Platform snapshot | `GET /analytics/admin` | Total students, companies, drives, and students with at least one application |
| User distribution donut | `GET /analytics/admin/activity` → `user_distribution` | Students / TPOs / Admins, counted once per account |
| Assessment performance grid | `GET /analytics/admin` | Assessments, attempts, submitted attempts, average score, completion rate (submitted ÷ attempts), questions, categories |

The page does not render the application-status donut, department distribution, monthly activity trend, or skill-mastery list. Those values are still returned by the analytics endpoints.

### 10.9 Admin analytics data (`GET /analytics/admin`)

There is no separate admin analytics page; these fields feed `/admin/dashboard` (§10.8).

| Chart / element | Source | Processing |
|---|---|---|
| Stat cards | `GET /analytics/admin` | `total_students`, `total_tpos`, `total_companies`, `total_drives` (+ `open_drives`) |
| Application status breakdown | `application_breakdown` | Reconciled three-way split + `legacy_selected` (internal, not plotted) |
| Assessment performance | `total_assessments`, `total_attempts`, `submitted_attempts`, `average_score_pct`, `total_questions`, `total_categories` | Direct counts; average over submitted attempts with nonzero maximum marks |
| Skill mastery overview | `skill_mastery_overview` | Per-skill average mastery across students with attempts, weakest first (API-only; not rendered) |

`GET /analytics/admin/activity` also returns monthly activity and department counts, and `GET /analytics/admin` returns application-status and skill-mastery fields; the dashboard currently renders only `user_distribution` from the activity payload. The other values remain API-only.

### 10.10 Admin applications workspace (`/admin/dashboard/drives`)

| Element | Source | Processing |
|---|---|---|
| Summary cards | `GET /analytics/admin/applications` → `summary` | `total`, `applied`, `shortlisted`, `rejected`, `legacy_selected` |
| Filters | `GET /analytics/admin/applications/filters` | Live companies, drives, departments |
| Table | `GET /analytics/admin/applications` | Paged; each row joins student, company, drive, assessment, score, rank |
| Status change | `PATCH /drives/{drive_id}/applications/{application_id}` | Same service as TPO; row refreshes |

### 10.11 Aggregation notes

- The backend performs aggregation in Python after fetching with Motor; it does **not** use MongoDB aggregation pipelines for these dashboards.
- Application counts are grouped in memory with dictionaries keyed by canonical department/company/month.
- `round(x, 1)` is applied at the response-model boundary for percentages.
- Date filters (`date_from`, `date_to`) are applied to `applied_at` before grouping.
- No caching layer exists for analytics; each request recomputes. This is acceptable at the current data volume but is a scaling limit (§16).

---

## 11. Backend and API reference

### 11.1 Conventions

- **Base URL:** `{API_V1_PREFIX}` = `/api/v1` (from `Settings.API_V1_PREFIX`).
- **Frontend path:** `/api/backend/<path>` rewrites to `<NEXT_PUBLIC_API_URL>/api/v1/<path>`.
- **Auth:** `Authorization: Bearer <access JWT>`.
- **Access column:** `public` = no auth; `auth` = any authenticated user; `student` / `tpo` / `admin` = role-restricted.
- **Errors:** `{"detail": "..."}`. Some domain errors use a structured object (e.g. placement deficits). The global handler returns `{"detail": "An unexpected error occurred. Please try again later."}` with `500`.
- **Total:** 104 route decorators across 16 routers, plus the unprefixed `GET /health` alias = 105 exposed method/path pairs.

### 11.2 Health

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/api/v1/health` | `health_check` | public |
| GET | `/health` | `health_check` (alias) | public |

Returns `{"status":"ok","database":"connected"|"unreachable"}`.

### 11.3 Auth (`/api/v1/auth`)

| Method | Path | Handler | Access |
|---|---|---|---|
| POST | `/auth/register/student` | `register_student` | public |
| POST | `/auth/register/tpo` | `register_tpo` | public |
| POST | `/auth/login` | `login` | public |
| POST | `/auth/google` | `google_auth` | public |
| POST | `/auth/refresh` | `refresh` | public |
| POST | `/auth/logout` | `logout` | public |
| POST | `/auth/forgot-password` | `forgot_password` | public |
| POST | `/auth/reset-password` | `reset_password` | public (token in body) |
| GET | `/auth/me` | `get_me` | auth |

Rate limited: `register/student`, `register/tpo`, `login`, `google`, `forgot-password` at `RATE_LIMIT_AUTH` (10/min).

### 11.4 Students (`/api/v1/students`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/students/me` | `get_my_profile` | student |
| PUT | `/students/me` | `update_my_profile` | student |

### 11.5 Resumes (`/api/v1/resumes`)

| Method | Path | Handler | Access |
|---|---|---|---|
| POST | `/resumes` | `upload_resume` | student |
| GET | `/resumes/history` | `resume_history` | student |
| GET | `/resumes/{resume_id}` | `get_resume` | auth |
| POST | `/resumes/{resume_id}/reparse` | `reparse_resume` | student |
| GET | `/resumes/{resume_id}/download` | `download_resume` | auth |
| GET | `/resumes/{resume_id}/autofill-suggestion` | `get_autofill_suggestion` | student |
| POST | `/resumes/{resume_id}/autofill-apply` | `apply_autofill` | student |

### 11.6 Drives (`/api/v1/drives`)

| Method | Path | Handler | Access |
|---|---|---|---|
| POST | `/drives` | `create_drive` | tpo |
| GET | `/drives` | `list_drives` | auth |
| GET | `/drives/applications/me` | `my_applications` | student |
| GET | `/drives/mine` | `list_my_drives` | tpo |
| GET | `/drives/{drive_id}` | `get_drive` | auth |
| PUT | `/drives/{drive_id}` | `update_drive` | tpo |
| DELETE | `/drives/{drive_id}` | `delete_drive` | tpo |
| POST | `/drives/{drive_id}/clone` | `clone_drive` | tpo |
| POST | `/drives/{drive_id}/apply` | `apply_to_drive` | student |
| GET | `/drives/{drive_id}/screening-summary` | `get_screening_summary` | tpo |
| POST | `/drives/{drive_id}/screen` | `trigger_screening` | tpo |
| GET | `/drives/{drive_id}/recommended-shortlist` | `get_recommended_shortlist` | tpo |
| GET | `/drives/{drive_id}/applications` | `get_drive_applications` | tpo, admin |
| PATCH | `/drives/{drive_id}/applications/bulk-status` | `bulk_update_application_status` | tpo, admin |
| GET | `/drives/{drive_id}/applications/export` | `export_applications_csv` | tpo |
| PATCH | `/drives/{drive_id}/applications/{application_id}` | `update_application_status` | tpo, admin |

### 11.7 Questions (`/api/v1/questions`)

| Method | Path | Handler | Access |
|---|---|---|---|
| POST | `/questions/categories` | `create_category` | admin |
| GET | `/questions/categories` | `list_categories` | admin, tpo |
| POST | `/questions` | `create_question` | admin |
| GET | `/questions` | `list_questions` | admin, tpo |
| GET | `/questions/stats` | `question_stats` | admin, tpo |
| PUT | `/questions/{question_id}` | `update_question` | admin |
| PATCH | `/questions/{question_id}/status` | `set_question_status` | admin |
| DELETE | `/questions/{question_id}` | `delete_question` | admin |
| POST | `/questions/import` | `import_questions` | admin |
| POST | `/questions/import/preview` | `preview_import` | admin |
| POST | `/questions/import/commit` | `commit_import` | admin |
| POST | `/questions/import/error-report` | `import_error_report` | admin |
| GET | `/questions/export/excel` | `export_excel` | admin |
| GET | `/questions/export/template` | `export_template` | admin |
| GET | `/questions/export` | `export_questions` | admin |

### 11.8 Assessments (`/api/v1/assessments`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/assessments/templates/presets` | `template_presets` | admin |
| GET | `/assessments/templates` | `list_templates` | admin |
| POST | `/assessments/templates` | `create_template` | admin |
| GET | `/assessments/templates/{template_id}` | `get_template` | admin |
| PUT | `/assessments/templates/{template_id}` | `update_template` | admin |
| POST | `/assessments/templates/{template_id}/duplicate` | `duplicate_template` | admin |
| PATCH | `/assessments/templates/{template_id}/status` | `set_template_status` | admin |
| DELETE | `/assessments/templates/{template_id}` | `delete_template` | admin |
| POST | `/assessments/placement/eligibility` | `placement_eligibility` | admin |
| POST | `/assessments/placement/generate` | `generate_placement_assessment` | admin |
| POST | `/assessments/placement/{assessment_id}/revise` | `revise_placement_assessment` | admin |
| GET | `/assessments/placement/{drive_id}/participation` | `placement_participation` | admin, tpo |
| POST | `/assessments` | `create_assessment` | admin |
| GET | `/assessments` | `list_assessments` | auth |
| GET | `/assessments/knowledge-states/me` | `my_knowledge_states` | student |
| GET | `/assessments/knowledge-states/{student_id}` | `student_knowledge_states` | tpo, admin |
| POST | `/assessments/{assessment_id}/start` | `start_assessment` | student |
| GET | `/assessments/attempts/{attempt_id}/questions` | `get_attempt_questions` | student |
| POST | `/assessments/attempts/{attempt_id}/answer` | `submit_answer` | student |
| POST | `/assessments/attempts/{attempt_id}/finish` | `finish_attempt` | student |
| POST | `/assessments/attempts/{attempt_id}/run-code` | `run_code` | student |
| POST | `/assessments/attempts/{attempt_id}/violation` | `report_violation` | student |
| GET | `/assessments/attempts/{attempt_id}/results` | `get_attempt_results` | student |

### 11.9 Matching (`/api/v1/matching`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/matching/drives/{drive_id}/score` | `get_drive_match_score` | student |
| GET | `/matching/recommended-drives` | `get_recommended_drives` | student |
| GET | `/matching/drives/{drive_id}/ranked-applicants` | `get_ranked_applicants` | tpo |

### 11.10 Applications (`/api/v1/applications`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/applications/{application_id}/explanation` | `get_application_explanation` | auth |

### 11.11 Analytics (`/api/v1/analytics`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/analytics/tpo` | `get_tpo_analytics` | tpo |
| GET | `/analytics/student/me` | `get_student_analytics` | student |
| GET | `/analytics/tpo/applications` | `get_tpo_application_analytics` | tpo |
| GET | `/analytics/tpo/applications/records` | `get_tpo_application_records` | tpo |
| GET | `/analytics/tpo/drives/{drive_id}/ranking` | `get_drive_ranking` | tpo, admin |
| GET | `/analytics/tpo/drives/{drive_id}/applicants` | `get_drive_applicants` | tpo |
| GET | `/analytics/tpo/drives/{drive_id}/participants` | `get_drive_participants` | tpo |
| GET | `/analytics/tpo/skill-gaps` | `get_skill_gaps` | tpo |
| GET | `/analytics/tpo/skill-gaps/filters` | `get_skill_gap_filters` | tpo |
| GET | `/analytics/tpo/skill-gaps/{skill_id}/students` | `get_skill_gap_students` | tpo |
| GET | `/analytics/admin/activity` | `get_admin_activity` | admin |
| GET | `/analytics/admin` | `get_admin_analytics` | admin |
| GET | `/analytics/admin/applications` | `get_admin_applications` | admin |
| GET | `/analytics/admin/applications/filters` | `get_admin_application_filters` | admin |

### 11.12 Market analytics (`/api/v1/analytics`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/analytics/tpo/market` | `get_market_analytics` | tpo |
| GET | `/analytics/tpo/market/filters` | `get_market_filters` | tpo |
| GET | `/analytics/tpo/market/comparison` | `get_market_comparison` | tpo |

### 11.13 Insights, JD explanation, gap analysis

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/insights/me` | `my_insights` | student |
| GET | `/drives/{drive_id}/match-explanation` | `get_match_explanation` | student |
| GET | `/assessments/attempts/{attempt_id}/gap-analysis` | `get_gap_analysis` | student |

### 11.14 Knowledge store (`/api/v1/admin/knowledge`)

| Method | Path | Handler | Access |
|---|---|---|---|
| POST | `/admin/knowledge/chunks` | `ingest_chunks` | admin |
| DELETE | `/admin/knowledge/{source_id}` | `delete_source` | admin |
| GET | `/admin/knowledge/stats` | `knowledge_stats` | admin |

### 11.15 Observability (`/api/v1/admin/observability`)

| Method | Path | Handler | Access |
|---|---|---|---|
| GET | `/admin/observability/llm` | `llm_observability` | admin |

### 11.16 Role access matrix (summary)

| Capability | Student | TPO | Admin |
|---|---|---|---|
| Register/login/refresh | ✔ | ✔ | ✔ (login only; created by CLI) |
| Profile | own | own | — |
| Resume | own | download via drive | — |
| Drives | read/apply | create/update/delete/clone | read |
| Applications | own | drive-scoped + status | all + status |
| Assessments | take | read | full CRUD + generation |
| Question bank | — | read | full CRUD + import/export |
| Analytics | own | own drives | platform |
| Market/skill gaps | — | ✔ | — |
| Knowledge store / LLM metrics | — | — | ✔ |

**Cross-reference:** every endpoint above is exercised by the page/hook map in §3–§5. Endpoints with no UI caller are called out in §16.

---

## 12. MongoDB lifecycle

### 12.1 Connection and startup

`backend/app/core/database.py`:

- `connect_to_mongo()` creates a single `AsyncIOMotorClient` from `MONGODB_URI`.
- `main.py`'s lifespan calls connect → `ensure_indexes()` → yield → `close_mongo_connection()`.
- `get_database()` is the FastAPI dependency and raises if the connection was not initialised.
- `MONGODB_DB_NAME` defaults to `placer_db`.

### 12.2 Index catalogue

Created by `ensure_indexes()`:

| Collection | Index |
|---|---|
| `users` | `email` unique |
| `refresh_tokens` | `token_hash` unique; `expires_at` TTL |
| `knowledge_states` | `(student_id, skill_tag)` unique |
| `questions` | `(category_id, difficulty)`; `status`; `topic` sparse; `skill` sparse; `type`; `updated_at` sparse |
| `notifications` | `(user_id, read, created_at desc)` |
| `resumes` | `(student_id, is_active)`; `(student_id, version desc)` |
| `applications` | `(drive_id, final_score desc)`; `(drive_id, student_id)` unique; `student_id`; `assessment_attempt_id` sparse |
| `placement_drives` | `(status, deadline)`; `created_by` |
| `companies` | `name` |
| `assessment_attempts` | `(student_id, started_at desc)`; `assessment_id`; `(assessment_id, student_id)`; `(assessment_id, student_id, status)` |
| `activity_logs` | `(user_id, timestamp desc)`; `(entity, entity_id)` |
| `students`, `tpos`, `admins` | `user_id` unique |
| `assessments` | `drive_id` sparse; `(format, status)` |
| `assessment_templates` | `status`; `preset_key` sparse |
| `job_market_postings` | `external_id` unique; `posted_at`; `year`; `company_slug`; `job_family`; `location`; `required_skills`; `technical_skills`; `soft_skills`; `source` |
| `market_skill_catalog` | `slug` unique |
| `market_import_runs` | (created by import script) |

**Not indexed at startup:** `password_reset_tokens`, `knowledge_chunks`, `insights_narrative_cache`, `unmapped_skill_suggestions` (repository-level de-dupe only). These are small today but are a scaling gap (§16).

### 12.3 TTL and retention

- `refresh_tokens.expires_at` has `expireAfterSeconds=0`, so MongoDB removes expired tokens automatically.
- `password_reset_tokens` relies on application checks; there is no TTL index.
- No other collection has TTL. Activity logs, attempts, and market data grow without automatic pruning.

### 12.4 Write patterns and denormalization

- **One active resume** per student, enforced by deactivating prior versions before insert.
- **One application** per `(drive, student)`, enforced by a unique index.
- **Scores are persisted** on the application after screening (`final_score`, sub-scores, matched/missing skills) so historical results do not change when a resume is re-parsed.
- **Embeddings are cached** on `resumes.resume_embedding` and `placement_drives.jd_embedding`. JD text changes invalidate the JD cache.
- **Knowledge states** are upserted per `(student, skill_tag)` on attempt finish, with a `history` array.
- **Activity logs** are append-only.
- **No cascading deletes.** Deleting a drive or a user does not delete dependent applications/attempts. Read paths tolerate orphans; this is a known gap.

### 12.5 Consistency and reconciliation

- **Assessment status** on an application is reconciled during screening and when the drive is read (`reconcile_expired_assessments`).
- **Legacy `selected`** is reconciled at read time only; no migration writes.
- **Department strings** are normalized on write for new records, and on read for display. A one-off audit script (`normalize_departments.py`) can repair historical values with `--apply`.
- **Counts** are recomputed per request; there is no materialized aggregate to drift.

---

## 13. Deployment and runtime

### 13.1 Local development

Prerequisites: Python 3.12, Node.js, MongoDB (local or Docker).

```powershell
# Backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # fill JWT_SECRET_KEY etc.
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
copy .env.local.example .env.local
npm run dev                 # http://localhost:3000
```

- API docs: `http://localhost:8000/api/docs`.
- Health: `http://localhost:8000/health` and `/api/v1/health`.
- Frontend proxy target: `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`).

### 13.2 Docker Compose

`docker-compose.yml` defines three services:

| Service | Image/build | Port | Notes |
|---|---|---|---|
| `mongodb` | `mongo:7` | `27017` | Bind mount `./mongodb-data:/data/db`; healthcheck `mongosh --eval db.adminCommand('ping')` |
| `backend` | `./backend/Dockerfile` | `8000` | `env_file: ./backend/.env`; `MONGODB_URI=mongodb://mongodb:27017`; depends on healthy MongoDB; mounts `./backend/app` and `./backend/storage` |
| `frontend` | *(not defined in compose)* | — | The frontend is run separately with `npm run dev` / `npm run build && npm start` |

`backend/Dockerfile`:

- Base `python:3.12-slim`.
- Installs `build-essential`, `curl`, `libgl1`, `libglib2.0-0`, `libgomp1` (PyMuPDF/spaCy/OpenCV/PaddleOCR).
- Installs `requirements.txt`, copies the app.
- `EXPOSE 8000`.
- `HEALTHCHECK` curls `/api/v1/health` every 30 s.
- `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.

> Note: the compose file has no `frontend` service. Deploying the UI requires a separate Node build/run or an external host. This is a deployment gap (§16).

### 13.3 Environment configuration

`backend/app/core/config.py` (`Settings`, cached with `lru_cache`) and `backend/.env.example`.

| Group | Keys |
|---|---|
| App | `APP_NAME`, `APP_ENV`, `DEBUG`, `API_V1_PREFIX` |
| JWT | `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `BCRYPT_ROUNDS` |
| Database | `MONGODB_URI`, `MONGODB_DB_NAME` |
| CORS | `CORS_ORIGINS` |
| Cookie | `REFRESH_TOKEN_COOKIE_NAME`, `COOKIE_SECURE`, `COOKIE_DOMAIN` |
| Google | `GOOGLE_CLIENT_ID` |
| Storage | `STORAGE_BACKEND`, `CLOUDINARY_*`, `LOCAL_STORAGE_PATH`, `MAX_RESUME_SIZE_MB` |
| Rate limit | `RATE_LIMIT_DEFAULT`, `RATE_LIMIT_AUTH` |
| ML | `ML_ARTIFACTS_DIR` |
| OCR | `OCR_ENABLED`, `OCR_LANG`, `OCR_USE_GPU`, `OCR_USE_ANGLE_CLS`, `OCR_CONFIDENCE_THRESHOLD`, `OCR_TRIGGER_MIN_CHARS`, `OCR_MIN_ALPHANUMERIC_RATIO`, `OCR_RENDER_DPI`, `OCR_PYTHON_PATH` |
| LLM | `LLM_PRIMARY_*`, `LLM_FALLBACK_*`, `LLM_USE_LOCAL_OLLAMA`, `OLLAMA_*`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES`, `LLM_RETRY_BACKOFF_SECONDS` |
| Embeddings | `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_API_KEY`, `EMBEDDING_DIM` |
| RAG | `KNOWLEDGE_STORE_BACKEND` |
| Code execution | `CODE_EXECUTION_ENABLED`, `CODE_EXECUTION_TIMEOUT_SECONDS`, `CODE_EXECUTION_TOTAL_TIMEOUT_SECONDS`, `CODE_EXECUTION_MAX_CODE_BYTES`, `CODE_EXECUTION_MAX_OUTPUT_BYTES`, `CODE_EXECUTION_MAX_TEST_CASES` |

`validate_production_config()` blocks unsafe defaults only when `APP_ENV=production` (for example, a default JWT secret or insecure cookie settings).

### 13.4 Health and readiness

- `GET /health` and `GET /api/v1/health` return service + database status.
- The Docker healthcheck uses the prefixed path.
- There is no separate readiness/liveness split and no metrics endpoint (Prometheus). LLM metrics are available only as JSON at `/api/v1/admin/observability/llm`.

### 13.5 Frontend build and proxy

- `npm run build` then `npm start` for production.
- `next.config.mjs` rewrites `/api/backend/:path*` using `NEXT_PUBLIC_API_URL`.
- `images.remotePatterns` allows `res.cloudinary.com`.
- `reactStrictMode: true`.

### 13.6 Storage

- `STORAGE_BACKEND=local` writes under `LOCAL_STORAGE_PATH` and stores `local://…` references in MongoDB.
- `STORAGE_BACKEND=cloudinary` uploads to Cloudinary and stores the secure URL.
- Docker mounts `./backend/storage` so local files survive container rebuilds.

---

## 14. Error handling, security, and observability

### 14.1 Error taxonomy

| Source | Behaviour |
|---|---|
| Pydantic validation | `422` with field errors |
| `HTTPException` in routers | Status + `{"detail": …}` |
| Domain errors (`DriveError`, `ResumeError`, `AssessmentError`, `PlacementGenerationError`) | Mapped by routers to `400/403/404/409/413/422` |
| Screening errors | Mapped to `400` (over-broad; see §16) |
| `LLMUnavailableError` | `503` or graceful fallback |
| Unhandled exception | Global handler logs with request ID, returns generic `500` (no stack trace) |

### 14.2 Authentication and authorization

- **Access token:** JWT, short-lived (15 min default), held in memory only (`lib/token-store.ts`). Never in `localStorage`.
- **Refresh token:** opaque, httpOnly cookie `placer_refresh_token`, SHA-256 hashed in `refresh_tokens`, rotated on every refresh.
- **Role guard:** `require_role(...)` on the backend is authoritative.
- **Frontend guards:** `middleware.ts` reads the non-httpOnly `placer_role` cookie for UX redirects; role layouts are client-side backstops. Neither is a security boundary.
- **Google:** `verify_google_token()` validates the ID token; errors map to `401`/`503`.

### 14.3 Input validation and upload safety

- Pydantic models bound string lengths, numeric ranges, and enums.
- Resume upload: size cap enforced while streaming, `%PDF` magic check, SHA-256 duplicate detection.
- Question import: extension + signature check, 10 MB / 5,000 rows / 20,000 chars caps, formula non-evaluation, CSV injection neutralization on export.
- File download routes check ownership (`auth`) before serving.
- Code execution is a best-effort local subprocess runner with timeouts and output caps. It is **not** a hardened sandbox.

### 14.4 Rate limiting (partial)

- `core/limiter.py` defines `Limiter(default_limits=[RATE_LIMIT_DEFAULT])`.
- **`SlowAPIMiddleware` is not registered**, so `default_limits` is not applied globally.
- Only these routes are actually limited:
  - `POST /auth/register/student`, `/auth/register/tpo`, `/auth/login`, `/auth/google`, `/auth/forgot-password` at `RATE_LIMIT_AUTH` (10/min).
  - `GET /insights/me` at `20/minute`.
- This is a known gap: most endpoints are effectively unthrottled (§16).

### 14.5 Secrets, cookies, and CORS

- Secrets come from env only; `.env` is git-ignored.
- `COOKIE_SECURE=true` is required in production (HTTPS).
- `CORS_ORIGINS` is an explicit allow-list.
- JWT algorithm is configurable (`HS256` default); no `none` algorithm.

### 14.6 Logging, request IDs, and metrics

- `RequestIdMiddleware` echoes `X-Request-ID` and injects `request_id` into every log record via a logging filter.
- `configure_logging()` installs the filter before the app is constructed.
- LLM metrics are in-process counters (`app/ml/llm/metrics.py`), exposed to admins.
- `activity_logs` records status decisions with actor, role, reasons, and IP.

### 14.7 Known security gaps

| Gap | Impact |
|---|---|
| `POST /drives/{drive_id}/clone` has no ownership check | A TPO can clone another TPO's drive if they know the ID |
| Screening maps any exception to `400` | Misleading errors; can hide server faults |
| `bulk-status` returns `200` with per-item failures | Callers must inspect the body |
| `applications.py` leaks `str(exc)` on `500` | Potential internal detail disclosure |
| `SlowAPIMiddleware` not registered | Default rate limits unused |
| Code runner is not sandboxed | Untrusted code executes on the host |
| Anti-cheat signals stored but not enforced | `fingerprint_hash`/`ip_address` never compared; fullscreen is client-side |
| No CSRF token on cookie-based refresh | Mitigated by `SameSite` cookie settings, but not explicitly defended |
| No admin user-management audit UI | Admin actions are only partially visible |

These are documented rather than silently ignored. See §16.

---

## 15. End-to-end illustrative example

> **This example is illustrative only.** Names, IDs, scores, and timings are invented to show the flow. They are **not** records from the live database, and no formula constant is changed by the example.

**Scenario.** A student, *A. Sharma*, applies to a drive and completes its assessment.

1. **Registration.** A. Sharma registers at `/register` with department "CS". The backend normalizes it to "Computer Science", creates a `users` row (role `student`) and a `students` profile.
2. **Resume.** She uploads `resume.pdf` (180 KB). The upload passes the size/magic/hash checks, is stored as version 1 and marked active, PyMuPDF extracts text, the LLM extracts skills (falling back to regex if needed), and autofill suggests her phone and skills.
3. **Discovery.** `GET /drives` lists open drives. `GET /matching/recommended-drives` ranks them using the hybrid score. She opens one drive and sees `semantic=0.71`, `skills=0.60`, `experience=1.00`, and `final=0.66` (assessment term 0 at this point).
4. **Apply.** `POST /drives/{drive_id}/apply` checks active resume, eligibility (CGPA/department/batch), and duplicate application. It inserts an `applications` row with `status="applied"` and `assessment_status="pending"` because the drive requires an assessment.
5. **Assessment.** The drive is linked to a standardized assessment (5 sections, 20 questions, 6/10/4 difficulty mix, 1/3/5 marks). She starts it, answers 20 questions, and finishes. The attempt is graded; MCQ answers are exact-match, one coding answer passes all test cases, and negative marking subtracts for two wrong MCQs. Her percentage is computed and `knowledge_states` are updated.
6. **Screening.** The TPO opens the applicants page and triggers `POST /drives/{drive_id}/screen`. The service reconciles her assessment (`pending` → `passed` if she met `assessment_min_score_pct`), computes and persists the four match scores, and leaves her status as `applied`.
7. **Shortlist.** The TPO reviews the recommended shortlist (`final_score >= 0.65` and assessment passed) and sets her status to `shortlisted`. `decision_at` is set and an `activity_logs` entry is written.
8. **Student view.** Her `/dashboard` donut now shows one shortlisted application; the applications page badge reads "Shortlisted". She opens the explanation, which narrates the already-computed eligibility, scores, and assessment result, grounded in retrieved knowledge chunks.
9. **Analytics.** The TPO dashboard's `status_breakdown` increments `shortlisted`; the monthly trend still shows the month of `applied_at`; the admin workspace row shows her effective status as `shortlisted` with the assessment score and rank.
10. **Outcome.** No placement/offer record is created. Shortlisting is the terminal state the system models. If the TPO later rejects her, the status becomes `rejected`, a rejection reason is stored, and the counts move accordingly.

**What this example demonstrates:** every arrow is a real endpoint/collection; every number is either user input, a deterministic computation, or an LLM narration of already-computed facts. Nothing is fabricated.

---

## 16. Known gaps and partial features

| Area | Status | Detail |
|---|---|---|
| Admin user/student/TPO management | **Not implemented** | No pages or endpoints for listing/editing/deactivating users. |
| Company CRUD | **Not implemented** | Companies are created on demand from drives; no admin management UI. |
| Notifications | **Not implemented** | `notifications` collection is index-only; no read/write code. |
| Activity-log viewer | **Not implemented** | Activity is aggregated into analytics; no raw log page. |
| Placement/offer records | **Not implemented** | No collection; "Placed Students" is never shown. |
| `placed_students` / `placement_rate_pct` | **Computed, not displayed** | Derived from legacy `selected` only; kept for API compatibility. |
| Legacy `selected` in TPO department/month/company/drive rows | **Inconsistent** | These rows use raw status values; only `status_breakdown` reconciles. |
| `VALID_STATUS_TRANSITIONS` | **Declared, not enforced** | Free toggling among the three managed statuses. |
| `POST /drives/{id}/clone` ownership | **Gap** | No TPO ownership check. |
| Screening error mapping | **Over-broad** | Any exception → `400`. |
| `bulk-status` | **Partial success** | `200` with `failed_ids`/`errors`. |
| `applications.py` 500 handler | **Leaks `str(exc)`** | Should use the generic message. |
| Global rate limiting | **Partial** | `SlowAPIMiddleware` not registered; only 6 routes limited. |
| Anti-cheat enforcement | **Partial** | Signals stored, never compared; fullscreen not backend-enforced. |
| Code execution | **Partial / unsafe** | Local subprocess, not a sandbox. |
| `password_reset_tokens`, `knowledge_chunks`, `insights_narrative_cache`, `unmapped_skill_suggestions` | **Unindexed** | No startup indexes. |
| Frontend in Docker Compose | **Missing** | Only MongoDB + backend are defined. |
| Analytics caching | **None** | Recomputed per request. |
| Median/stddev/percentile | **Not implemented** | Only mean/ratio/sum/count/max/min. |
| LLM/RAG local testability | **Blocked locally** | Requires API keys or a running Ollama; otherwise deterministic fallbacks apply. |
| `gap-analysis` and `match-explanation` UI | **API-only** | Endpoints exist; no page calls them. |
| `unmapped_skill_suggestions` review UI | **Not implemented** | Queue is written but no admin screen reads it. |
| Drive deletion cascade | **Not implemented** | Applications/attempts are left orphaned. |

---

## 17. Cross-references and maintenance

### 17.1 Cross-document map

| Question | Where to look |
|---|---|
| How does the system behave end to end? | [`SYSTEM_FLOW.md`](./SYSTEM_FLOW.md) |
| What are the layers and components? | Architecture §A |
| What are the entities and relationships? | Architecture §B |
| What is the physical schema? | Architecture §C |
| What are the 15 data flows? | Architecture §D |
| How does each role move through the system? | Architecture §E |
| How does the AI model run inference? | Architecture §F |
| How is each number computed? | Formulas §1–§11 |
| Which formulas are not implemented? | Formulas §12 |
| Which code implements each formula? | Formulas §13 |
| How does data move between pages/APIs/collections? | This document §3–§10 |
| What are the exact endpoints and roles? | This document §11 |
| How is it deployed? | This document §13 |
| What is missing or partial? | This document §16 |

### 17.2 Source-of-truth files

| Concern | File |
|---|---|
| App wiring, middleware, exception handler | `backend/app/main.py` |
| Settings and production guard | `backend/app/core/config.py` |
| DB connection + indexes | `backend/app/core/database.py` |
| Auth dependencies | `backend/app/core/deps.py`, `core/security.py` |
| Canonical departments | `backend/app/core/departments.py`, `frontend/lib/departments.ts` |
| Application/drive models | `backend/app/models/drive.py` |
| Assessment models | `backend/app/models/assessment.py` |
| Analytics response models | `backend/app/models/analytics.py` |
| Drive lifecycle | `backend/app/services/drive_service.py` |
| Assessment grading/attempts | `backend/app/services/assessment_service.py` |
| Placement generation | `backend/app/services/placement_assessment_service.py` |
| Screening | `backend/app/services/screening_service.py` |
| Analytics aggregation | `backend/app/services/analytics_service.py` |
| Resume pipeline | `backend/app/services/resume_service.py`, `resume_parsing_service.py`, `profile_autofill_service.py` |
| Matching | `backend/app/services/matching_service.py`, `backend/app/ml/matching/inference.py` |
| LLM client/metrics | `backend/app/ml/llm/client.py`, `metrics.py` |
| RAG | `backend/app/ml/rag/knowledge_store.py` |
| Frontend API wrapper | `frontend/lib/api-client.ts`, `lib/token-store.ts` |
| Frontend proxy | `frontend/next.config.mjs` |
| Frontend guards | `frontend/middleware.ts`, `app/(*)/layout.tsx` |
| Deployment | `docker-compose.yml`, `backend/Dockerfile`, `backend/.env.example` |

### 17.3 Maintenance rules

1. **Keep the four documents in sync.** If an endpoint, collection, formula, or status rule changes, update the relevant document in the same change.
2. **Do not reintroduce synthetic labels.** Provenance stays internal; only the Market Insights source banner is intentionally user-visible.
3. **Do not add a fifth doc file** to `docs/` without an explicit decision; the project is scoped to four (this design doc, `SYSTEM_FLOW.md`, the formulas doc, and the architecture `.mmd`).
4. **Do not write legacy `selected` to the database.** Map at read time.
5. **Do not infer placement from shortlisting.** No "Placed Students" metric without an offer collection.
6. **Validate Mermaid before publishing.** Each `.mmd` group is standalone; paste it into a renderer after edits.

---

*End of document.*
