# PLACER — AI-Powered Campus Recruitment & Placement Assistance System

A full-stack placement platform for **Students**, **TPOs** (Training & Placement
Officers), and **Admins**: resume upload/parsing/OCR, AI semantic job matching,
standardized and adaptive assessments with an isolated code judge, screening and
shortlisting, placement analytics, market-demand insights, skill-gap analysis,
and grounded LLM/RAG coaching narratives.

**Tech stack:** FastAPI (Python) + MongoDB, Next.js 15 + React 19 + TypeScript +
Tailwind, JWT auth with rotating refresh cookies, a fine-tuned bi-encoder /
cross-encoder pair for resume-to-job matching, and an optional OpenAI-compatible
LLM + embedding provider.

This README is the canonical "get it running and see it work" guide. For the
phase-by-phase build history see [`PROJECT_PROGRESS.md`](./PROJECT_PROGRESS.md).
For how the system works end to end see
[`docs/SYSTEM_FLOW.md`](./docs/SYSTEM_FLOW.md).

---

## Documentation

| Document | What it covers |
|---|---|
| [`docs/SYSTEM_FLOW.md`](./docs/SYSTEM_FLOW.md) | **Start here for behaviour.** End-to-end flows: auth, resume → OCR → parse → autofill, matching, drives/applications/screening, assessments/judge/grading, analytics/market/skill gaps/insights, RAG/LLM, data stores. Includes Mermaid diagrams. |
| [`docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md`](./docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md) | Detailed system design: page-by-page data flow, collection inventory, API reference (104 route decorators), deployment, security, known gaps. |
| [`docs/PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md`](./docs/PLACER_MATHEMATICAL_FORMULAS_AND_ALGORITHMS.md) | Every implemented calculation with worked examples: matching, grading, mastery, analytics, skill gaps, market trends, insights, RAG. |
| [`docs/PLACER_SYSTEM_ARCHITECTURE.mmd`](./docs/PLACER_SYSTEM_ARCHITECTURE.mmd) | Standalone Mermaid diagram groups A–F: architecture, ER model, physical schema, DFD, role workflows, AI inference. |
| [`docs/SEED_DATA.md`](./docs/SEED_DATA.md) | Deterministic local dataset: 500 questions, 50 students, 18 drives, 25 assessments, 7,469 market postings, verification rules. |
| [`docs/CODE_EXECUTION_JUDGE.md`](./docs/CODE_EXECUTION_JUDGE.md) | Coding-question execution model and the isolated judge service. |
| [`credentials.md`](./credentials.md) | Local-only logins and a role-by-role verification checklist (git-ignored). |

---

## What the system does

### Student
- Profile with completeness scoring, resume upload/history, parsed-resume
  preview, and reviewable profile autofill.
- Browse open drives with server-side eligibility checks (CGPA, department,
  batch year), see the match score and matched/missing skills, and apply.
- Take practice assessments (adaptive) and drive assessments (standardized),
  including coding questions graded by the isolated judge.
- View results, skill mastery, and AI insights; per-attempt gap analysis is
  available through the API.

### TPO
- Create, edit, clone, publish/close drives with JD, required skills,
  eligibility, deadline, and a linked standardized assessment.
- Screen applicants: recompute match scores, reconcile assessment outcomes,
  and shortlist/reject in bulk or individually; export CSV.
- Analytics for applications, drives, departments, and companies; Market
  Insights from imported job postings; Skill Gaps from student evidence vs
  market demand.

### Admin
- Question bank CRUD, categories, bulk Excel/CSV preview + import, and export.
- Assessment templates, standardized placement-paper generation, and revision.
- Platform analytics and activity summary, LLM/embedding observability and RAG
  knowledge ingest (API-backed), and a cross-drive applications workspace.

### AI / ML
- **Resume parsing:** PyMuPDF → pdfplumber → PaddleOCR fallback, regex section
  parsing, spaCy NER with heuristics, LLM skill extraction with a regex
  fallback.
- **Matching:** bi-encoder retrieval → cross-encoder reranking → Platt
  calibration → hybrid score:
  `0.40·semantic + 0.30·skills + 0.20·experience + 0.10·assessment`.
  The assessment term is `1.0` when no assessment is required or it has not
  been scored yet.
- **LLM/RAG:** grounded narratives for application explanations, JD match
  explanations, student insights, and attempt gap analysis. Deterministic
  fallbacks are returned when the LLM or vector store is unavailable.
- **Code execution:** Python/JavaScript subprocess runner, locally or in an
  isolated judge container. Hidden tests and reference solutions never reach
  the browser.

---

## Prerequisites

- **Python 3.11+** (3.12 is what the project is developed against)
- **Node.js 20+**
- **MongoDB 7** — Docker Compose (recommended) or a local/Atlas instance
- **~1 GB free disk space** for ML model weights
- Optional: Docker Desktop for the full stack and isolated judge
- Optional: an LLM/embedding provider (NVIDIA NIM, OpenRouter, Gemini, or local
  Ollama) for AI narratives. Every AI feature degrades gracefully without one.

## 1. Clone and get the model weights

```bash
git clone <this-repo-url>
cd PLACER
```

The two largest model files (~560 MB combined) are not tracked in git. Download
`bi_encoder_model.safetensors` and `cross_encoder_model.safetensors` from the
repo's **Releases** page and place them as:

```text
backend/app/ml/matching/artifacts/bi_encoder/model.safetensors
backend/app/ml/matching/artifacts/cross_encoder/model.safetensors
```

Keep the exact filename `model.safetensors` in each folder. Config, tokenizer,
and the calibrator are already in the repo.

If the weights are missing, the app still runs: every feature works except AI
match scores, which return `503` instead of crashing. See the artifact READMEs
under `backend/app/ml/matching/artifacts/`.

## 2. Backend setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate

.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m spacy download en_core_web_sm

copy .env.example .env              # macOS/Linux: cp .env.example .env
```

Generate and set a real JWT secret:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Paste the output into `backend/.env` as `JWT_SECRET_KEY=...`. Other defaults are
safe for local development. Common optional settings:

| Variable | Default | Purpose |
|---|---|---|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DB_NAME` | `placer_db` | Database name |
| `OCR_ENABLED` | `true` | PaddleOCR fallback for scanned resumes |
| `CODE_EXECUTION_ENABLED` | `true` | Enable coding-question submissions |
| `CODE_EXECUTION_BACKEND` | `local` | `local` subprocess or `judge` service |
| `LLM_PRIMARY_PROVIDER` | `nvidia_nim` | `nvidia_nim`, `openrouter`, or `ollama` |
| `LLM_PRIMARY_API_KEY` | empty | Required for hosted providers |
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` or OpenAI-compatible `openai` |
| `GOOGLE_CLIENT_ID` | empty | Optional Google Sign-In |

See `backend/.env.example` and `backend/app/core/config.py` for the full list.
Never commit real keys.

### Start MongoDB

```powershell
# Option A — full Docker stack (from the repo root)
docker compose up --build -d

# Option B — local/Atlas
# Set MONGODB_URI in backend/.env and run MongoDB yourself.
```

Compose starts `mongodb`, `backend`, `frontend`, and an internal-only `judge`.
The judge has no published port and is attached only to `judge_net`.

### Create the first admin (one-time)

There is no public admin sign-up by design.

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.create_admin
```

Follow the prompts for name, email, and password.

### Seed the demo dataset (optional, recommended)

The seed creates a complete, verifiable local dataset: 500 questions, 50
students, 14 companies, 18 drives, 25 assessments, 183 submitted attempts,
199 applications, and 7,469 job-market postings.

```powershell
cd backend
.venv\Scripts\python.exe -m scripts.reset_db --yes       # backs up, drops, recreates indexes
.venv\Scripts\python.exe -m scripts.seed.run_all
.venv\Scripts\python.exe -m scripts.seed.run_all --verify-only
```

Seeded logins use the password **`Placer@2026`** by default
(`PLACER_SEED_PASSWORD` overrides it):

| Role | Email |
|---|---|
| Admin | `admin@placer.edu` |
| TPO | `tpo@placer.edu` |
| Students | `student01@placer.edu` … `student50@placer.edu` |

Full dataset details and invariants: [`docs/SEED_DATA.md`](./docs/SEED_DATA.md).

### Run the tests

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q
```

The suite currently collects **331 tests**. It uses `mongomock-motor`, so no
live MongoDB is required. If matching tests fail, check step 1 (model weights);
most of the suite does not need them.

### Start the backend

```powershell
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

- API: `http://localhost:8000/api/v1`
- Swagger UI: `http://localhost:8000/api/docs`
- Health: `http://localhost:8000/api/v1/health` (also `GET /health`)

## 3. Frontend setup (separate terminal)

```powershell
cd frontend
npm install
copy .env.local.example .env.local   # macOS/Linux: cp .env.local.example .env.local
npm run dev
```

App: `http://localhost:3000`. The Next.js rewrite proxies `/api/backend/*` to
`${NEXT_PUBLIC_API_URL}/api/v1/*`, so the browser stays same-origin and the
httpOnly refresh cookie works without CORS in normal use.

Google Sign-In needs a free OAuth **Web application** client ID from
[console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials).
Set the same value as `GOOGLE_CLIENT_ID` (backend `.env`) and
`NEXT_PUBLIC_GOOGLE_CLIENT_ID` (frontend `.env.local`). Add both
`http://localhost` and `http://localhost:3000` under **Authorized JavaScript
origins**, and open the app at `http://localhost:3000` (Google does not accept
`127.0.0.1`). Changes can take a few minutes to propagate. Without a client ID
the Google button is disabled with an explanatory message; password login still
works.

## 4. Try it out

1. **Student** — log in as `student01@placer.edu`, open **Resume**, upload a
   PDF (or use the seeded active resume), review the parsed data and autofill
   suggestion, then browse **Drives** and open a drive to see eligibility,
   match score, matched/missing skills, and apply.
2. **Student** — open **Assessments**, take a practice adaptive paper or a
   drive paper. Coding answers run against visible samples; hidden tests are
   graded by the judge. Finish and open **Results** and **Insights** (the
   per-attempt gap analysis is API-only).
3. **TPO** — log in as `tpo@placer.edu`, open **Drives**, screen applicants,
   shortlist/reject (individually or in bulk), export CSV, then check
   **Analytics**, **Market Insights**, and **Skill Gaps**.
4. **Admin** — log in as `admin@placer.edu`, inspect the **Question bank**,
   create/import questions, generate a standardized placement paper under
   **Assessments**, and use **Applications** for the cross-drive workspace.

## Project layout

```text
PLACER/
├── backend/
│   ├── app/
│   │   ├── core/           # config, database/indexes, security, deps, limiter, request IDs
│   │   ├── models/         # Pydantic schemas and MongoDB document models
│   │   ├── repositories/   # one repository per collection
│   │   ├── routers/        # 16 routers: auth, resumes, students, drives, questions,
│   │   │                   # assessments, analytics, market, matching, applications,
│   │   │                   # gap analysis, insights, observability, knowledge, JD, health
│   │   ├── services/       # business logic and orchestration
│   │   ├── ml/             # parsing/OCR, matching, LLM, RAG, quality
│   │   └── main.py         # app factory, middleware, router registration
│   ├── scripts/            # seed/, create_admin, reset_db, market import, diagnostics
│   ├── tests/              # 331 pytest tests
│   └── storage/            # local resume PDFs (git-ignored)
├── frontend/
│   ├── app/
│   │   ├── (auth)/         # login, register
│   │   ├── (student)/      # dashboard, resume, drives, applications, assessments, insights, profile
│   │   ├── (tpo)/          # overview, drives, analytics, market insights, skill gaps
│   │   └── (admin)/        # overview, question bank, assessments, applications
│   ├── components/         # shared dashboard shell, charts, UI primitives
│   ├── hooks/              # React Query hooks
│   ├── lib/                # API client, token store, departments, helpers
│   └── providers/          # auth and query providers
├── docs/
├── docker-compose.yml
├── PROJECT_PROGRESS.md
└── README.md
```

## Common issues

- **`Invalid email or password` but the credentials are right** — usually a
  stale backend process or the wrong Python install. Always invoke through the
  venv (`.venv\Scripts\python.exe -m uvicorn ...`), and restart the terminal
  after `pip install`.
- **`ECONNREFUSED` / “Failed to proxy” in the frontend terminal** — the backend
  is not running or not reachable at `NEXT_PUBLIC_API_URL` (default
  `http://localhost:8000`).
- **Google button renders but does nothing / `403` on `/gsi/button`** — the
  OAuth client is missing an authorized JavaScript origin. Add both localhost
  origins, wait a few minutes, and retry in a private window.
- **Match endpoints return `503`** — the matching model weights are missing
  (step 1). Narrative/insight endpoints do not fail this way; they fall back to
  deterministic output when the LLM/embedding provider is unconfigured.
- **Coding submissions return `503`** — `CODE_EXECUTION_ENABLED=false`, the
  judge is unreachable, or the judge semaphore is overloaded.
- **`scripts.reset_db` refuses the target** — it only accepts loopback MongoDB
  hosts. To reseed a Compose deployment, run the seed step inside the backend
  container instead: `docker compose exec backend python -m scripts.seed.run_all`.

## Current status and limitations

- All feature phases are implemented; the suite collects 331 tests.
- Deployment is documented but not provisioned live (Vercel/Render/Atlas).
- The local code runner is **not a hardened sandbox**; use the judge service for
  any shared environment.
- Descriptive answers are stored ungraded for manual review. The TPO
  Descriptive Review page has been removed; grading is backend/API-only.
- Anti-cheat events are recorded and the server enforces timers, but fullscreen
  and fingerprint checks are not backend-enforced.
- `notifications` is index-only; no notification UI/read/write path exists.
- LLM/RAG features need provider keys or a running Ollama. Deterministic
  fallbacks are used otherwise.

See `docs/PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md` §16 for the full known-gaps
list and `PROJECT_PROGRESS.md` for the build history.
