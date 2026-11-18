/**
 * Full status split as stored, including legacy `selected` outcomes.
 * `selected` is audit-only: the backend maps it into `shortlisted` at read
 * time, and no chart, filter or rate in the current UI displays it.
 */
export interface ApplicationStatusBreakdown {
  applied: number;
  shortlisted: number;
  rejected: number;
  selected: number;
}

/**
 * The three statuses a TPO actually manages.
 * `selected` is deliberately absent: the current TPO workflow ends at
 * shortlist/reject, so no TPO chart, legend, filter or rate shows it.
 */
export interface TpoApplicationStatusBreakdown {
  applied: number;
  shortlisted: number;
  rejected: number;
}

export interface DriveFunnel {
  drive_id: string;
  job_title: string;
  company_name: string;
  status: string;
  total_applications: number;
  breakdown: TpoApplicationStatusBreakdown;
  /** Assessment linkage + per-drive participation (backend-computed). */
  required_assessment_id: string | null;
  assessment_title: string | null;
  /** Unique students who started the drive assessment. */
  participant_count: number;
  /** Unique students with a submitted attempt. */
  submitted_participant_count: number;
  /** Eligible applications (one per student) — completion denominator. */
  eligible_application_count: number;
  /** submitted participants / eligible applications, zero-safe. */
  completion_rate_pct: number;
}

export interface DriveAssessmentRankingEntry {
  rank: number;
  student_id: string;
  student_name: string;
  department: string | null;
  cgpa: number | null;
  score_pct: number;
  submitted_at: string;
  /** True for flagged demo data — the UI must mark it. */
  is_synthetic?: boolean;
}

export interface DriveAssessmentRanking {
  drive_id: string;
  job_title: string;
  company_name: string;
  assessment_id: string;
  assessment_title: string;
  entries: DriveAssessmentRankingEntry[];
}

export interface TpoAnalytics {
  total_drives: number;
  open_drives: number;
  closed_drives: number;
  total_applications: number;
  breakdown: TpoApplicationStatusBreakdown;
  drives: DriveFunnel[];
  /** Applications in this view flagged synthetic (demo seed data). */
  synthetic_application_count: number;
}

export interface DriveApplicantEntry {
  application_id: string;
  student_id: string;
  student_name: string;
  department: string | null;
  batch_year: number | null;
  /** Application status: applied | shortlisted | rejected | selected (legacy). */
  status: string;
  applied_at: string;
  is_synthetic?: boolean;
}

export interface DriveApplicantsResponse {
  drive_id: string;
  job_title: string;
  company_name: string;
  total: number;
  page: number;
  limit: number;
  entries: DriveApplicantEntry[];
}

export interface DriveParticipantEntry {
  student_id: string;
  student_name: string;
  department: string | null;
  batch_year: number | null;
  attempt_id: string;
  /** "in_progress" | "submitted" — one row per student, best attempt shown. */
  attempt_status: string;
  /** null for an in-progress attempt. */
  score_pct: number | null;
  started_at: string;
  submitted_at: string | null;
  is_synthetic?: boolean;
}

export interface DriveParticipantsResponse {
  drive_id: string;
  job_title: string;
  company_name: string;
  assessment_id: string | null;
  assessment_title: string | null;
  total: number;
  page: number;
  limit: number;
  entries: DriveParticipantEntry[];
}

export interface SkillMasteryOverview {
  skill_tag: string;
  avg_mastery_pct: number;
  student_count: number;
}

export type UserRole = "student" | "tpo" | "admin";

export interface AdminUserRoleCount {
  role: UserRole;
  count: number;
}

export interface AdminDepartmentStudentCount {
  department: string;
  count: number;
}

export interface AdminActivityMonthPoint {
  /** "YYYY-MM" */
  month: string;
  new_students: number;
  new_drives: number;
  applications: number;
}

export interface AdminActivity {
  user_distribution: AdminUserRoleCount[];
  total_users: number;
  department_student_counts: AdminDepartmentStudentCount[];
  monthly_activity: AdminActivityMonthPoint[];
}

export interface AdminAnalytics {
  total_students: number;
  total_tpos: number;
  total_drives: number;
  open_drives: number;
  closed_drives: number;
  total_applications: number;
  /** Distinct students across all applications, not application rows. */
  unique_applicants: number;
  /** User-facing name for `unique_applicants`. */
  students_with_applications: number;
  /** Companies with at least one drive. */
  total_companies: number;
  application_breakdown: ApplicationStatusBreakdown;
  /** Audit-only: legacy `selected` rows mapped into `shortlisted` at read time. */
  legacy_selected: number;
  placed_students: number;
  placement_rate_pct: number;
  total_categories: number;
  total_questions: number;
  total_assessments: number;
  total_attempts: number;
  submitted_attempts: number;
  average_score_pct: number | null;
  skill_mastery_overview: SkillMasteryOverview[];
  /** Additive dashboard fields. */
  total_admins: number;
  user_role_counts: AdminUserRoleCount[];
  department_student_counts: AdminDepartmentStudentCount[];
  /** Provenance counts for the demo-data disclosure banner. */
  synthetic_students: number;
  synthetic_applications: number;
}

// ---------------------------------------------------------------------------
// Role-specific dashboard analytics
// ---------------------------------------------------------------------------

export interface StudentApplicationStatusCounts {
  applied: number;
  shortlisted: number;
  rejected: number;
  selected: number;
}

export interface StudentDomainScore {
  domain: string;
  /** Difficulty-weighted marks / maximum marks, 0-100. */
  score_pct: number;
  correct: number;
  answered: number;
}

export interface StudentAssessmentTrendPoint {
  attempt_id: string;
  assessment_id: string;
  assessment_title: string;
  submitted_at: string;
  score_pct: number;
  correct: number;
  answered: number;
}

export interface StudentAnalytics {
  applications: StudentApplicationStatusCounts;
  total_applications: number;
  /** All rates use `total_applications` as the denominator; zero-safe. */
  applied_rate_pct: number;
  shortlisting_rate_pct: number;
  rejection_rate_pct: number;
  domain_scores: StudentDomainScore[];
  assessment_trend: StudentAssessmentTrendPoint[];
  submitted_attempt_count: number;
  /** Mean of graded submitted attempts; null when there is no graded attempt. */
  average_score_pct: number | null;
  /** Audit-only: legacy `selected` rows mapped into `shortlisted`. */
  legacy_selected: number;
}

export interface TpoDepartmentStatusCounts {
  department: string;
  applied: number;
  shortlisted: number;
  rejected: number;
  total: number;
}

export interface TpoMonthlyApplicationPoint {
  /** "YYYY-MM" */
  month: string;
  applied: number;
  shortlisted: number;
  rejected: number;
  total: number;
}

export interface TpoCompanyApplicationCounts {
  company_id: string | null;
  company_name: string;
  applied: number;
  shortlisted: number;
  rejected: number;
  total: number;
}

export type TpoCompanySort = "applications" | "shortlisted" | "name";

export interface TpoDriveApplicationCounts {
  drive_id: string;
  job_title: string;
  company_id: string | null;
  company_name: string;
  drive_status: string;
  applied: number;
  shortlisted: number;
  rejected: number;
  total: number;
}

export interface TpoApplicationAnalytics {
  total_applications: number;
  total_drives: number;
  date_from: string | null;
  date_to: string | null;
  status_breakdown: TpoApplicationStatusBreakdown;
  /** Distinct students, not application rows. */
  unique_applicants: number;
  /** User-facing name for `unique_applicants`. */
  students_with_applications: number;
  /** Distinct applicants in this view (dashboard KPI). */
  total_students: number;
  /** Currently open drives owned by this TPO (not date-filtered). */
  active_drives: number;
  /** Audit-only: legacy `selected` rows mapped into `shortlisted`. */
  legacy_selected: number;
  /** Applications in this view flagged synthetic (demo seed data). */
  synthetic_application_count: number;
  applied_rate_pct: number;
  shortlisting_rate_pct: number;
  rejection_rate_pct: number;
  departments: TpoDepartmentStatusCounts[];
  monthly_trend: TpoMonthlyApplicationPoint[];
  companies: TpoCompanyApplicationCounts[];
  /** Distinct companies BEFORE Top-N truncation. */
  company_count: number;
  company_sort: TpoCompanySort;
  top_n: number;
  /** Only drives that received an application in this view. */
  drives: TpoDriveApplicationCounts[];
  drive_count: number;
  /** Aggregate radar from real graded answers; empty when no evidence. */
  domain_scores: StudentDomainScore[];
}

export interface TpoApplicationRecordEntry {
  application_id: string;
  student_id: string;
  student_name: string;
  department: string | null;
  drive_id: string;
  job_title: string;
  company_id: string | null;
  company_name: string;
  status: string;
  applied_at: string;
  is_synthetic?: boolean;
}

export interface TpoApplicationRecordsResponse {
  total: number;
  page: number;
  limit: number;
  entries: TpoApplicationRecordEntry[];
}

// ---------------------------------------------------------------------------
// Admin applications workspace
// ---------------------------------------------------------------------------

/** Status cards computed over every filter EXCEPT the status filter. */
export interface AdminApplicationSummary {
  total: number;
  applied: number;
  shortlisted: number;
  rejected: number;
  /** Audit-only: legacy `selected` rows mapped into `shortlisted`. */
  legacy_selected: number;
}

export interface AdminApplicationEntry {
  application_id: string;
  student_id: string;
  student_name: string;
  department: string | null;
  company_id: string | null;
  company_name: string;
  drive_id: string;
  job_title: string;
  assessment_id: string | null;
  assessment_title: string | null;
  assessment_status: string;
  assessment_score_pct: number | null;
  /** Standing in the drive's required assessment; null without a submission. */
  rank: number | null;
  status: string;
  applied_at: string;
  is_synthetic?: boolean;
}

export interface AdminApplicationRecordsResponse {
  total: number;
  page: number;
  limit: number;
  summary: AdminApplicationSummary;
  entries: AdminApplicationEntry[];
}

export interface AdminApplicationFilterCompany {
  id: string;
  name: string;
}

export interface AdminApplicationFilterDrive {
  id: string;
  job_title: string;
  company_name: string;
  status: string;
}

export interface AdminApplicationFiltersResponse {
  companies: AdminApplicationFilterCompany[];
  drives: AdminApplicationFilterDrive[];
  departments: string[];
}

export type AdminAssessmentCompletionFilter =
  | "all"
  | "completed"
  | "pending"
  | "not_required";

export interface AdminApplicationQuery {
  status?: "applied" | "shortlisted" | "rejected";
  company_id?: string;
  drive_id?: string;
  department?: string;
  assessment_completion?: AdminAssessmentCompletionFilter;
  date_from?: string;
  date_to?: string;
  page?: number;
  limit?: number;
}
