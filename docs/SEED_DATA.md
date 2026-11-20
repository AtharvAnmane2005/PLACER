# PLACER local seed data

This document describes the deterministic local dataset created by
`backend/scripts/seed/`. It contains **no credentials**. The operator guide
with the local development logins is written to `credentials.md` at the repo
root, which is git-ignored.

## Safety

* `scripts/reset_db.py` refuses any MongoDB target that is not loopback
  (`localhost`, `127.0.0.1`, `::1`). `mongodb+srv://` and remote hosts are
  rejected before a connection is opened.
* Unless `--no-backup` is passed, every collection is exported to
  `backend/db_backups/pre_reset_<timestamp>/<database>/<collection>.json`
  (MongoDB Extended JSON) before the database is dropped.
* All seeded records carry `data_origin="synthetic"`, `is_synthetic=true` and
  `synthetic_batch="placer-seed-v2"`.

## Commands

From `PLACER/backend` with the project venv:

```powershell
# Drop the local database (backs up first), then recreate indexes
.venv\Scripts\python.exe -m scripts.reset_db --yes

# Build the complete dataset
.venv\Scripts\python.exe -m scripts.seed.run_all

# Read everything back from MongoDB and assert the invariants
.venv\Scripts\python.exe -m scripts.seed.run_all --verify-only

# Restore the deterministic job-market demo dataset (TPO Market Insights)
.venv\Scripts\python.exe -m scripts.seed_job_market
```

Useful flags: `--skip-cohort`, `--no-credentials` (run_all),
`--no-backup` (reset_db, only when a verified backup exists).

## Skill taxonomy

`backend/app/core/skill_taxonomy.py` is the single vocabulary used by resumes,
drives, matching and analytics:

| Metric | Count |
| --- | ---: |
| Canonical skills | 135 |
| Aliases | 235 |
| Domains | 12 |

Domains: Programming Languages (17), Data Structures & Algorithms (8),
Databases & Data (12), Web & Frontend (11), Backend & APIs (13), Mobile
Development (5), Cloud & DevOps (13), Cybersecurity (7), Operating Systems &
Networks (7), Machine Learning & AI (19), Software Engineering (11),
Professional & Business (12).

`normalize_skill`, `canonicalize_skills`, `extract_skills`,
`domain_for_skill`, `domain_for_category` and `taxonomy_snapshot` are the
public helpers. `app/ml/parsing/skill_normalizer.py` is a compatibility
re-export, so existing parser imports keep working.

## Question bank — exactly 500 active questions

| Section | Total | Easy | Medium | Hard | Marks |
| --- | ---: | ---: | ---: | ---: | --- |
| Technical MCQ | 300 | 92 | 134 | 74 | 1 / 3 / 5 |
| Aptitude / Verbal | 120 | 34 | 57 | 29 | 1 / 3 / 5 |
| Coding | 60 | 12 | 26 | 22 | 1 / 3 / 5 |
| Descriptive | 20 | 12 | 8 | 0 | 1 / 3 / 5 |
| **Total** | **500** | **150** | **225** | **125** | |

Types: `mcq=420`, `coding=60`, `descriptive=20`.

Categories (13): Data Structures & Algorithms 89, Aptitude & Logical Reasoning
80, Verbal Ability 40, Python Programming 37, JavaScript & Web Development 37,
DBMS & SQL 34, Machine Learning & AI 32, Software Engineering 30,
Object-Oriented Programming 27, Operating Systems 26, Computer Networks 25,
Cybersecurity 22, Cloud & DevOps 21.

Coding questions are Python or JavaScript and every expected output was
produced by executing the reference solution through the real
`execute_code()` runner. Only the first test case is visible; all others are
hidden. Reference solutions are never stored in MongoDB and are never part of
an admin or student API response.

Descriptive questions have `correct_answer=null` and are stored ungraded. The
TPO **Descriptive Review** page has been removed, so grading is backend/API-only;
`explanation` remains model-answer guidance for reviewers.

## Collections

| Collection | Count |
| --- | ---: |
| users | 52 |
| admins | 1 |
| tpos | 1 |
| students | 50 |
| resumes | 50 |
| companies | 14 |
| placement_drives | 18 |
| question_categories | 13 |
| questions | 500 |
| assessment_templates | 6 |
| assessments | 25 |
| assessment_attempts | 183 |
| applications | 199 |
| knowledge_states | 862 |
| notifications | 171 |
| activity_logs | 257 |
| refresh_tokens | 9 |
| job_market_postings | 7,469 |
| market_skill_catalog | 52 |
| market_import_runs | 4 |

The 7,469 postings are the 300 deterministic demo rows plus 7,169 imported
public postings (RemoteOK 30, Arbeitnow 196, Hacker News “Who is hiring?”
6,943). Counts are from the current local database after the E2E run. The
verifier recomputes the important ones from MongoDB rather than trusting
seeder return values.

## Companies and drives

Fourteen fictional companies, eighteen open drives. Every drive stores its JD
as `jd_text` on the drive document (the existing model), canonical
`required_skills`, eligibility, selection stages, and one linked standardized
assessment.

| Company | Job title | Location |
| --- | --- | --- |
| MedixAI | AI Research Engineer | Bengaluru |
| Skyline Logistics | Backend Engineer - Logistics | Pune |
| Nexus Software Labs | Backend Engineer - Python | Bengaluru |
| TalentBridge Consulting | Business Analyst | Noida |
| CloudForge Systems | Cloud Engineer | Hyderabad |
| Quantiva Analytics | Data Analyst | Pune |
| DataHarbor | Data Engineer | Bengaluru |
| GreenVolt Energy | Data Scientist - Energy | Bengaluru |
| CloudForge Systems | DevOps Engineer | Hyderabad |
| AeroByte Robotics | Embedded Software Engineer | Chennai |
| PixelWorks Studio | Frontend Developer | Remote |
| FinEdge Technologies | Full Stack Developer | Mumbai |
| ByteCraft Games | Gameplay Programmer | Bengaluru |
| FinEdge Technologies | Java Backend Developer | Mumbai |
| Quantiva Analytics | Machine Learning Engineer | Pune |
| SecureLayer | Security Analyst | Gurugram |
| Nexus Software Labs | Software Development Engineer I | Bengaluru |
| InfraGrid | Software Engineer - IoT | Ahmedabad |

## Assessments

* **6 templates**: aptitude, logical reasoning, placement drive mock,
  programming, technical, verbal ability.
* **7 practice papers**: 5 adaptive drills created through the admin
  `POST /assessments` path, plus 2 fixed-set standardized papers — a
  20-question placement mock and a 20-question coding-only paper. Adaptive
  papers store a best-case `total_marks` at creation (the sum of the highest
  marks among their eligible questions), so they no longer show 0 until an
  attempt is graded.
* **18 drive assessments**: one standardized 20-question paper per drive,
  five sections, 6/10/4 difficulty quota, 30-minute timer, 56 marks, pass mark
  28 (50%). Each contains exactly one coding question in the Programming
  section, graded against hidden tests. Drives set
  `assessment_min_score_pct=50` and an assessment deadline.

The selector's coding quota is a preference: if a question bank has no coding
questions, the reserved slot falls back to an objective question instead of
failing generation.

## Student cohort

* `student01@placer.edu` … `student50@placer.edu`.
* One admin: `admin@placer.edu`; one TPO: `tpo@placer.edu`.
* The password is `PLACER_SEED_PASSWORD` (default in `scripts/seed/context.py`
  is a local-development value; override it for any shared environment).
* 50 profiles across 6 departments, CGPA 6.6–9.4, batch years 2026/2027.
* Each student has an active PDF resume, applications, submitted assessment
  attempts, knowledge states and notifications.
* Applications: 143 applied, 20 shortlisted, 36 rejected.

## Verification performed

`scripts.seed.run_all --verify-only` asserts:

* 500 questions, no duplicate text, exact difficulty and type distributions.
* 13 canonical categories, no orphan questions, no empty category.
* Every coding question has at least two test cases, exactly one visible
  sample, no `correct_answer`, and no reference-solution keys.
* Descriptive questions have no `correct_answer`.
* 14 companies / 18 drives, every drive has a JD, required skills and an
  assessment.
* Every drive assessment is standardized, has 20 questions and at least one
  coding question.
* The student-facing projection exposes only visible sample tests and never
  `correct_answer`.
* 50 student logins, 50 active resumes, applications, attempts, knowledge
  states and notifications exist.
* At least one coding answer was graded through the execution runner and at
  least one passed all hidden tests.

## Docker

From `PLACER/`:

```powershell
docker compose build
docker compose up -d
docker compose ps
```

* `mongodb` — MongoDB 7, published on `27017`, data in `./mongodb-data`.
* `backend` — FastAPI on `8000`, `CODE_EXECUTION_BACKEND=judge`.
* `judge` — isolated runner, internal-only `judge_net`, no published port.
* `frontend` — Next.js on `3000`, rewrites `/api/backend/*` to the backend.

The judge container is read-only, writes only to a 64 MB `/tmp` tmpfs, runs as
a non-root user, drops all capabilities, and is limited to 1 CPU, 256 MB and
128 PIDs. It reuses the backend's `code_execution_service.py` with
`CODE_EXECUTION_BACKEND=local`, so there is one grading implementation.

`reset_db.py` intentionally refuses the compose hostname `mongodb` because it
is not loopback. To reseed a compose deployment, run the seed step (not the
reset step) inside the backend container:

```powershell
docker compose exec backend python -m scripts.seed.run_all
```

## Market Insights semantics

* The headline `yoy_posting_growth_pct` compares the latest two **complete**
  calendar years when the newest year is still in progress, and reports that
  basis in `yoy_growth_basis` (currently `Full year 2025 vs 2024 (latest
  complete years)`). A half-finished year is never shown as a decline.
* `sort=trending` ranks by `momentum_pct`, the percentage-point change in a
  skill's demand share versus the previous comparable window. `declining`
  skills are always ordered last, so a high-volume but shrinking skill (for
  example React in this dataset) is not presented as the top trend.
* `summary.most_demanded_skill` is measured over the current comparable period
  (Python, 631 postings, 29.6% of the current real-data window), not all-time
  totals.

## Known limitations

* The job-market set mixes 300 deterministic demo postings with 7,169 imported
  public postings. Re-run `python -m scripts.import_job_market --all` when you
  want a fresh pull; imports are idempotent by source URL.
* Descriptive answers are manual-graded by design. The TPO **Descriptive
  Review** page has been removed; grading is backend/API-only
  (`GET /assessments/review/pending`, `GET /assessments/attempts/{id}/review`,
  `POST /assessments/attempts/{id}/grade`). The student sees the score and
  reviewer feedback on the result page once graded.
* The `custom` template preset is a blank UI starting point with zero sections
  and is intentionally not persisted. Add at least one section before saving.
