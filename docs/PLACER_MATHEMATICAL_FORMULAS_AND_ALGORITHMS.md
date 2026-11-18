# PLACER — Mathematical Formulas and Algorithms

**Document version:** 1.0
**Scope:** every quantitative calculation that is actually implemented in the PLACER backend, plus a clearly-labelled list of calculations that are *not* implemented.
**Companion documents:**

- [`PLACER_SYSTEM_ARCHITECTURE.mmd`](./PLACER_SYSTEM_ARCHITECTURE.mmd) — system architecture, ER model, physical schema, data-flow diagrams, role workflows, AI model flow.
- [`PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md`](./PLACER_SYSTEM_DESIGN_AND_DATA_FLOW.md) — interfaces, API reference, lifecycles, deployment, end-to-end example.

---

## 0. How to read this document

### 0.1 Implementation-status legend

| Marker | Meaning |
|---|---|
| **Implemented** | The formula is executed by shipped backend code on live data. Constants and call sites are given. |
| **Partial** | Part of the pipeline exists; a named sub-part is missing, uncalibrated, or only reachable under a configuration that is not currently wired. |
| **Planned** | Referenced in design intent or dead code but **not** executed. Never presented to users as a real number. |
| **Not implemented** | No code exists. Listed only so readers do not assume a statistic exists. |

### 0.2 Notation

| Symbol | Meaning |
|---|---|
| $N$ | A count of records (applications, postings, answers, students). |
| $x_i$ | The $i$-th observation of a quantity $x$. |
| $\bar{x}$ | Arithmetic mean of $x$. |
| $\lvert S\rvert$ | Cardinality of set $S$. |
| $\mathrm{clamp}(x,a,b)$ | $\min(\max(x,a),b)$. |
| $\mathrm{round}(x,d)$ | Round-half-to-even at $d$ decimal places (Python `round`). |
| $[P]$ | Iverson bracket: 1 when predicate $P$ holds, else 0. |

### 0.3 Rounding and precision policy (global)

| Stage | Rule | Where |
|---|---|---|
| Stored scores | Full float precision, except screening which stores `round(x, 4)` | `screening_service.py` |
| Percentage displays | `round(x, 1)` | `analytics_service.py`, `market_analytics_service.py`, `skill_gap_service.py`, `student_insights_service.py` |
| Trend score | `round(x, 2)` | `market_analytics_service._trend_score` |
| Mastery history | `round(x, 2)` | `knowledge_tracing_service.py` |
| Match explanation | `round(x, 3)` | `jd_explanation_service.py` |

No median, standard deviation, percentile, quantile, z-score or confidence-interval function exists anywhere in the analytics or ML services. All "averages" below are arithmetic means unless stated otherwise.

---

## 1. Application-status analytics

**Source of truth:** `backend/app/services/analytics_service.py`
**Collections:** `applications`, `placement_drives`, `students`, `companies`, `assessments`, `assessment_attempts`
**Models:** `backend/app/models/analytics.py`

The current placement workflow has exactly three managed statuses — `applied`, `shortlisted`, `rejected`. `selected` exists only in the enum for legacy documents. Every analytics read **replaces the stored `selected` value with `shortlisted` in memory**; no document is ever rewritten.

### F-1.1 — Effective status mapping

**Status:** Implemented
**Expression**

$$
s_{\text{eff}}(a)=
\begin{cases}
\text{shortlisted} & \text{if } s(a)=\text{selected}\\
s(a) & \text{otherwise}
\end{cases}
$$

**Variables**

| Symbol | Meaning |
|---|---|
| $s(a)$ | Raw `application.status` string from MongoDB. |
| $s_{\text{eff}}(a)$ | Status used by every breakdown, rate and chart. |

**Worked example.** An application document still holds `"selected"`. $s_{\text{eff}}=\text{shortlisted}$, so it contributes to the green Shortlisted segment and never creates a fourth stage.

**Why used.** The product no longer has a Selected stage. Mapping at read time preserves historical data without destructive migration and guarantees the three displayed statuses reconcile with the total.

**Implementation.** `_LEGACY_STATUS_MAP = {"selected": "shortlisted"}` and `_effective_status(value)` at `analytics_service.py:92-97`.

**Dashboard display.** All status donuts, stacked bars and rate cards for Student, TPO and Admin.

**Storage.** Read-only transformation; `applications.status` is untouched.

**Edge cases.**
- Unknown status strings are counted by no bucket, so they would break reconciliation; the enum makes this unreachable through the API.
- `_tally_tpo` and `_tally` both use the mapping; the audit counter `_legacy_selected_count` deliberately reads the raw value.

### F-1.2 — Status tally and reconciliation invariant

**Status:** Implemented
**Expression**

$$
T=\sum_{a\in A}\Big([s_{\text{eff}}(a)=\text{applied}]+[s_{\text{eff}}(a)=\text{shortlisted}]+[s_{\text{eff}}(a)=\text{rejected}]\Big)
$$

$$
T=\lvert A\rvert
$$

**Variables.** $A$ is the set of applications in the current scope (student, TPO-owned drives, or platform).

**Worked example.** Live platform data: 28 applied, 14 shortlisted, 38 rejected $\Rightarrow T=80$, and there are 80 application documents. Invariant holds.

**Why used.** Prevents a dashboard from showing segments that do not add up to its own headline total.

**Implementation.** `_tally` (`analytics_service.py:100-116`) and `_tally_tpo` (`:128-141`). The admin path uses a database `$group` (`ApplicationRepository.status_counts`) and then adds `selected` into `shortlisted`.

**Dashboard display.** Student dashboard donut, TPO dashboard donut and stacked monthly columns, Admin analytics breakdown.

**Storage.** Not stored; recomputed per request.

**Edge cases.** Legacy `selected` is counted once, in `shortlisted`; it is never double-counted. Admin sets `selected=0` in the response model even though the model still has the field.

### F-1.3 — Rate percentage (zero-safe)

**Status:** Implemented
**Expression**

$$
r_{\text{pct}}(n,d)=
\begin{cases}
\mathrm{round}\!\left(\dfrac{100\,n}{d},1\right) & d>0\\[4pt]
0.0 & d=0
\end{cases}
$$

**Variables.** $n$ = numerator count, $d$ = denominator count.

**Worked example.** 14 shortlisted out of 80 applications: $100\cdot14/80=17.5\%$.

**Why used.** Dashboards must render on an empty account (new student, new TPO) without a divide-by-zero error.

**Implementation.** `_rate_pct` (`analytics_service.py:144-146`). Market analytics has an independent identical helper `_pct` (`market_analytics_service.py:197-198`).

**Dashboard display.** Applied / Shortlisting / Rejection rate cards; drive completion rate.

**Storage.** Not stored.

**Edge cases.** A zero denominator yields `0.0`, which is visually indistinguishable from a genuine 0%. The UI distinguishes "no data" via separate empty-state logic and record counts.

### F-1.4 — Students with applications (distinct count)

**Status:** Implemented
**Expression**

$$
U=\left\lvert\{\,a.\text{student\_id}\;:\;a\in A\,\}\right\rvert
$$

**Variables.** $A$ is the application set in scope.

**Worked example.** 80 platform applications produced by 22 distinct students $\Rightarrow U=22$. The label is **"Students with Applications"**; the legacy field name `unique_applicants` is retained only for API compatibility.

**Why used.** A student who applies to five drives is one applicant, not five.

**Implementation.** `ApplicationRepository.distinct_students()` (`distinct("student_id", {})`), consumed at `analytics_service.py:1518`; TPO variant computes `len(applicant_student_ids)` at `:1042`.

**Dashboard display.** Admin "Platform snapshot"; TPO application analytics summary.

**Storage.** Derived.

**Edge cases.** Counts students who have at least one application in any status, including rejected. It does **not** mean "placed".

### F-1.5 — Monthly application grouping key

**Status:** Implemented
**Expression**

$$
k(t)=\text{YYYY-MM}(t)
$$

**Variables.** $t$ = `application.applied_at` (UTC datetime).

**Worked example.** Every live application has `applied_at` in November 2026, so all 80 map to the single key `2026-11`.

**Why used.** Provides a stable lexicographically sortable bucket for the trend chart.

**Implementation.** `_month_key` (`analytics_service.py:267-269`).

**Dashboard display.** "Monthly Application Trends" grouped/stacked column chart on TPO dashboard.

**Storage.** Derived from `applied_at`.

**Edge cases.** Timestamps are naive UTC by convention (`datetime.utcnow()`); no timezone conversion is applied, so an application at 23:30 UTC on the last day of a month belongs to that UTC month.

### F-1.6 — Month axis: zero-fill and clamping

**Status:** Implemented
**Expression.** For an explicit date range $[d_f,d_t]$:

$$
K=\{\,\text{month}(m)\;:\;m\in[d_f,d_t]\text{ stepped monthly}\,\}
$$

For no range but at least one application:

$$
K=\{\,\text{month}(m)\;:\;m\in[\min_a k(a),\ \max_a k(a)]\text{ stepped monthly}\,\},\qquad \lvert K\rvert\le 24
$$

**Variables.** $K$ is the ordered list of month keys rendered on the x-axis; `_MAX_TREND_MONTHS = 24`.

**Worked example.** With no filter and all applications in `2026-11`, $K=[\texttt{2026-11}]$ — one column, not twelve invented months.

**Why used.** A trend line should show real empty months inside a real range (so a gap is visible), but must not fabricate a year of zeros around a single month.

**Implementation.** `_month_keys` (`:303-318`), `_clamped_month_keys` (`:320-329`), `_add_months` (`:298-301`). Explicit ranges are validated (`date_from <= date_to`, else HTTP 400).

**Dashboard display.** Monthly trend chart plus the "limited range" note when the axis has one month.

**Storage.** Derived.

**Edge cases.** A 25-month explicit range is clamped to the most recent 24 keys; the API still reports the requested `date_from`/`date_to` in metadata.

### F-1.7 — Department grouping and canonicalisation

**Status:** Implemented
**Expression**

$$
G_{\text{dept}}(d)=\{\,a\in A\;:\;\text{norm}(student(a).\text{department})=d\,\}
$$

**Variables.** `norm` is `core/departments.normalize_department`, which maps aliases (for example `CS`) to one of ten canonical labels and preserves unknown free text.

**Worked example.** Live data after canonicalisation: Computer Science 12, Information Technology 7, Electronics and Communication 3, Electrical Engineering 3, Mathematics and Computing 2, Statistics 1, unset 1.

**Why used.** `"CS"` and `"Computer Science"` must not appear as two departments in the same chart.

**Implementation.** `_normalize_department` import, used at `analytics_service.py:862`, `:1295`, `:1562`. Canonical list in `backend/app/core/departments.py`; mirrored exactly in `frontend/lib/departments.ts`.

**Dashboard display.** TPO department breakdown table; Admin department distribution chart.

**Storage.** Normalised on read; profile writes also normalise (Phase 0). The stored raw value is not destroyed.

**Edge cases.** Blank department becomes one explicit "Not specified" bucket. Unknown text is preserved rather than silently forced into "Other".

### F-1.8 — Company / drive aggregation ordering

**Status:** Implemented
**Expression.** For company rows sorted by applications:

$$
\text{key}(c)=(-c_{\text{total}},\,-c_{\text{shortlisted}},\,\text{lower}(c_{\text{name}}))
$$

**Variables.** $c_{\text{total}}$ = applications to that company, $c_{\text{shortlisted}}$ = its shortlisted count.

**Worked example.** Company A 20 total/5 shortlisted, Company B 20/7, Company C 12/2 $\Rightarrow$ order B, A, C.

**Why used.** Deterministic ordering; ties never flip between requests.

**Implementation.** `analytics_service.py:964-973` (`applications`, `shortlisted`, `name` modes); drive rows at `:1009`; departments at `:879-883`.

**Dashboard display.** Top-N company bar chart, per-drive comparison table.

**Storage.** Derived.

**Edge cases.** `top_n` slices only the company list; `company_count` reports the untruncated number of distinct companies so the UI can say "showing 8 of 12".

### F-1.9 — Drive assessment completion rate

**Status:** Implemented
**Expression**

$$
\text{completion}_{\text{pct}}(d)=\frac{\left\lvert\{\,\text{student}\in \text{applicants}(d)\;:\;\exists\,\text{attempt submitted on }d.\text{required\_assessment}\,\}\right\rvert}{\left\lvert\{\,a\in A_d\;:\;a.\text{eligibility\_passed}\ne\text{false}\,\}\right\rvert}\times 100
$$

**Variables.** Numerator is distinct applicants with a **submitted** attempt on the drive's required assessment. Denominator is applications not explicitly marked ineligible (so "never screened" counts as eligible).

**Worked example.** 18 applicants, 16 eligible (not false), 9 submitted participants $\Rightarrow 56.25\%\rightarrow56.3\%$.

**Why used.** Measures assessment participation, not placement.

**Implementation.** `get_tpo_analytics` (`analytics_service.py:491-529`), `_rate_pct`.

**Dashboard display.** TPO dashboard drive funnel and completion progress bar.

**Storage.** Derived.

**Edge cases.** A drive with no `required_assessment_id` reports `participant_count=0` and `completion_rate_pct=0.0`. In-progress attempts are excluded from `submitted_participant_count`.

### F-1.10 — Admin average assessment score (database pipeline)

**Status:** Implemented
**Expression.** For each submitted attempt $i$ with at least one answer:

$$
m_i=\sum_{j\in \text{answers}(i)} w\big(d_{ij}\big),\qquad
s_i=\sum_{j\in\text{answers}(i)} \text{marks}_{ij}
$$

$$
\bar{s}=\frac{1}{\lvert\{i:m_i>0\}\rvert}\sum_{i:m_i>0} 100\cdot\frac{s_i}{m_i}
$$

with $w(\text{easy})=1$, $w(\text{medium})=3$, $w(\text{hard})=5$ (`DIFFICULTY_MARKS`).

**Variables.** $d_{ij}$ = `difficulty_at_time` of answer $j$; `marks_awarded` may be fractional (negative marking) or zero.

**Worked example.** Two attempts: 9/12 = 75%, 6/12 = 50% $\Rightarrow \bar{s}=62.5\%$.

**Why used.** Computed in MongoDB so a fetch cap cannot silently turn a true mean into a sample mean.

**Implementation.** `AttemptRepository.submitted_score_stats` (aggregation: `$match status=submitted`, `$unwind answers`, `$group` per attempt, `$match maximum>0`, `$group` overall `$avg`), consumed at `analytics_service.py:1527-1537`.

**Dashboard display.** Admin dashboard "Average assessment score" stat card (renders an em-dash when `None`).

**Storage.** Derived.

**Edge cases.** Submitted attempts with zero answers are counted in `submitted_attempts` but excluded from the average (`maximum = 0`). If no scored attempt exists the API returns `average_score_pct = null`, never `0.0`.

### F-1.11 — Admin average skill mastery

**Status:** Implemented
**Expression**

$$
\overline{M}_{\text{skill}}=\frac{1}{\lvert S_{\text{skill}}\rvert}\sum_{s\in S_{\text{skill}}} M_{s,\text{skill}}
$$

**Variables.** $M_{s,\text{skill}}$ = `knowledge_states.mastery_pct` for one student/skill pair.

**Worked example.** Three students at 40, 55 and 70 $\Rightarrow 55.0\%$.

**Why used.** Shows cohort-level mastery without pulling every document into Python.

**Implementation.** `KnowledgeStateRepository.mastery_overview` (`$group` by `skill_tag`, `$avg`), sorted at `analytics_service.py:1539-1549`.

**Dashboard display.** Admin dashboard skill mastery list.

**Storage.** Derived from `knowledge_states`.

**Edge cases.** Skills with no knowledge state do not appear at all (no invented zero rows). Student count is the number of state documents, which is one per student/skill by unique index.

### F-1.12 — Legacy audit counters

**Status:** Implemented (internal only)
**Expression**

$$
L=\sum_{a\in A}[s(a)=\text{selected}],\qquad
L_{\text{admin}}=\text{status\_counts}[\text{selected}]
$$

**Worked example.** Live database contains 0 `selected` rows, so $L=0$ while Shortlisted still shows 14.

**Why used.** Gives auditors a way to confirm that no historical row was deleted, without exposing a "Selected" stage to users.

**Implementation.** `_legacy_selected_count` (`analytics_service.py:119-121`); admin at `:1510`.

**Dashboard display.** Not displayed. Returned as `legacy_selected` in analytics payloads for diagnostics.

**Storage.** Derived from raw `applications.status`.

**Edge cases.** Because the mapping is read-time, $L$ can be non-zero while `selected` is 0 in the response breakdown.

---

## 2. Assessment grading and scoring

**Source of truth:** `backend/app/services/assessment_service.py`
**Collections:** `questions`, `assessments`, `assessment_attempts`, `applications`, `placement_drives`
**Models:** `backend/app/models/assessment.py`

### F-2.1 — Question grading predicates

**Status:** Implemented
**Expression**

$$
g(q,r)=
\begin{cases}
[\,\mathrm{strip}(r)=\mathrm{strip}(c)\,] & q.\text{type}=\text{mcq}\\[2pt]
[\,\mathrm{lower}(\mathrm{strip}(r))=\mathrm{lower}(\mathrm{strip}(c))\,] & q.\text{type}=\text{true\_false}\\[2pt]
[\,E\neq\varnothing \wedge E=G\,] & q.\text{type}=\text{multiple\_select}\\
\text{None} & q.\text{type}\in\{\text{coding},\text{descriptive}\}
\end{cases}
$$

where

$$
E=\{\mathrm{strip}(p):p\in \mathrm{split}(c,\texttt{"|"}),\ p\ne\varnothing\},\qquad
G=\{\mathrm{strip}(p):p\in \mathrm{split}(r,\texttt{"|"}),\ p\ne\varnothing\}
$$

**Variables.** $r$ = student response, $c$ = `question.correct_answer`, $q.\text{type}$ = question type.

**Worked example.** Multiple-select answer stored as `"Index|Hash"`; student sends `"Hash|Index"`. $E=G$ as sets $\Rightarrow$ correct despite different order.

**Why used.** Order-independent multi-select grading; whitespace/case tolerance where the question type permits it.

**Implementation.** `_grade` (`assessment_service.py:98-110`).

**Storage.** Result persisted as `assessment_attempts.answers[].is_correct` (`bool | null`).

**Edge cases.**
- Multiple-select with an empty correct set is always wrong (`bool(expected)` guard).
- Coding returns `None` from `_grade` and is graded by executing test cases.
- Descriptive always returns `None` and never affects the numeric score.

### F-2.2 — Marks awarded and negative marking

**Status:** Implemented
**Expression**

$$
\text{marks}(q,g)=
\begin{cases}
q.\text{marks} & g=\text{True}\\
0 & g=\text{False}\ \wedge\ \text{not standardized}\\
-\lvert \text{assessment.negative\_marks}\rvert & g=\text{False}\ \wedge\ \text{standardized}\\
0 & g=\text{None}
\end{cases}
$$

**Variables.** $q.\text{marks}$ is an integer; it defaults to the difficulty mark when an admin does not override it (`question_service.py`). `negative_marks` is a non-negative configured value.

**Worked example.** Standardized assessment, `negative_marks = 0.25`. A wrong medium question awards $-0.25$, not $-3$ and not $-0.75$. Negative marking is a **flat penalty per wrong question**, independent of the question's marks.

**Why used.** Explicit, auditable penalty rule; fractional penalties require float storage (`marks_awarded: float`).

**Implementation.** `assessment_service.py:482-486`.

**Storage.** `answers[].marks_awarded` (float).

**Edge cases.**
- Negative marking applies only to auto-graded wrong answers (`is_correct is False`). Ungraded descriptive answers award 0.
- Coding questions are all-or-nothing: `is_correct = code_result.all_passed`; partial test-case passes award 0 and, on a standardized assessment, incur the flat penalty.
- Because the maximum is computed from `DIFFICULTY_MARKS` while the award uses `q.marks`, an admin who sets custom marks above the difficulty mark can produce a score above 100% on an adaptive attempt.

### F-2.3 — Attempt score percentage (answered-only)

**Status:** Implemented
**Expression**

$$
\text{score}_{\text{attempt}}(i)=\mathrm{round}\!\left(100\cdot\frac{\sum_{j\in\text{answers}(i)}\text{marks}_{ij}}{\sum_{j\in\text{answers}(i)}w(d_{ij})},\,1\right)
$$

with the convention $0/0\mapsto 0.0$.

**Variables.** Denominator counts **only answered questions**, using the difficulty at the time each answer was recorded.

**Worked example.** Answers: easy correct (1/1), medium wrong (0/3), hard correct (5/5), medium correct (3/3) $\Rightarrow 9/12=75.0\%$.

**Why used.** Adaptive attempts have no fixed paper; the difficulty-weighted maximum of what the student actually faced is the only honest denominator.

**Implementation.** `_attempt_score_pct` (`analytics_service.py:149-155`); identical logic inside `_finalize_attempt` (`assessment_service.py:401-406`).

**Dashboard display.** Attempt results page, student trend line, drive ranking.

**Storage.** Persisted indirectly as `applications.assessment_score_pct` when an attempt is linked to an application; the attempt itself stores raw answers, not the percentage.

**Edge cases.**
- A submitted attempt with zero answers scores 0.0 and is excluded from the student trend and domain radar (it is not evidence).
- `_graded_attempt_score_pct` (used by the trend/radar) additionally excludes `is_correct is None`, so ungraded descriptive answers do not inflate the denominator.

### F-2.4 — Standardized assessment final score (clamped)

**Status:** Implemented
**Expression**

For a standardized assessment (see F-2.5):

$$
M=\text{assessment.total\_marks}\ \text{(or the answered maximum if }0\text{)},\qquad
S=\mathrm{clamp}\!\left(\sum_j \text{marks}_{ij},\,0,\,M\right)
$$

$$
\text{score}_{\text{final}}(i)=\mathrm{round}\!\left(100\cdot\frac{S}{M},\,1\right)
$$

**Variables.** $M$ = configured paper maximum; $S$ = earned marks after negative marking, clamped to $[0,M]$.

**Worked example.** 20-question paper, `total_marks = 56`. Earned $40$ with three wrong at $-0.25$: $S=40-0.75=39.25$; $\text{score}=100\cdot39.25/56=70.089\ldots\rightarrow70.1\%$. With a catastrophic $-20$ penalty, $S$ would clamp to 0 rather than go negative.

**Why used.** A standardized paper has a fixed maximum, so percentage must not depend on how many questions the student happened to answer. Clamping prevents a negative percentage from appearing on a results page.

**Implementation.** `_finalize_attempt` (`assessment_service.py:398-406`).

**Storage.** `applications.assessment_score_pct` (one decimal).

**Edge cases.** If `assessment.total_marks` is 0 (malformed legacy record), the answered maximum is used as a fallback, which reverts to the adaptive behaviour for that paper.

### F-2.5 — Standardized-assessment predicate

**Status:** Implemented
**Expression**

$$
\text{standardized}(A)=[A.\text{format}=\text{standardized}]\ \wedge\ [\,A.\text{question\_ids}\ne\varnothing\,]
$$

**Variables.** Both conditions are required. `format` alone is not enough.

**Worked example.** A template saved with `format="standardized"` but an empty `question_ids` list is treated as adaptive: no fixed question set, no standardized clamping.

**Why used.** Guards against half-generated papers being graded under standardized rules.

**Implementation.** `_is_standardized` (`assessment_service.py:140-142`).

**Storage.** Read from `assessments.format` and `assessments.question_ids`.

**Edge cases.** The placement generator always writes a 20-ID list, so genuine placement assessments always satisfy the predicate.

### F-2.6 — Pass / fail determination

**Status:** Implemented
**Expression**

$$
\text{result}=
\begin{cases}
\text{failed} & D.\text{assessment\_min\_score\_pct}\ne\text{null}\ \wedge\ \text{score}_{\text{final}}<D.\text{assessment\_min\_score\_pct}\\
\text{failed} & \text{no drive threshold}\ \wedge\ \text{standardized}\ \wedge\ A.\text{passing\_marks}>0\ \wedge\ S<A.\text{passing\_marks}\\
\text{passed} & \text{otherwise}
\end{cases}
$$

**Variables.** $D$ = the linked drive; $S$ = earned marks from F-2.4.

**Worked example.** Drive threshold 70%, score 70.1% $\Rightarrow$ passed. Same score with drive threshold 75% $\Rightarrow$ failed, even if the paper's own `passing_marks` is lower.

**Why used.** A company's cut-off (drive threshold) must override the generic paper pass mark. Percentage is compared for drive thresholds; raw marks are compared for the paper's own `passing_marks`.

**Implementation.** `_finalize_attempt` (`assessment_service.py:416-432`).

**Storage.** `applications.assessment_status` ∈ {`passed`, `failed`}; the score is stored alongside.

**Edge cases.**
- Only applications already linked through `assessment_attempt_id` are updated.
- A practice assessment is never linked to an application, so it never sets a pass/fail status.
- If an attempt is linked to several applications, all are updated (fetch limit 100).

### F-2.7 — Adaptive difficulty transition

**Status:** Implemented
**Expression**

$$
d_{t+1}=
\begin{cases}
\min\!\big(\text{index}(d_t)+1,\ 2\big) & g_t=\text{True}\\
\max\!\big(\text{index}(d_t)-1,\ 0\big) & g_t=\text{False}\\
d_t & g_t=\text{None}
\end{cases}
$$

with the ordered index set $\{\text{easy}=0,\text{medium}=1,\text{hard}=2\}$.

**Worked example.** Start medium (1). Correct $\rightarrow$ hard (2). Wrong next $\rightarrow$ medium (1). Wrong again $\rightarrow$ easy (0). Wrong again stays easy.

**Why used.** A simple staircase that adapts without requiring calibrated item-response parameters.

**Implementation.** `_adjust_difficulty` (`assessment_service.py:113-119`), `DIFFICULTY_ORDER` (`models/assessment.py:37`).

**Storage.** `assessment_attempts.current_difficulty` and `answers[].difficulty_at_time`.

**Edge cases.** Only adaptive assessments move; standardized assessments present a fixed ordered set and accept answers in any order.

### F-2.8 — Violation auto-submit threshold

**Status:** Implemented
**Expression**

$$
\text{auto\_submit}=[\,\lvert V\rvert\ge A.\text{anti\_cheat\_config.max\_violations}\,]
$$

Default `max_violations = 3`.

**Worked example.** Third reported violation sets `auto_submitted=true`, finalises the attempt, and returns the updated status.

**Why used.** Bounded anti-cheat response that is visible to the student.

**Implementation.** `report_violation` (`assessment_service.py:631` onward).

**Storage.** `assessment_attempts.violations[]`, `status`, `submitted_at`.

**Edge cases.** The violation `type` is free-form; the backend counts every report. `fingerprint_hash` and `ip_address` are stored but never compared, and fullscreen is a client-side control, not a backend enforcement.

### F-2.9 — Placement paper composition

**Status:** Implemented
**Constants**

$$
\text{sections}=5,\qquad \text{questions per section}=4,\qquad \text{total}=20
$$

$$
\text{quota}=(\text{easy}=6,\ \text{medium}=10,\ \text{hard}=4)
$$

**Worked example.** Default paper marks $=6\cdot1+10\cdot3+4\cdot5=56$.

**Why used.** A fixed, auditable standardized paper shape.

**Implementation.** `PLACEMENT_SECTIONS`, `PLACEMENT_SECTION_SIZE`, `PLACEMENT_TOTAL_QUESTIONS`, `PLACEMENT_DIFFICULTY_QUOTA` (`models/assessment.py:69-81`); generation in `placement_assessment_service.generate` (`:228-336`).

**Storage.** `assessments.sections[]` (each with `question_ids`), `assessments.question_ids`, `assessments.total_marks`.

**Edge cases.** Generation fails with a structured deficit list if the bank cannot fill every section/difficulty slot; it never pads with duplicates or invents questions.

### F-2.10 — Difficulty-slot allocation across sections

**Status:** Implemented
**Algorithm (round-robin)**

1. Build a flat slot list: 6 easy, 10 medium, 4 hard (pad with medium if the quota is short).
2. Truncate to $\sum_i \text{size}_i$.
3. Deal slots cyclically into sections that still have capacity.

**Worked example.** Five sections of 4, quota 6/10/4:

| Section | Slots |
|---|---|
| 1 | E, E, M, M |
| 2 | E, M, M, H |
| 3 | E, M, M, H |
| 4 | E, M, M, H |
| 5 | E, M, M, H |

Totals: 6 E, 10 M, 4 H — exactly the quota, with every section at 4 questions.

**Why used.** Guarantees both the global quota and the per-section size without randomness.

**Implementation.** `allocate_difficulty_slots` (`assessment_selection_service.py:32-61`).

**Storage.** Consumed by `QuestionSelector.select`; the resulting IDs are written into `assessments.sections`.

**Edge cases.** If a section cannot be filled for a difficulty, a precise deficit string is produced (`"<section> / <difficulty>: need N eligible question(s), found M."`). Question selection is deterministic: candidates are sorted by `(created_at, id)` and the oldest fresh questions are taken.

---

## 3. Mastery / knowledge tracing

**Source of truth:** `backend/app/services/knowledge_tracing_service.py`
**Collection:** `knowledge_states`
**Model:** `KnowledgeStateInDB`

> **Important:** this is an exponential-moving-average heuristic, **not** Bayesian Knowledge Tracing. The module docstring says so explicitly. No $P(\text{learn})$, $P(\text{guess})$ or $P(\text{slip})$ parameters are fitted or used.

### F-3.1 — EMA mastery update

**Status:** Implemented
**Expression**

$$
M_{t+1}=\mathrm{clamp}\!\Big(M_t+\eta\,w(d)\big(T-M_t\big),\,0,\,100\Big)
$$

where

$$
T=\begin{cases}100 & g_t=\text{True}\\0 & g_t=\text{False}\end{cases},\qquad
\eta=0.25,\qquad
w(\text{easy})=0.7,\ w(\text{medium})=1.0,\ w(\text{hard})=1.3
$$

**Variables**

| Symbol | Meaning |
|---|---|
| $M_t$ | Current `mastery_pct`; **50.0** when no state exists ("neutral start, not zero"). |
| $\eta$ | `LEARNING_RATE = 0.25`. |
| $w(d)$ | `DIFFICULTY_WEIGHT[difficulty]`. |
| $T$ | Target mastery for the observed outcome. |
| $g_t$ | Graded outcome (`True`/`False`); ungraded answers are not passed to the tracer. |

**Worked example.** New skill, hard question answered correctly:
$M_1=50+0.25\cdot1.3\cdot(100-50)=50+16.25=66.25$.
Next, easy question answered wrong:
$M_2=66.25+0.25\cdot0.7\cdot(0-66.25)=66.25-11.59375=54.65625\rightarrow54.66$ (stored to 2 dp in history).

**Why used.** Transparent, monotone, bounded, and explainable to a student. A wrong hard question moves mastery less than a wrong easy question ($w=1.3$ vs $0.7$ on the negative delta), reflecting that a hard miss is weaker evidence of low mastery.

**Implementation.** `KnowledgeTracingService.update_mastery` (`knowledge_tracing_service.py:34-75`), constants at `:20-27`.

**Dashboard display.** Student insights severity and focus areas, admin skill-mastery overview, TPO skill-gap classification (as an input to evidence classes).

**Storage.** `knowledge_states.mastery_pct` (float, 0–100), `confidence`, `attempts_count`, `history[]` capped at the last 50 entries.

**Edge cases.**
- A brand-new state starts at 50, so the first correct answer cannot jump to 100.
- `history` is truncated with `[-50:]`; older points are discarded, not aggregated.
- Practice assessments update mastery too (the tracer does not distinguish practice from drive assessments); student *insight trends* deliberately exclude practice (see F-5.4).

### F-3.2 — Confidence

**Status:** Implemented
**Expression**

$$
C_{t}=\min\!\left(1,\ \frac{n_t}{10}\right)
$$

**Variables.** $n_t$ = cumulative attempts on that skill after the update.

**Worked example.** After 1 attempt $C=0.1$; after 5 $C=0.5$; after 10 or more $C=1.0$.

**Why used.** Communicates how much evidence supports a mastery estimate without pretending it is a statistical confidence interval.

**Implementation.** `knowledge_tracing_service.py:47`.

**Storage.** `knowledge_states.confidence`.

**Edge cases.** It is a saturating counter, not a variance-based measure; it never decreases.

### F-3.3 — Weak / strong classification

**Status:** Implemented
**Expression**

$$
\text{weak}(s)=[M_s<50],\qquad \text{strong}(s)=[M_s\ge75]
$$

**Worked example.** $M=49.9$ is weak; $M=50.0$ is neither weak nor strong; $M=75.0$ is strong.

**Why used.** Shared thresholds keep the tracer, insights and skill-gap views consistent.

**Implementation.** `WEAK_THRESHOLD = 50.0`, `STRONG_THRESHOLD = 75.0`; `get_weak_and_strong_topics` (`:77-83`).

**Storage.** Derived.

**Edge cases.** A skill can be neither weak nor strong (the 50–75 band).

### F-3.4 — Average mastery (per student)

**Status:** Implemented
**Expression**

$$
\overline{M}=\frac{1}{\lvert S\rvert}\sum_{s\in S}M_s,\qquad S=\text{skills with a knowledge state}
$$

**Worked example.** Skills at 56.9, 50.0, 57.4, 52.8, 63.0 $\Rightarrow \overline{M}=56.02\rightarrow56.0\%$ (the live dashboard shows 56.9 for a different set of five domain aggregates — see F-4.2).

**Why used.** One headline readiness input that is a real mean of tracked skills.

**Implementation.** `get_average_mastery` (`:85-97`); student insights computes `round(sum/len, 1)` at `student_insights_service.py`.

**Storage.** Derived.

**Edge cases.** Returns `None` when the student has no states; the API surfaces `average_mastery_pct: null`, not 0.

---

## 4. Assessment ranking and domain radar

**Source of truth:** `backend/app/services/analytics_service.py`
**Endpoints:** `GET /api/v1/analytics/tpo/drives/{drive_id}/ranking`, `GET /api/v1/analytics/tpo/drives/{drive_id}/applicants`, `GET /api/v1/analytics/tpo/drives/{drive_id}/participants`

### F-4.1 — Best attempt per student, then rank

**Status:** Implemented
**Expression**

$$
b(s)=\max_{i\in \text{submitted}(s)} \text{score}_{\text{attempt}}(i)
$$

$$
\text{rank}(s_1)<\text{rank}(s_2)\iff
\big(-b(s_1),\ t(s_1),\ s_1\big)<_{\text{lex}}\big(-b(s_2),\ t(s_2),\ s_2\big)
$$

where $t(s)$ is the submission time of the attempt that achieved $b(s)$ (falling back to `started_at`).

**Variables.** `submitted(s)` = submitted attempts by student $s$ on the drive's required assessment, restricted to the drive's applicant pool.

**Worked example.** Student A scores 80 then 90 (retake) $\Rightarrow b=90$. Student B scores 90 but submitted later $\Rightarrow$ A ranks above B on the time tie-break; if both also tie on time, the smaller student id wins.

**Why used.** A retake must not penalise a student, and the order must be stable across requests.

**Implementation.** `get_drive_ranking` (`analytics_service.py:1236-1310`); `_drive_attempt_pool` (`:1216-1234`).

**Dashboard display.** TPO drive applicants page "Assessment ranking" table; also exposed to admin through the same endpoint (`require_role("admin","tpo")`).

**Storage.** Derived from `assessment_attempts`; nothing is persisted by the ranking call.

**Edge cases.**
- In-progress attempts are excluded (no final score).
- The denominator is answered-only (`_attempt_score_pct`), so a student who answered one hard question correctly can outrank a student who answered twenty questions at 70%. The **results page** uses a different denominator (clamped total marks) — this is a documented divergence, not a bug in either formula.
- A student with no submitted attempt is absent from the ranking (no zero-score row is invented).

### F-4.2 — Domain score (radar axis)

**Status:** Implemented
**Expression**

$$
\text{domain\_score}(D)=\mathrm{round}\!\left(100\cdot\frac{\sum_{j\in A_D}\text{marks}_j}{\sum_{j\in A_D}w(d_j)},\,1\right)
$$

with $0$ when the denominator is 0. $A_D$ is the set of **graded** answers attributed to domain $D$.

**Variables.** $D$ ranges over the five canonical placement sections:

1. Quantitative Aptitude
2. Logical Reasoning
3. Verbal Ability
4. Technical Knowledge
5. Programming / Problem Solving

**Worked example.** Quantitative Aptitude: awarded 9 over a maximum of 12 $\Rightarrow 75.0\%$; answered 4, correct 3. Live student radar: 56.9 / 50.0 / 57.4 / 52.8 / 63.0.

**Why used.** Gives a per-competency profile instead of one opaque total, and is the only radar data source (no fabricated categories).

**Implementation.** `get_student_analytics` (`analytics_service.py:711-768`); TPO aggregate `_domain_scores_for_attempts` (`:544-642`).

**Dashboard display.** Student dashboard radar chart; TPO analytics radar (aggregate across the filtered drives/applicants).

**Storage.** Derived from `assessment_attempts.answers`, `questions`, `question_categories`, `assessments.sections`.

**Edge cases.**
- Only **submitted** attempts with at least one graded answer contribute.
- A domain with no evidence still appears with `score_pct = 0.0`, `answered = 0` in the student series; the TPO series returns `[]` when there is no evidence at all so the UI can show an explicit empty state.
- Ungraded descriptive answers are excluded, so they cannot depress a domain score.

### F-4.3 — Domain attribution precedence

**Status:** Implemented
**Algorithm**

1. If the assessment's own `sections[]` metadata names the question's section and that name is one of the five canonical sections, use it. This is authoritative.
2. Otherwise, if the question still exists, build a lowercase haystack from its category name, `skill_tags`, `skill`, `topic`, and question type, and match against a keyword table.
3. If the question type is `coding`, attribute to "Programming / Problem Solving".
4. Otherwise attribute to "Technical Knowledge".
5. If the question no longer exists and no section metadata names it, return `None` (cannot be attributed honestly).

**Worked example.** A legacy MCQ tagged `"quantitative aptitude"` lands in Quantitative Aptitude via keywords. A deleted question with no section metadata is skipped, not guessed.

**Why used.** New standardized papers carry explicit section metadata; legacy attempts still need a defensible mapping.

**Implementation.** `_section_domain_map` (`:358-374`), `_domain_for_question` (`:377-411`), `_DOMAIN_KEYWORDS`.

**Storage.** Read-only.

**Edge cases.** An unrecognised custom section name falls through to the legacy heuristics rather than inventing a sixth radar axis.

### F-4.4 — Student assessment trend point

**Status:** Implemented
**Expression**

For each submitted attempt with at least one graded answer:

$$
\text{point}_i=\Big(t_i,\ \text{score}_{\text{graded}}(i),\ \text{correct}_i,\ \text{answered}_i\Big)
$$

$$
\text{score}_{\text{graded}}(i)=\mathrm{round}\!\left(100\cdot\frac{\sum_{j\in G_i}\text{marks}_j}{\sum_{j\in G_i}w(d_j)},\,1\right)
$$

where $G_i=\{\text{answers with }is\_correct\ne\text{None}\}$.

**Worked example.** A 10-answer attempt with 7 graded answers at 5/9 marks $\Rightarrow 55.6\%$; the three ungraded descriptive answers are not counted.

**Why used.** The trend must measure graded performance only; otherwise a paper with descriptive questions would show a fake drop.

**Implementation.** `_graded_attempt_score_pct` (`:337-349`), trend assembly at `:717-754`; sorted by `(submitted_at, attempt_id)`.

**Dashboard display.** Student dashboard "Assessment trend" line chart and `average_score_pct` card.

**Storage.** Derived.

**Edge cases.** A submitted attempt with zero graded answers is excluded from the trend and from `submitted_attempt_count` (which counts trend points, not raw attempts).

### F-4.5 — Student average assessment score

**Status:** Implemented
**Expression**

$$
\overline{\text{score}}=\mathrm{round}\!\left(\frac{1}{\lvert P\rvert}\sum_{p\in P}p.\text{score\_pct},\,1\right)
$$

**Worked example.** Trend points 50.0 and 61.8 $\Rightarrow 55.9\%$ (matches the live student card).

**Why used.** A single headline number consistent with the visible trend points.

**Implementation.** `analytics_service.py:770-774`.

**Storage.** Derived.

**Edge cases.** Returns `null` when the student has no graded submitted attempt.

---

## 5. Skill-gap analysis

**Source of truth:** `backend/app/services/skill_gap_service.py`
**Collections:** `job_market_postings`, `market_skill_catalog`, `knowledge_states`, `questions`, `assessment_attempts`, `resumes`
**Endpoints:** `GET /api/v1/analytics/tpo/skill-gaps`, `/skill-gaps/filters`, `/skill-gaps/{skill_id}/students`

### F-5.1 — Industry demand percentage

**Status:** Implemented
**Expression**

$$
\text{demand}(k)=\mathrm{round}\!\left(100\cdot\frac{n_k}{N_{\text{postings}}},\,1\right)
$$

**Variables.** $n_k$ = postings in the filtered population that require skill $k$; $N_{\text{postings}}$ = all postings in that population.

**Worked example.** 65 of 200 postings require Docker $\Rightarrow 32.5\%$.

**Why used.** Normalises across filters and years so a skill's share is comparable.

**Implementation.** `_build_entry` (`skill_gap_service.py:665`); `_pct` imported from `market_analytics_service`.

**Dashboard display.** TPO skill-gaps demand column, demand-vs-proficiency scatter.

**Storage.** Derived from the market dataset.

**Edge cases.** Zero postings yields 0.0, not an error; the endpoint returns an empty analysis instead.

### F-5.2 — Student gap percentage

**Status:** Implemented
**Expression**

$$
\text{gap}(k)=\mathrm{round}\!\left(100\cdot\frac{P-D_k}{P},\,1\right),\qquad
D_k=\lvert\{\text{students classified \emph{demonstrated} on }k\}\rvert
$$

**Variables.** $P$ = student population size; $D_k$ = students with at least `MIN_GRADED_ANSWERS = 3` graded answers and accuracy $\ge 75\%$ on that skill.

**Worked example.** $P=29$, $D_k=12$ $\Rightarrow (29-12)/29=58.62\%\rightarrow58.6\%$.

**Why used.** "Lacking demonstrated competence" is a defensible, evidence-based gap; it does not claim a student cannot do the skill.

**Implementation.** `skill_gap_service.py:662-666`.

**Storage.** Derived.

**Edge cases.** Self-reported skills do **not** count as demonstrated. Students with 1–2 answers are classified `insufficient` and counted as lacking (conservative).

### F-5.3 — Year-over-year growth

**Status:** Implemented
**Expression**

$$
\text{growth}(k)=\mathrm{round}\!\left(100\cdot\frac{c_{\text{current}}-c_{\text{previous}}}{c_{\text{previous}}},\,1\right)
$$

with `None` when $c_{\text{previous}}=0$.

**Variables.** Counts are restricted to a **comparable window** (the same calendar months in both years, capped by coverage). See F-6.3.

**Worked example.** Current window 60, previous window 50 $\Rightarrow 20.0\%$.

**Why used.** Raw full-year-vs-partial-year comparison would manufacture a decline purely from calendar coverage.

**Implementation.** `_growth_pct` (`market_analytics_service.py:201-205`), `_window_count` (`:251-253`), used at `skill_gap_service.py:597-599`.

**Dashboard display.** Skill-gap growth column, rising-demand list.

**Storage.** Derived.

**Edge cases.** Previous zero returns `None` (not "+∞%" and not "+100%"); the UI shows "new" / "not comparable".

### F-5.4 — Skill-gap priority score

**Status:** Implemented (explicitly documented as a transparent heuristic, **not** an industry standard)
**Expression**

When comparable growth exists:

$$
\text{priority}(k)=0.5\,\text{demand}(k)+0.4\,\text{gap}(k)+0.1\cdot\frac{\mathrm{clamp}(\text{growth}(k),-100,100)+100}{2}
$$

When no comparable growth exists:

$$
\text{priority}(k)=\frac{0.5\,\text{demand}(k)+0.4\,\text{gap}(k)}{0.9}
$$

Both rounded to 1 dp.

**Variables.** `PRIORITY_WEIGHTS = {demand: 0.5, gap: 0.4, growth: 0.1}`.

**Worked example.** demand 30.0, gap 60.0, growth 20.0:
growth component $=(20+100)/2=60$; priority $=15+24+6=45.0$.
Without comparable growth: $(15+24)/0.9=43.33\rightarrow43.3$.

**Why used.** Ranks skills by a blend of market pull, student shortfall, and momentum. Re-weighting the available dimensions (rather than inserting a zero growth term) avoids unfairly penalising skills with no history.

**Implementation.** `_priority_score` (`skill_gap_service.py:202-220`), constants at `:127-129`.

**Dashboard display.** Default "Priority" sort and priority column in the skill-gap table.

**Storage.** Derived.

**Edge cases.** Growth is clamped to $[-100,100]$ so a doubling cannot dominate the score. The response also publishes the weights and thresholds so the number is auditable.

### F-5.5 — Priority class

**Status:** Implemented
**Expression**

$$
\text{class}(p)=
\begin{cases}
\text{high} & p\ge60\\
\text{medium} & 40\le p<60\\
\text{low} & p<40
\end{cases}
$$

**Worked example.** $p=60.0\rightarrow$ high; $p=59.9\rightarrow$ medium; $p=40.0\rightarrow$ medium; $p=39.9\rightarrow$ low.

**Why used.** Gives the table a stable grouping without inventing statistical significance.

**Implementation.** `_priority_class` (`:223-228`), `PRIORITY_CLASS_THRESHOLDS = {"high": 60.0, "medium": 40.0}`.

**Storage.** Derived.

**Edge cases.** Thresholds are inclusive at the lower bound of each class.

### F-5.6 — Assessment evidence classification

**Status:** Implemented
**Expression**

$$
\text{evidence}(s,k)=
\begin{cases}
\text{insufficient} & a_{s,k}<3\\
\text{demonstrated} & a_{s,k}\ge3\ \wedge\ \text{acc}_{s,k}\ge75\\
\text{developing} & a_{s,k}\ge3\ \wedge\ 50\le\text{acc}_{s,k}<75\\
\text{not\_demonstrated} & a_{s,k}\ge3\ \wedge\ \text{acc}_{s,k}<50
\end{cases}
$$

$$
\text{acc}_{s,k}=100\cdot\frac{\text{correct}_{s,k}}{a_{s,k}}
$$

**Variables.** $a_{s,k}$ = graded answers by student $s$ on questions tagged skill $k$.

**Worked example.** 2 answers, 2 correct $\Rightarrow$ `insufficient` (not demonstrated). 4 answers, 3 correct $\Rightarrow75.0\%\rightarrow$ `demonstrated`.

**Why used.** Prevents one lucky answer from certifying a skill.

**Implementation.** `MIN_GRADED_ANSWERS = 3`, `DEMONSTRATED_MIN_PCT = 75.0`, `DEVELOPING_MIN_PCT = 50.0`; `_classify_accuracy` (`:192-199`) and the per-student loop (`:634-646`).

**Dashboard display.** Skill-gap student drill-down filters (`all` / `demonstrated` / `developing` / `not_demonstrated` / `insufficient`).

**Storage.** Derived.

**Edge cases.** Only `is_correct` values that are not `None` are counted; ungraded descriptive answers do not create evidence.

### F-5.7 — Evidence partition and "no evidence" count

**Status:** Implemented
**Expression**

$$
R=\{\text{self-reported}\},\quad E=\{\text{assessed (demonstrated/developing/not)}\},\quad I=\{\text{insufficient}\}
$$

$$
\text{reported\_only}=\lvert R\setminus E\rvert,\qquad
\text{both}=\lvert R\cap E\rvert,\qquad
\text{no\_evidence}=P-\lvert R\cup E\cup I\rvert
$$

**Worked example.** $P=29$, reported 10, assessed 12, insufficient 4, overlap 3 $\Rightarrow$ reported-only 7, both 3, no-evidence $29-(10+12+4-3)=29-23=6$.

**Why used.** Distinguishes "claims the skill" from "proved the skill" and keeps the categories mutually exclusive.

**Implementation.** `skill_gap_service.py:648-660`.

**Dashboard display.** Skill detail panel evidence breakdown.

**Storage.** Derived.

**Edge cases.** A student with insufficient evidence is never promoted into a demonstrated/developing class, and their self-report is still visible.

### F-5.8 — Demonstrated percentage

**Status:** Implemented
**Expression**

$$
\text{demonstrated\_pct}(k)=\mathrm{round}\!\left(100\cdot\frac{D_k}{P},\,1\right)
$$

**Worked example.** 12 of 29 $\Rightarrow41.4\%$; the complement of F-5.2 up to rounding.

**Why used.** The demand-vs-proficiency chart needs a proficiency axis on the same 0–100 scale as demand.

**Implementation.** `skill_gap_service.py:694`.

**Storage.** Derived.

**Edge cases.** `demonstrated_pct + gap_pct` may differ from 100.0 by 0.1 due to independent rounding.

---

## 6. Market analytics (Trending Skills)

**Source of truth:** `backend/app/services/market_analytics_service.py`
**Collections:** `job_market_postings`, `market_skill_catalog`, `market_import_runs`
**Endpoints:** `GET /api/v1/analytics/tpo/market`, `/market/filters`, `/market/comparison`

All market figures are computed from the historical job-posting dataset, **not** from placement drives. They are global (not scoped to a TPO's drives). The UI keeps a data-source banner because imported postings can be demo data.

### F-6.1 — Demand share

**Status:** Implemented
**Expression**

$$
\text{demand}(k)=\mathrm{round}\!\left(100\cdot\frac{n_k}{N},\,1\right)
$$

**Variables.** $n_k$ = postings requiring skill $k$; $N$ = postings in the filtered population. One posting that requires a skill five times still counts once for this metric (skill presence per posting).

**Worked example.** 40 of 250 postings $\Rightarrow16.0\%$.

**Why used.** The shared denominator makes every skill comparable within one response and across charts.

**Implementation.** `_pct` (`market_analytics_service.py:197-198`); `_skill_record` (`:460-499`).

**Dashboard display.** Trending Skills demand bar, summary cards, comparison entity shares.

**Storage.** Derived.

**Edge cases.** $N=0\Rightarrow0.0$; the endpoint returns an empty dataset with an explicit disclaimer rather than a divide error.

### F-6.2 — Year-over-year growth

**Status:** Implemented
**Expression**

$$
\text{growth}(k)=\mathrm{round}\!\left(100\cdot\frac{c_{\text{current}}-c_{\text{previous}}}{c_{\text{previous}}},\,1\right)
$$

with `None` when $c_{\text{previous}}=0$.

**Worked example.** 120 current vs 100 previous $\Rightarrow+20.0\%$; 80 vs 100 $\Rightarrow-20.0\%$.

**Why used.** Momentum is more actionable than a static share.

**Implementation.** `_growth_pct` (`:201-205`); `_skill_record` (`:470-489`).

**Dashboard display.** Trending table "YoY" column, trend badge tooltip.

**Storage.** Derived.

**Edge cases.** Zero previous is `None`, never an infinite or fabricated percentage.

### F-6.3 — Comparable comparison window

**Status:** Implemented
**Expression**

$$
e_{\text{latest}}=\max\!\big(1,\ \min(12,\ \text{coverage}[\text{latest}],\ \text{coverage}[\text{latest}-1])\big)
$$

For a historical year $y$:

$$
e_y=\max\!\big(1,\ \min(12,\ \text{coverage}[y],\ \text{coverage}[y-1])\big)
$$

**Variables.** `coverage[y]` = highest calendar month present for year $y$ in the filtered population; default 12 when unknown.

**Worked example.** Latest year has data through June, previous year through December $\Rightarrow e=6$. Both sides of the YoY comparison are restricted to January–June.

**Why used.** Comparing Jan–Jun 2026 with all of 2025 would produce a fake decline caused only by calendar coverage.

**Implementation.** `_comparison_end_month` (`:234-243`), `_historical_end_month` (`:246-248`), `_window_count` (`:251-253`).

**Storage.** Derived.

**Edge cases.** When the latest year is a full year (`e=12`), the windowed and full counters are identical, so the restriction is a no-op.

### F-6.4 — Trend classification

**Status:** Implemented
**Expression**

$$
\text{trend}(k)=
\begin{cases}
\text{None} & \neg\text{comparable}\\
\text{emerging} & c_{\text{prev}}=0\ \wedge\ c_{\text{cur}}>0\\
\text{None} & c_{\text{prev}}=0\ \wedge\ c_{\text{cur}}=0\\
\text{rising} & g\ge10\\
\text{declining} & g\le-10\\
\text{stable} & \text{otherwise}
\end{cases}
$$

where $g=100\,(c_{\text{cur}}-c_{\text{prev}})/c_{\text{prev}}$ is the **unrounded** growth.

**Worked example.** 100→110 is `rising` (exactly +10%); 100→109.9 is `stable`; 100→90 is `declining` (exactly −10%).

**Why used.** A ±10% dead-band prevents noise from being labelled momentum.

**Implementation.** `_classify_trend` (`:208-219`).

**Dashboard display.** Trend badge (rising / stable / declining / emerging) across the Trending Skills page.

**Storage.** Derived.

**Edge cases.** `comparable=False` yields `None` and the UI says "not comparable", never "stable".

### F-6.5 — Weighted trend score

**Status:** Implemented
**Expression**

$$
\text{trend\_score}(k)=\mathrm{round}\!\left(\sum_{y\in Y}\frac{w_y}{\sum_{z\in Y}w_z}\cdot\text{demand}(k,y),\,2\right)
$$

$$
w_y=
\begin{cases}
(0.40,0.30,0.20,0.10)[\text{latest}-y] & 0\le\text{latest}-y<4\\
0 & \text{otherwise}
\end{cases}
$$

If $\sum_y w_y=0$, all present years receive equal weight $w_y=1$.

**Variables.** $Y$ = years present in the filtered population; $\text{demand}(k,y)$ = skill $k$'s demand share within year $y$.

**Worked example.** Latest year 2026; shares 2023=10.0, 2024=12.0, 2025=15.0, 2026=18.0:
$0.10\cdot10+0.20\cdot12+0.30\cdot15+0.40\cdot18=1.0+2.4+4.5+7.2=15.10$.

**Why used.** Recency-weighted average of share, not raw count, so a growing total posting volume does not inflate every skill equally.

**Implementation.** `_TREND_WEIGHTS_BY_YEAR_OFFSET = (0.40,0.30,0.20,0.10)` (`:140`), `_trend_score` (`:256-298`).

**Dashboard display.** Default "trending" sort and the trend score in the Trending Skills table.

**Storage.** Derived.

**Edge cases.**
- If every present year is older than the 4-year window, the uniform fallback prevents a zero score.
- When the latest year is partial, every compared year uses the same partial window (`use_partial_window=True`), so the score cannot drop for calendar reasons.

### F-6.6 — Entity posting share (comparison)

**Status:** Implemented
**Expression**

$$
\text{share}(e)=\mathrm{round}\!\left(100\cdot\frac{n_e}{N_{\text{whole population}}},\,1\right)
$$

**Worked example.** Company with 30 postings in a 250-posting population $\Rightarrow12.0\%$.

**Why used.** Comparison entities must be measured against the same whole-population denominator; using the selected group's total would make shares depend on which peers were chosen.

**Implementation.** `get_market_comparison` (`:996-1134`), `posting_share_pct` at `:1118-1123`.

**Dashboard display.** Comparison section entity headers.

**Storage.** Derived.

**Edge cases.** At most 6 entities can be compared; more returns HTTP 400. An entity with no postings in the filtered population returns empty skills so the UI can say so.

### F-6.7 — Technical / soft skill instance share

**Status:** Implemented
**Expression**

$$
\text{tech\_share}(e)=\mathrm{round}\!\left(100\cdot\frac{I_{\text{tech}}}{I_{\text{tech}}+I_{\text{soft}}},\,1\right)
$$

**Variables.** $I$ counts **instances**: one posting requiring one skill contributes 1. A posting can contribute to both totals.

**Worked example.** 60 technical instances and 40 soft instances $\Rightarrow60.0\%$ / $40.0\%$.

**Why used.** Separates the technical/soft composition of demand from the number of postings.

**Implementation.** `market_analytics_service.py:1123-1124`.

**Storage.** Derived.

**Edge cases.** Zero instances yields 0.0 for both shares (the entity is already reported as having no postings).

### F-6.8 — Market summary YoY growth

**Status:** Implemented
**Expression**

$$
\text{summary\_growth}=\mathrm{round}\!\left(100\cdot\frac{P_{\text{current}}-P_{\text{previous}}}{P_{\text{previous}}},\,1\right)
$$

**Variables.** $P$ = total postings in the comparable window.

**Worked example.** 500 current vs 400 previous $\Rightarrow+25.0\%$.

**Why used.** A headline market-volume signal alongside skill-level trends.

**Implementation.** `_build_response` (`:631` onward) using the same `_growth_pct`.

**Storage.** Derived.

**Edge cases.** `None` when the previous window has no postings.

---

## 7. Student insights and focus ranking

**Source of truth:** `backend/app/services/student_insights_service.py`
**Endpoint:** `GET /api/v1/insights/me` (student only, 20/min)
**Collection:** `insights_narrative_cache` (LLM narrative cache only)

### F-7.1 — Overall accuracy

**Status:** Implemented
**Expression**

$$
\text{accuracy}=\mathrm{round}\!\left(100\cdot\frac{\sum_{i\in\text{submitted}}\sum_{j\in\text{answers}(i)}[is\_correct_{ij}=\text{True}]}{\sum_{i\in\text{submitted}}\sum_{j\in\text{answers}(i)}[is\_correct_{ij}\ne\text{None}]},\,1\right)
$$

with $0.0$ when the denominator is 0.

**Worked example.** 45 correct out of 80 graded answers $\Rightarrow56.3\%$.

**Why used.** Ungraded descriptive answers are neither right nor wrong, so they must not lower accuracy.

**Implementation.** `build` (`student_insights_service.py:218-310`).

**Dashboard display.** Student insights stat cards.

**Storage.** Derived.

**Edge cases.** Deleted questions are skipped entirely (their answers cannot be attributed), so they affect neither numerator nor denominator.

### F-7.2 — Focus priority

**Status:** Implemented
**Expression**

$$
\text{priority}(s)=(100-M_s)+2\cdot100\cdot\frac{w_s}{v_s}
$$

with $w_s/v_s=0$ when $v_s=0$.

**Variables**

| Symbol | Meaning |
|---|---|
| $M_s$ | Mastery for skill $s$ (50.0 if no state). |
| $w_s$ | Wrong answers on skill $s$ across submitted attempts. |
| $v_s$ | Times skill $s$ was seen. |
| $2$ | `_FOCUS_WEIGHT_ERROR_RATE = 2.0`. |

**Worked example.** $M=40$, wrong 3, seen 10 $\Rightarrow(100-40)+200\cdot0.3=60+60=120.0$.

**Why used.** Mastery deficit dominates; the error-rate term breaks ties toward skills the student repeatedly misses.

**Implementation.** `_rank_skills` (`:325-373`), constant at `:73`.

**Dashboard display.** Student insights "Focus areas", ordered by descending priority.

**Storage.** Derived.

**Edge cases.** A skill can be in the focus list only if $M_s<50$ (`WEAK_MASTERY_THRESHOLD`). Priority is still computed for strengths and returned in the payload.

### F-7.3 — Severity

**Status:** Implemented
**Expression**

$$
\text{severity}(s)=
\begin{cases}
\text{critical} & M_s<35\ \wedge\ w_s>0\\
\text{weak} & M_s<50\\
\text{watch} & w_s>0\\
\text{ok} & \text{otherwise}
\end{cases}
$$

**Worked example.** $M=30$, wrong 2 $\Rightarrow$ critical. $M=30$, wrong 0 $\Rightarrow$ weak (no miss evidence yet). $M=60$, wrong 1 $\Rightarrow$ watch.

**Why used.** Distinguishes "low mastery" from "actively missing questions" without inventing a probability.

**Implementation.** `_severity` (`:376-383`), `CRITICAL_MASTERY_THRESHOLD = 35.0`.

**Storage.** Derived.

**Edge cases.** The ordering of the branches matters: critical requires both conditions, so low mastery with no misses is only "weak".

### F-7.4 — Skill trend direction

**Status:** Implemented
**Expression.** Let $a_1,\dots,a_n$ be the student's accuracy on a skill in each submitted attempt, ordered by submission time, and $\Delta_i=a_{i+1}-a_i$.

$$
\text{trend}=
\begin{cases}
\text{unknown} & n<2\\
\text{steady} & \exists i:\Delta_i>0\ \wedge\ \exists j:\Delta_j<0\\
\text{improving} & a_n-a_1>5\\
\text{declining} & a_n-a_1<-5\\
\text{steady} & \text{otherwise}
\end{cases}
$$

**Worked example.** Accuracies 40 → 55 → 70: deltas both positive, end-to-end $+30>5\Rightarrow$ improving. Accuracies 40 → 70 → 45: both signs present $\Rightarrow$ steady.

**Why used.** Fluctuation is not a trend; a 5-point band is treated as noise.

**Implementation.** `_trend_from_attempts` (`:386-411`).

**Dashboard display.** Focus/strength rows and the narrative facts.

**Storage.** Derived.

**Edge cases.** Practice attempts and in-progress attempts are excluded, as is the tracer's own history (which includes practice).

### F-7.5 — Strength classification

**Status:** Implemented
**Expression**

$$
\text{strength}(s)=[M_s\ge70]\ \wedge\ [w_s=0]\ \wedge\ [v_s>0]
$$

**Worked example.** $M=72$, wrong 0, seen 4 $\Rightarrow$ strength. $M=72$, wrong 0, seen 0 $\Rightarrow$ not a strength (no evidence).

**Why used.** A strength must be both high-mastery and clean in real attempts.

**Implementation.** `_rank_skills` (`:366-369`).

**Storage.** Derived.

**Edge cases.** Note the asymmetry with the tracer's `STRONG_THRESHOLD = 75`: insights uses 70 for the strengths list. Both constants are intentional; the insights threshold is local to the service.

### F-7.6 — Study-guide ordering

**Status:** Implemented
**Algorithm**

1. Count wrong answers per question across submitted attempts.
2. Deduplicate by normalised question text (`" ".join(text.lower().split())`).
3. Order by focus-area rank first, then by descending miss count.
4. Cap at `STUDY_GUIDE_MAX_ITEMS = 10`.

**Worked example.** Two identical questions missed 3 and 2 times collapse to one row; the row keeps the higher miss count.

**Why used.** Surfaces the specific questions to review rather than a vague skill label, without showing the same question twice.

**Implementation.** `_build_study_guide` (`:413-475`).

**Storage.** Derived.

**Edge cases.** No wrong answers returns an empty guide; the narrative then returns `None` without calling the LLM.

### F-7.7 — Narrative cache key

**Status:** Implemented
**Expression**

$$
\text{key}=\mathrm{SHA256}\Big(\mathrm{repr}\big(\mathrm{sorted}(\text{facts.items})\big)\Big)
$$

**Worked example.** Changing one focus skill's mastery changes the fact tuple, producing a different key and a cache miss.

**Why used.** Avoids paying for an identical LLM narrative twice; the cache is consulted **before** RAG retrieval, so a hit costs zero embedding calls.

**Implementation.** `_maybe_narrate` (`:476-558`), cache at `:513`; `_trim_narrative_cache` keeps 200 entries.

**Storage.** `insights_narrative_cache` documents keyed by the hash; only the generated narrative is cached.

**Edge cases.** Dict ordering is normalised by sorting; nested structures are stringified by `repr`, so any change in facts invalidates the entry. Cache failure must never fail the request.

---

## 8. Resume–job matching

**Source of truth:** `backend/app/services/matching_service.py`, `backend/app/ml/matching/inference.py`
**Collections:** `resumes`, `placement_drives`, `companies`, `applications`, `assessments`
**Endpoints:** `GET /api/v1/matching/drives/{id}/score`, `/matching/recommended-drives`, `/matching/drives/{id}/ranked-applicants`

### F-8.1 — Final match score

**Status:** Implemented
**Expression**

$$
F=0.40\,S+0.30\,K+0.20\,E+0.10\,A
$$

$$
A=
\begin{cases}
\text{assessment\_score\_pct}/100 & \text{assessment required and scored}\\
1.0 & \text{otherwise}
\end{cases}
$$

**Variables**

| Symbol | Meaning |
|---|---|
| $S$ | Calibrated cross-encoder semantic probability ∈ [0,1]. |
| $K$ | Skills coverage. |
| $E$ | Experience fit. |
| $A$ | Assessment component, normalised to [0,1]. |

**Worked example.** $S=0.82$, $K=3/5=0.6$, $E=2/3=0.6667$, $A=70/100=0.7$:
$F=0.328+0.18+0.1333+0.07=0.7113$.

**Why used.** Blends semantic relevance with hard requirements and assessment evidence. The weights are a documented product decision, not a learned parameter.

**Implementation.** `compute_final_score` (`matching_service.py:69-97`) — the declared single source of truth; called by both ranking wrappers and by screening.

**Dashboard display.** Student drive card match score, TPO ranked applicants, application explanation breakdown.

**Storage.** Persisted by screening into `applications.final_score` (4 dp); `semantic_score`, `skills_score`, `experience_score` stored alongside.

**Edge cases.**
- If no assessment is required or it is unscored, $A=1.0$ (full credit). This is deliberate: absence of a requirement must not penalise a candidate.
- `rank_drives_for_resume` never passes assessment data, so **every student-facing drive recommendation gets the full 10% assessment term**. This is a known asymmetry, not a claim that the student passed.
- A drive with zero required skills yields $K=0$ (denominator `max(1, 0)`), not full credit.

### F-8.2 — Skills coverage

**Status:** Implemented
**Expression**

$$
K=\frac{\lvert R\cap J\rvert}{\max(1,\lvert J\rvert)}
$$

**Variables.** $R$ = canonical resume skill set; $J$ = canonical drive required-skill set. Both are canonicalised by `skill_ontology.to_skill_set`.

**Worked example.** Resume {Python, React, SQL}; drive {Python, React, Docker, AWS, SQL} $\Rightarrow K=3/5=0.6$.

**Why used.** Direct, explainable coverage of the stated requirement.

**Implementation.** `matching_service.py:188-199` and `:225-239`.

**Storage.** `applications.skills_score`; `matched_skills` / `missing_skills` arrays.

**Edge cases.** The denominator is always the **JD's** skill count, so the metric is intentionally asymmetric. Extra resume skills do not help.

### F-8.3 — Experience fit

**Status:** Implemented
**Expression**

$$
E=\begin{cases}
1.0 & y_{\text{jd}}\le0\\
\mathrm{clamp}\!\left(\dfrac{y_{\text{resume}}}{y_{\text{jd}}},\,0,\,1\right) & y_{\text{jd}}>0
\end{cases}
$$

**Worked example.** 2 years vs 3 required $\Rightarrow0.6667$; 5 years vs 3 required $\Rightarrow1.0$ (capped).

**Why used.** Over-qualification should not produce a score above 1, and a zero requirement means everyone fits.

**Implementation.** `exp_fit` (`matching_service.py:62-66`).

**Storage.** `applications.experience_score`.

**Edge cases.** A missing resume `experience_years` is treated as 0.0 by `build_resume_text`, yielding $E=0$ when the JD requires experience.

### F-8.4 — Retrieve-then-rerank

**Status:** Implemented
**Expression**

$$
\text{pool}=\operatorname{TopK}_{j}\big(\cos(\mathbf{q},\mathbf{d}_j),\,k=100\big)
$$

$$
F_j=0.40\,\sigma_{\text{cal}}\big(\mathrm{CE}(r,d_j)\big)+0.30\,K_j+0.20\,E_j+0.10\,A_j
$$

**Variables.** $\mathbf{q}$ = resume bi-encoder embedding; $\mathbf{d}_j$ = drive embedding; CE = cross-encoder logit; $\sigma_{\text{cal}}$ = sigmoid followed by Platt calibration.

**Worked example.** 250 open drives $\rightarrow$ bi-encoder prunes to 100 $\rightarrow$ cross-encoder scores 100 pairs $\rightarrow$ sorted by $F$.

**Why used.** Cross-encoding every pair is expensive; bi-encoder cosine is a cheap recall stage.

**Implementation.** `_retrieve_top_k` (`:253-265`), `rank_drives_for_resume` (`:295-306`), `rank_resumes_for_drive` (`:308-...`), `DEFAULT_RETRIEVER_POOL = 100` (`:33`).

**Storage.** Resume and drive embeddings are cached in `resumes.resume_embedding` and `placement_drives.jd_embedding`; they are invalidated (`null`) when the source text or skills change.

**Edge cases.**
- If the candidate count is $\le k$, no ordering is applied at the retrieval stage; the final score sort still determines output order.
- Cached embeddings carry **no model stamp**; replacing the bi-encoder artifact does not invalidate them, and mixed dimensions would break `np.stack`.
- A missing artifact set raises `MatchingUnavailableError`, surfaced as HTTP 503 by the matching router.

### F-8.5 — Screening recommendation thresholds

**Status:** Implemented
**Expression**

$$
\text{eligible}(a)=[a.\text{eligibility\_passed}\ne\text{false}]
$$

$$
\text{recommended}(a)=\text{eligible}(a)\ \wedge\ a.\text{assessment\_status}\in\{\text{passed},\text{not\_required}\}\ \wedge\ a.\text{final\_score}\ge0.65
$$

$$
\text{shortlist}(a)=\text{eligible}(a)\ \wedge\ a.\text{assessment\_status}\in\{\text{passed},\text{not\_required}\}\ \wedge\ a.\text{status}=\text{applied}\ \wedge\ a.\text{final\_score}\ge0.60
$$

Top $n=10$ shortlist rows by `final_score` descending (API bounds: $n\in[1,100]$, min score $\in[0,1]$).

**Worked example.** Score 0.64 with assessment passed $\Rightarrow$ counts toward the summary recommendation (≥0.65? no — 0.64 fails) and toward the shortlist (≥0.60? yes), provided status is still `applied`.

**Why used.** Two different actions: a summary count of strong candidates (stricter) versus a suggested shortlist (slightly looser).

**Implementation.** `screening_service.get_screening_summary` (`:162-204`), `get_recommended_shortlist` (`:206-223`), router defaults (`routers/drives.py:299-312`).

**Storage.** Read-only; screening itself persists scores but does not change `status`.

**Edge cases.**
- `eligibility_passed = None` (never screened) counts as eligible.
- A missing student profile leaves `is_eligible = True` with no reasons.
- Screening calls `rank_resumes_for_drive` **without** assessment arguments, so its first pass gives full assessment credit; the persisted `final_score` is recomputed with the real assessment percentage. Only the recomputed value is stored.

### F-8.6 — Eligibility rules

**Status:** Implemented
**Expression**

$$
\text{eligible}(s,d)=
[\,d.\text{min\_cgpa}=\text{null}\ \vee\ (s.\text{cgpa}\ne\text{null}\ \wedge\ s.\text{cgpa}\ge d.\text{min\_cgpa})\,]
$$
$$
\wedge\ [\,d.\text{departments}=\varnothing\ \vee\ \text{norm}(s.\text{department})\in\text{norm}(d.\text{departments})\,]
$$
$$
\wedge\ [\,d.\text{batch\_years}=\varnothing\ \vee\ s.\text{batch\_year}\in d.\text{batch\_years}\,]
$$

**Worked example.** min CGPA 7.0, student 7.2, department Computer Science, batch 2026 in [2025, 2026] $\Rightarrow$ eligible.

**Why used.** Explicit, inspectable rules; no hidden scoring.

**Implementation.** `drive_service._check_eligibility` and `screening_service.screen_applications` (`:113-126`).

**Storage.** `applications.eligibility_passed`, `eligibility_reasons[]`.

**Edge cases.** There is **no backlog rule** anywhere in the backend. A missing student profile is treated as eligible in screening (documented gap).

---

## 9. Transformer and neural-network mathematics (inference)

**Source of truth:** `backend/app/ml/matching/inference.py`
**Artifacts:** `backend/app/ml/matching/artifacts/{bi_encoder,cross_encoder,calibrator.pkl}`

> **Status: Implemented for inference; no training code exists in this repository.** The training description below comes from the shipped model card (`artifacts/cross_encoder/README.md`) and is included so the numbers are traceable. It is not executed by the backend.

### F-9.1 — Bi-encoder mean pooling

**Status:** Implemented
**Expression**

$$
\mathbf{h}_t=\mathrm{BERT}(x)_t,\qquad
\mathbf{m}=\frac{\sum_{t=1}^{T}m_t\,\mathbf{h}_t}{\max\!\left(\sum_{t=1}^{T}m_t,\ 10^{-9}\right)}
$$

**Variables.** $m_t\in\{0,1\}$ is the attention mask; $T\le256$; hidden size 384.

**Worked example.** Three real tokens with vectors summing to $[3,6,9]$ and mask sum 3 $\Rightarrow\mathbf{m}=[1,2,3]$.

**Why used.** Converts a variable-length token sequence into one fixed-size sentence vector.

**Implementation.** `MatchingEngine.embed_texts` (`inference.py:155-178`); `_BI_MAX_LENGTH = 256`; pooling mode `mean` from `1_Pooling/config.json`.

**Storage.** `resumes.resume_embedding`, `placement_drives.jd_embedding` (plain float lists).

**Edge cases.** Empty input returns a `(0, hidden)` array. Padding tokens are excluded by the mask.

### F-9.2 — L2 normalisation

**Status:** Implemented
**Expression**

$$
\hat{\mathbf{m}}=\frac{\mathbf{m}}{\lVert\mathbf{m}\rVert_2+\varepsilon}
$$

**Worked example.** $\mathbf{m}=[3,4]\Rightarrow\hat{\mathbf{m}}=[0.6,0.8]$.

**Why used.** After normalisation, the dot product equals cosine similarity, so retrieval is a single matrix multiply.

**Implementation.** `torch.nn.functional.normalize(..., p=2, dim=1)` (`inference.py:176`); the `Normalize` module is also recorded in `modules.json`.

**Storage.** Cached embeddings are stored already normalised.

**Edge cases.** A zero vector is guarded by the epsilon in the torch implementation.

### F-9.3 — Cosine similarity

**Status:** Implemented
**Expression**

$$
\cos(\mathbf{q},\mathbf{d})=\hat{\mathbf{q}}\cdot\hat{\mathbf{d}}=\sum_{i=1}^{384}q_i d_i
$$

**Worked example.** $\hat{\mathbf{q}}=[1,0]$, $\hat{\mathbf{d}}=[0.6,0.8]\Rightarrow0.6$.

**Why used.** Ranking metric for the retrieval pool.

**Implementation.** `MatchingEngine.cosine_similarity` (`:180-186`) — a matrix product because both sides are unit vectors.

**Storage.** Derived.

**Edge cases.** Empty candidate matrix returns an empty score array.

### F-9.4 — Cross-encoder scoring

**Status:** Implemented
**Expression**

$$
z=\mathrm{clamp}\big(\mathrm{RoBERTa}(r,d).\text{logits},\,-50,\,50\big),\qquad
p=\sigma(z)=\frac{1}{1+e^{-z}}
$$

**Variables.** Input order is always `(resume_text, jd_text)`; max length 256; one output logit.

**Worked example.** $z=1.386\Rightarrow p=0.8$.

**Why used.** Joint attention over both texts captures requirement-specific relevance that independent embeddings miss.

**Implementation.** `MatchingEngine.score_pairs` (`:194-214`); `_CROSS_MAX_LENGTH = 256`; clamp guards overflow before sigmoid.

**Storage.** Not persisted; recomputed per request.

**Edge cases.** An empty batch returns the empty array unchanged.

### F-9.5 — Platt calibration

**Status:** Implemented
**Expression**

$$
p_{\text{cal}}=\mathrm{LogisticRegression}.\text{predict\_proba}\big([p]\big)[1]
=\frac{1}{1+e^{-(a\,p+b)}}
$$

**Variables.** $a,b$ are the fitted coefficients inside `calibrator.pkl` (scikit-learn `LogisticRegression`).

**Worked example.** If $a=2.0$, $b=-0.5$ and $p=0.8$, the calibrated score is $\sigma(1.1)=0.7503$.

**Why used.** Raw cross-encoder sigmoid outputs are not calibrated probabilities; Platt scaling maps them onto observed match rates.

**Implementation.** `calibrate` (`:216-222`), artifact loaded with `pickle.load` at `:138-139`.

**Storage.** `calibrator.pkl` (~4 KB), loaded once with the engine.

**Edge cases.** The pickle was created with scikit-learn 1.6.1 and loaded under 1.9.1; this emits a warning but produces finite, monotonic output (documented in `MODEL_VALIDATION.md`). Loading fails closed with `MatchingModelsUnavailable` if artifacts are missing.

### F-9.6 — Softmax attention (architecture description)

**Status:** Implemented inside the pretrained transformer (not authored here)
**Expression**

$$
\mathrm{Attention}(Q,K,V)=\mathrm{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}+M\right)V
$$

**Variables.** $d_k$ = per-head dimension (384/12 = 32 for the bi-encoder); $M$ is the additive attention mask ($-\infty$ on padding).

**Worked example.** With $d_k=32$, the scale factor is $1/\sqrt{32}\approx0.1768$.

**Why used.** Standard scaled dot-product attention; documented here because the model cards specify 12 heads and 6 (bi) / 12 (cross) layers.

**Implementation.** Supplied by Hugging Face `BertModel` / `RobertaForSequenceClassification`; the backend only calls forward passes.

**Storage.** Model weights in the artifacts directories.

**Edge cases.** Sequence length is capped at 256, so longer resumes/JDs are truncated, not chunked.

### F-9.7 — Training objective (model card only)

**Status:** Documented, **not implemented in this repository**
**Expression**

$$
\mathcal{L}_{\text{BCE}}=-\frac{1}{N}\sum_{i=1}^{N}\Big[y_i\log \hat{y}_i+(1-y_i)\log(1-\hat{y}_i)\Big]
$$

**Variables.** $y_i$ = labelled pair relevance; $\hat{y}_i$ = sigmoid output. Model card: 17,658 pairs, 2 epochs, learning rate $5\times10^{-5}$, base `cross-encoder/stsb-roberta-base`.

**Why included.** So the provenance of the calibrator and cross-encoder is explicit and not mistaken for code in this repo. No training script is shipped.

---

## 10. Retrieval-augmented generation (RAG)

**Source of truth:** `backend/app/ml/rag/knowledge_store.py`
**Collection:** `knowledge_chunks`
**Backend:** `mongodb_cosine` (vectors stored in MongoDB, scored in Python)

### F-10.1 — Chunking

**Status:** Implemented
**Algorithm.** `max_chars=1200`, `overlap=150`.

1. Return `[text]` if `len(text) <= 1200`.
2. Split on blank lines and accumulate paragraphs up to the budget.
3. Split an oversized paragraph on sentence boundaries (`(?<=[.!?])\s+`).
4. Hard-split with overlap as a last resort.

**Worked example.** A 2,600-character document with no paragraph breaks becomes chunks of 1,200 / 1,200 / 350 characters, with 150-character overlap between hard splits.

**Why used.** Keeps chunks small enough to embed and inject into a prompt, while preserving paragraph/sentence boundaries when possible.

**Implementation.** `_chunk_text` (`knowledge_store.py`); `ingest_long`.

**Storage.** One document per chunk in `knowledge_chunks`, with `chunk_index` and `source_id = "<source>#<idx>"`.

**Edge cases.** Empty text inserts nothing (`ingest` returns `False`); an embedding failure also returns `False` rather than crashing the caller.

### F-10.2 — Retrieval cosine similarity

**Status:** Implemented
**Expression**

$$
\text{sim}(\mathbf{q},\mathbf{v})=\frac{\mathbf{q}\cdot\mathbf{v}}{\lVert\mathbf{q}\rVert_2\lVert\mathbf{v}\rVert_2+\varepsilon}
=\hat{\mathbf{q}}\cdot\hat{\mathbf{v}}
$$

**Variables.** $\mathbf{q}$ = embedding of the comma-joined query skills; $\mathbf{v}$ = stored chunk vector.

**Worked example.** $\hat{\mathbf{q}}=[1,0]$, $\hat{\mathbf{v}}=[0.6,0.8]\Rightarrow0.6$.

**Why used.** Model-agnostic similarity that works with any embedding provider.

**Implementation.** `retrieve` (`:225-...`); normalisation uses `np.linalg.norm(...) + 1e-9`.

**Storage.** `knowledge_chunks.vector`, `embed_model`, `embed_dim`.

**Edge cases.**
- Chunks whose `embed_model` does not match the current `EMBEDDING_MODEL`, or whose dimension differs, are skipped as foreign. Chunks with no `embed_model` stamp are also skipped.
- Retrieval is a **hard pre-filter** on `tags: {"$in": query_skills}` and `chunk_type`; a semantically relevant chunk with different tags is never scored.
- Empty `query_skills` returns `[]` without an embedding call.

### F-10.3 — Top-K selection

**Status:** Implemented
**Expression**

$$
\mathcal{R}=\operatorname{TopK}_{v\in C}\big(\text{sim}(\mathbf{q},\mathbf{v}),\,k\big),\qquad k=5\ \text{(default)}
$$

**Worked example.** Ten eligible chunks with similarities 0.91, 0.88, 0.72, … $\Rightarrow$ the first five are returned in descending order.

**Why used.** Bounds prompt size and cost.

**Implementation.** `retrieve` sorts by score descending and slices `[:top_k]`. Call sites: JD explanation `top_k=5`, application explanation `top_k=4`, insights/gap analysis `top_k=5`.

**Storage.** Read-only.

**Edge cases.** If embeddings are unavailable, retrieval returns `[]` and the narrative proceeds ungrounded; the deterministic breakdown is still returned.

### F-10.4 — Ingestion deduplication

**Status:** Partial
**Expression.** None. There is **no vector-level deduplication**; the only idempotency is `delete_by_source_prefix` used by the seed script.

**Worked example.** Re-running the seed script for taxonomy deletes `seed:skill_taxonomy*` first, then re-inserts; posting the same chunk twice via the admin API creates two rows.

**Why used.** Simple, predictable ingestion.

**Implementation.** `delete_by_source_prefix` (`:192`), seed script `scripts/seed_knowledge_store.py`.

**Storage.** `knowledge_chunks`.

**Edge cases.** `job_description` chunks are never ingested automatically: `drive_service` only invalidates `jd_embedding`, and the JD explanation router's ingestion hook is commented out. Only an admin `POST /admin/knowledge/chunks` creates them.

---

## 11. Statistical operations inventory

This section answers "which statistics does PLACER actually compute?" so no reader assumes more rigour than exists.

| Operation | Implemented? | Where | Notes |
|---|---|---|---|
| Sum | Yes | Throughout | Marks, counts, weights. |
| Count / distinct count | Yes | Repositories, analytics | `count_documents`, `distinct`. |
| Arithmetic mean | Yes | Admin average score, average mastery, average assessment score, average insight mastery | No weighting by recency except F-6.5. |
| Ratio / percentage | Yes | F-1.3, F-2.x, F-5.x, F-6.x | Zero-safe helpers. |
| Min / max / clamp | Yes | Mastery, experience fit, trend score, standardized score | Used for bounds, not statistics. |
| Exponential moving average | Yes | F-3.1 | Fixed learning rate. |
| Weighted mean | Yes | F-6.5 | Fixed recency weights. |
| Median | **No** | — | Not implemented anywhere. |
| Standard deviation / variance | **No** | — | Not implemented. |
| Percentile / quantile | **No** | — | Not implemented. |
| Z-score / significance test | **No** | — | Not implemented. |
| Correlation / regression | **No** | — | Only the pretrained calibrator contains fitted coefficients; no analytics regression exists. |
| Bayesian Knowledge Tracing | **No** | — | Explicitly rejected in the module docstring. |
| Item Response Theory | **No** | — | Not implemented. |
| Confidence interval | **No** | — | `confidence` is an attempt counter (F-3.2). |

---

## 12. Referenced-but-not-implemented calculations

These names appear in comments, docs or design intent. They are **not** computed, and no UI should present them as real.

| Concept | Status | Evidence |
|---|---|---|
| Composite "Placement Readiness" score (mastery + resume + semantic) | **Planned** | `knowledge_tracing_service.get_average_mastery` docstring says the full readiness score "isn't assembled until a dashboard phase needs it". No caller composes it. |
| Bayesian Knowledge Tracing | **Planned** | Module docstring explains why it is deliberately not shipped. |
| Backlog eligibility rule | **Not implemented** | `EligibilityCriteria` has only `min_cgpa`, `departments`, `batch_years`; no `backlog` field exists. |
| Confirmed offer rate / placement rate from offers | **Partial** | `AdminAnalyticsResponse` still carries `placed_students` and `placement_rate_pct`, computed from legacy `status="selected"` rows. There is no offers collection; the UI no longer shows "Placed Students". Live value is 0. |
| Median / percentile cohort comparisons | **Not implemented** | No code path. |
| Vector-database ANN search | **Not implemented** | Retrieval is exact cosine over MongoDB-stored vectors, documented as suitable for hundreds–low thousands of chunks. |
| JD embedding ingestion into RAG | **Not implemented** | `drive_service` only nulls `jd_embedding`; the ingestion hook is commented out. |
| Model retraining / fine-tuning pipeline | **Not implemented** | Only inference code and supplied artifacts exist. |
| Cross-encoder domain prefix in runtime text | **Partial** | Training pairs included `Domain: ...`; `build_resume_text` omits it because no domain field exists on `Resume`/`Drive`. |

---

## 13. Formula-to-code mapping table

| ID | Formula | File | Function / symbol | Endpoint(s) | Status |
|---|---|---|---|---|---|
| F-1.1 | Legacy status mapping | `backend/app/services/analytics_service.py` | `_effective_status`, `_LEGACY_STATUS_MAP` | `/analytics/*` | Implemented |
| F-1.2 | Status tally / reconciliation | same | `_tally`, `_tally_tpo` | `/analytics/student/me`, `/analytics/tpo`, `/analytics/admin` | Implemented |
| F-1.3 | Zero-safe rate | same | `_rate_pct` | all analytics | Implemented |
| F-1.4 | Students with applications | same + `application_repository.py` | `distinct_students` | `/analytics/admin`, `/analytics/tpo/applications` | Implemented |
| F-1.5 | Month key | `analytics_service.py` | `_month_key` | `/analytics/tpo/applications` | Implemented |
| F-1.6 | Month axis zero-fill/clamp | same | `_month_keys`, `_clamped_month_keys` | same | Implemented |
| F-1.7 | Department canonicalisation | `analytics_service.py`, `core/departments.py` | `_normalize_department` | TPO/admin analytics | Implemented |
| F-1.8 | Aggregation ordering | `analytics_service.py` | `get_tpo_application_analytics` | `/analytics/tpo/applications` | Implemented |
| F-1.9 | Drive completion rate | same | `get_tpo_analytics` | `/analytics/tpo` | Implemented |
| F-1.10 | Admin average score | `attempt_repository.py` | `submitted_score_stats` | `/analytics/admin` | Implemented |
| F-1.11 | Average mastery | `knowledge_state_repository.py` | `mastery_overview` | `/analytics/admin` | Implemented |
| F-1.12 | Legacy audit count | `analytics_service.py` | `_legacy_selected_count` | analytics payloads | Implemented |
| F-2.1 | Grading predicates | `assessment_service.py` | `_grade` | `POST .../answer` | Implemented |
| F-2.2 | Marks / negative marking | same | `submit_answer` | same | Implemented |
| F-2.3 | Attempt score % | `analytics_service.py` / `assessment_service.py` | `_attempt_score_pct`, `_finalize_attempt` | results, ranking | Implemented |
| F-2.4 | Standardized clamped score | `assessment_service.py` | `_finalize_attempt` | finish/results | Implemented |
| F-2.5 | Standardized predicate | same | `_is_standardized` | start/answer/finish | Implemented |
| F-2.6 | Pass/fail | same | `_finalize_attempt` | finish | Implemented |
| F-2.7 | Difficulty transition | same | `_adjust_difficulty` | adaptive answer | Implemented |
| F-2.8 | Violation auto-submit | same | `report_violation` | `POST .../violation` | Implemented |
| F-2.9 | Placement paper shape | `models/assessment.py` | `PLACEMENT_*` | placement generate | Implemented |
| F-2.10 | Difficulty slot allocation | `assessment_selection_service.py` | `allocate_difficulty_slots` | templates/placement | Implemented |
| F-3.1 | EMA mastery | `knowledge_tracing_service.py` | `update_mastery` | assessment answer | Implemented |
| F-3.2 | Confidence | same | `update_mastery` | assessment answer | Implemented |
| F-3.3 | Weak/strong | same | `get_weak_and_strong_topics` | internal | Implemented |
| F-3.4 | Average mastery | same | `get_average_mastery` | internal | Implemented |
| F-4.1 | Best attempt + rank | `analytics_service.py` | `get_drive_ranking` | `/analytics/tpo/drives/{id}/ranking` | Implemented |
| F-4.2 | Domain score | same | `get_student_analytics`, `_domain_scores_for_attempts` | `/analytics/student/me`, `/analytics/tpo/applications` | Implemented |
| F-4.3 | Domain attribution | same | `_section_domain_map`, `_domain_for_question` | same | Implemented |
| F-4.4 | Trend point | same | `_graded_attempt_score_pct` | `/analytics/student/me` | Implemented |
| F-4.5 | Average assessment score | same | `get_student_analytics` | `/analytics/student/me` | Implemented |
| F-5.1 | Demand % | `skill_gap_service.py` | `_build_entry` | `/analytics/tpo/skill-gaps` | Implemented |
| F-5.2 | Gap % | same | `_build_entry` | same | Implemented |
| F-5.3 | YoY growth | `market_analytics_service.py` | `_growth_pct` | market + skill gaps | Implemented |
| F-5.4 | Priority score | `skill_gap_service.py` | `_priority_score` | skill gaps | Implemented |
| F-5.5 | Priority class | same | `_priority_class` | skill gaps | Implemented |
| F-5.6 | Evidence class | same | `_classify_accuracy` | skill gaps | Implemented |
| F-5.7 | Evidence partition | same | `_build_entry` | skill gaps | Implemented |
| F-5.8 | Demonstrated % | same | `_build_entry` | skill gaps | Implemented |
| F-6.1 | Market demand % | `market_analytics_service.py` | `_pct`, `_skill_record` | `/analytics/tpo/market` | Implemented |
| F-6.2 | Market YoY | same | `_growth_pct` | same | Implemented |
| F-6.3 | Comparable window | same | `_comparison_end_month`, `_window_count` | market + skill gaps | Implemented |
| F-6.4 | Trend class | same | `_classify_trend` | market | Implemented |
| F-6.5 | Trend score | same | `_trend_score` | market | Implemented |
| F-6.6 | Entity share | same | `get_market_comparison` | `/market/comparison` | Implemented |
| F-6.7 | Tech/soft share | same | `get_market_comparison` | same | Implemented |
| F-6.8 | Summary YoY | same | `_build_response` | `/analytics/tpo/market` | Implemented |
| F-7.1 | Overall accuracy | `student_insights_service.py` | `build` | `/insights/me` | Implemented |
| F-7.2 | Focus priority | same | `_rank_skills` | `/insights/me` | Implemented |
| F-7.3 | Severity | same | `_severity` | `/insights/me` | Implemented |
| F-7.4 | Trend direction | same | `_trend_from_attempts` | `/insights/me` | Implemented |
| F-7.5 | Strength class | same | `_rank_skills` | `/insights/me` | Implemented |
| F-7.6 | Study-guide ordering | same | `_build_study_guide` | `/insights/me` | Implemented |
| F-7.7 | Narrative cache key | same | `_maybe_narrate` | `/insights/me` | Implemented |
| F-8.1 | Final match score | `matching_service.py` | `compute_final_score` | `/matching/*`, screening | Implemented |
| F-8.2 | Skills coverage | same | `_score_one_*` | `/matching/*` | Implemented |
| F-8.3 | Experience fit | same | `exp_fit` | `/matching/*` | Implemented |
| F-8.4 | Retrieve-then-rerank | same | `_retrieve_top_k`, `rank_*` | `/matching/*` | Implemented |
| F-8.5 | Screening thresholds | `screening_service.py` | `get_screening_summary`, `get_recommended_shortlist` | `/drives/{id}/screening-summary`, `/recommended-shortlist` | Implemented |
| F-8.6 | Eligibility rules | `drive_service.py`, `screening_service.py` | `_check_eligibility`, `screen_applications` | apply/screen | Implemented |
| F-9.1 | Mean pooling | `ml/matching/inference.py` | `embed_texts` | matching | Implemented |
| F-9.2 | L2 normalisation | same | `embed_texts` | matching | Implemented |
| F-9.3 | Cosine similarity | same | `cosine_similarity` | matching | Implemented |
| F-9.4 | Cross-encoder | same | `score_pairs` | matching | Implemented |
| F-9.5 | Platt calibration | same | `calibrate` | matching | Implemented |
| F-9.6 | Softmax attention | HF `BertModel` / `RobertaForSequenceClassification` | forward pass | matching | Implemented (library) |
| F-9.7 | BCE training loss | model card only | — | — | Documented, not implemented |
| F-10.1 | Chunking | `ml/rag/knowledge_store.py` | `_chunk_text` | admin knowledge, seed | Implemented |
| F-10.2 | Retrieval cosine | same | `retrieve` | explanations, insights | Implemented |
| F-10.3 | Top-K | same | `retrieve` | explanations, insights | Implemented |
| F-10.4 | Ingestion dedup | same | `delete_by_source_prefix` | admin knowledge, seed | Partial |

---

## 14. Cross-references

| Topic | Architecture diagram | System design doc |
|---|---|---|
| Collections and relationships | `PLACER_SYSTEM_ARCHITECTURE.mmd` Group B (ER) and Group C (schema) | §2 "Data stores at a glance" and §12 "MongoDB lifecycle" |
| Assessment lifecycle | Group E1 (Student workflow), Group F (AI flow) | §8 "Drive and assessment lifecycle" |
| Analytics data processing per chart | Group A (system architecture), Group E2 (TPO workflow) | §10 "Analytics data processing, chart by chart" |
| Matching and RAG | Group F (AI model architecture and inference flow) | §7 "Resume and AI pipeline" |
| API ownership and role access | Group A | §11 "Backend and API reference" |
| Deployment and health | Group A | §13 "Deployment and runtime" |
| Security and error handling | — | §14 "Error handling, security, and observability" |
| Role interfaces (pages → APIs → collections) | Group E1/E2/E3 | §3 "Interface A — Student", §4 "Interface B — TPO", §5 "Interface C — Admin" |

**Terminology used consistently across all three documents:** Applied, Under Review (= applied), Shortlisted, Rejected, Students with Applications, Monthly Application Trends, Drive Assessment, Assessment Builder. "Placed Students" and "Selected" are not user-facing stages.


