/**
 * Canonical department list shown in every department picker.
 *
 * These are the exact labels the backend stores (see
 * `backend/app/core/departments.py`). Keeping the UI list identical to the
 * canonical values is what makes a student's profile department match a
 * drive's eligibility criteria: a drive created with "Computer Science" must
 * accept a student whose profile says "Computer Science", not "CS".
 *
 * The backend still canonicalises aliases on write and on read (for older
 * records), so a legacy value can never block an application. This list is
 * the source of truth for what the pickers offer.
 */
export const DEPARTMENTS = [
  "Computer Science",
  "Information Technology",
  "Electronics and Communication",
  "Electrical Engineering",
  "Mechanical Engineering",
  "Civil Engineering",
  "Mathematics and Computing",
  "Artificial Intelligence and Machine Learning",
  "Data Science",
  "Statistics",
] as const;

export type Department = (typeof DEPARTMENTS)[number];

/**
 * Alias -> canonical label, mirroring `backend/app/core/departments.py`.
 * Used only for client-side display/pre-checks; the backend remains the
 * authority for eligibility and storage.
 */
const DEPARTMENT_ALIASES: Record<string, Department | string> = {
  cs: "Computer Science",
  cse: "Computer Science",
  "comp sci": "Computer Science",
  compsci: "Computer Science",
  "computer sciences": "Computer Science",
  "computer science and engineering": "Computer Science",
  "computer science engineering": "Computer Science",
  "computer engineering": "Computer Science",
  it: "Information Technology",
  "information tech": "Information Technology",
  "information technology engineering": "Information Technology",
  ece: "Electronics and Communication",
  ec: "Electronics and Communication",
  electronics: "Electronics and Communication",
  "electronics and communications": "Electronics and Communication",
  "electronics and communication engineering": "Electronics and Communication",
  "electronics and telecommunication": "Electronics and Communication",
  ee: "Electrical Engineering",
  eee: "Electrical Engineering",
  electrical: "Electrical Engineering",
  "electrical and electronics engineering": "Electrical Engineering",
  me: "Mechanical Engineering",
  mech: "Mechanical Engineering",
  mechanical: "Mechanical Engineering",
  ce: "Civil Engineering",
  civil: "Civil Engineering",
  mnc: "Mathematics and Computing",
  "maths and computing": "Mathematics and Computing",
  "math and computing": "Mathematics and Computing",
  "mathematics computing": "Mathematics and Computing",
  aiml: "Artificial Intelligence and Machine Learning",
  "ai ml": "Artificial Intelligence and Machine Learning",
  "ai and ml": "Artificial Intelligence and Machine Learning",
  "artificial intelligence": "Artificial Intelligence and Machine Learning",
  ds: "Data Science",
  stats: "Statistics",
  "applied statistics": "Statistics",
};

function aliasKey(value: string): string {
  return value
    .split(/\s+/)
    .join(" ")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[.,()]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .join(" ");
}

/** Canonicalise one department value for display. Never invents a value. */
export function normalizeDepartment(value: string | null | undefined): string | null {
  const text = (value ?? "").split(/\s+/).join(" ").trim();
  if (!text) return null;
  return DEPARTMENT_ALIASES[aliasKey(text)] ?? text;
}

/**
 * Whether a student's department satisfies a drive's department criteria.
 * Mirrors the backend rule: an empty eligibility list means "open to all".
 */
export function departmentMatches(
  studentDepartment: string | null | undefined,
  eligibleDepartments: string[] | null | undefined
): boolean {
  const eligible = (eligibleDepartments ?? []).filter((value) => value && value.trim());
  if (eligible.length === 0) return true;
  const student = normalizeDepartment(studentDepartment);
  const studentRaw = (studentDepartment ?? "").split(/\s+/).join(" ").toLowerCase();
  return eligible.some((candidate) => {
    const canonical = normalizeDepartment(candidate);
    if (student && canonical && student.toLowerCase() === canonical.toLowerCase()) return true;
    const candidateRaw = candidate.split(/\s+/).join(" ").toLowerCase();
    return Boolean(studentRaw) && studentRaw === candidateRaw;
  });
}

