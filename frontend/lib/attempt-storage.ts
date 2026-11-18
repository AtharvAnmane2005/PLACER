import type { AntiCheatConfig, AssessmentFormat, QuestionStudentView } from "@/types/assessment";

export interface AttemptState {
  sessionToken: string;
  timeLimitSec: number;
  antiCheatConfig: AntiCheatConfig;
  currentQuestion: QuestionStudentView | null;
  startedAtMs: number;
  violationCount: number;

  /** Standardized attempts carry the immutable fixed set locally so students
   *  can navigate, change answers and resume without regenerating questions. */
  format?: AssessmentFormat;
  questions?: QuestionStudentView[];
  answeredQuestionIds?: string[];
  answers?: Record<string, string>;
  activeIndex?: number;
  instructions?: string;
  totalMarks?: number;
}

function key(attemptId: string): string {
  return `placer_attempt_${attemptId}`;
}

export function saveAttemptState(attemptId: string, state: AttemptState): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(key(attemptId), JSON.stringify(state));
}

export function loadAttemptState(attemptId: string): AttemptState | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(key(attemptId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AttemptState;
  } catch {
    return null;
  }
}

export function clearAttemptState(attemptId: string): void {
  if (typeof window === "undefined") return;
  window.sessionStorage.removeItem(key(attemptId));
}
