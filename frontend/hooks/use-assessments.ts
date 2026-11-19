import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type {
  AssessmentResponse,
  AttemptQuestionsResponse,
  AttemptResultResponse,
  AttemptReviewResponse,
  CodeRunSummary,
  FinishAttemptResponse,
  KnowledgeStateResponse,
  ManualGradeResponse,
  PendingReviewItem,
  StartAttemptResponse,
  StudentInsightsResponse,
  SubmitAnswerResponse,
  ViolationReportResponse,
} from "@/types/assessment";

export function useAssessments() {
  return useQuery({
    queryKey: ["assessments"],
    queryFn: async () => {
      const { data } = await apiClient.get<AssessmentResponse[]>("/assessments");
      return data;
    },
  });
}

/** Cross-attempt focus areas + study guide for the logged-in student. */
export function useStudentInsights() {
  return useQuery({
    queryKey: ["insights", "me"],
    queryFn: async () => {
      const { data } = await apiClient.get<StudentInsightsResponse>("/insights/me");
      return data;
    },
  });
}

export function useKnowledgeStates() {
  return useQuery({
    queryKey: ["assessments", "knowledge-states", "me"],
    queryFn: async () => {
      const { data } = await apiClient.get<KnowledgeStateResponse[]>("/assessments/knowledge-states/me");
      return data;
    },
  });
}

/** TPO/admin view of a specific student's mastery — used from the applicant-review page. */
export function useStudentKnowledgeStates(studentId: string | null) {
  return useQuery({
    queryKey: ["assessments", "knowledge-states", studentId],
    queryFn: async () => {
      const { data } = await apiClient.get<KnowledgeStateResponse[]>(`/assessments/knowledge-states/${studentId}`);
      return data;
    },
    enabled: Boolean(studentId),
  });
}

/** Reload a standardized attempt's student-safe fixed question set. */
export function useAttemptQuestions(attemptId: string | null) {
  return useQuery({
    queryKey: ["assessments", "attempts", attemptId, "questions"],
    queryFn: async () => {
      const { data } = await apiClient.get<AttemptQuestionsResponse>(
        `/assessments/attempts/${attemptId}/questions`
      );
      return data;
    },
    enabled: Boolean(attemptId),
  });
}

export function useAttemptResults(attemptId: string | null) {
  return useQuery({
    queryKey: ["assessments", "attempts", attemptId, "results"],
    queryFn: async () => {
      const { data } = await apiClient.get<AttemptResultResponse>(`/assessments/attempts/${attemptId}/results`);
      return data;
    },
    enabled: Boolean(attemptId),
  });
}

/**
 * The rest of the attempt flow (start -> answer -> answer -> ... -> submit)
 * is inherently sequential, stateful, per-session data, not something that
 * benefits from react-query's caching model — the take-assessment page
 * keeps that state locally and just uses these as plain mutation wrappers.
 */
export function useStartAssessment() {
  return useMutation({
    mutationFn: async ({
      assessmentId,
      fingerprintHash,
      applicationId,
    }: {
      assessmentId: string;
      fingerprintHash?: string;
      applicationId?: string;
    }) => {
      const { data } = await apiClient.post<StartAttemptResponse>(`/assessments/${assessmentId}/start`, {
        fingerprint_hash: fingerprintHash ?? null,
        application_id: applicationId ?? null,
      });
      return data;
    },
  });
}

export function useSubmitAnswer() {
  return useMutation({
    mutationFn: async (payload: {
      attemptId: string;
      sessionToken: string;
      questionId: string;
      response: string;
      timeTakenSec?: number;
    }) => {
      const { data } = await apiClient.post<SubmitAnswerResponse>(`/assessments/attempts/${payload.attemptId}/answer`, {
        session_token: payload.sessionToken,
        question_id: payload.questionId,
        response: payload.response,
        time_taken_sec: payload.timeTakenSec ?? null,
      });
      return data;
    },
  });
}

/** Finalize an in-progress attempt early, using the answers submitted so far. */
export function useFinishAssessment() {
  return useMutation({
    mutationFn: async (payload: { attemptId: string; sessionToken: string }) => {
      const { data } = await apiClient.post<FinishAttemptResponse>(
        `/assessments/attempts/${payload.attemptId}/finish`,
        { session_token: payload.sessionToken }
      );
      return data;
    },
  });
}

export function useReportViolation() {
  return useMutation({
    mutationFn: async (payload: {
      attemptId: string;
      sessionToken: string;
      type: string;
      metadata?: Record<string, unknown>;
    }) => {
      const { data } = await apiClient.post<ViolationReportResponse>(
        `/assessments/attempts/${payload.attemptId}/violation`,
        {
          session_token: payload.sessionToken,
          type: payload.type,
          metadata: payload.metadata ?? {},
        }
      );
      return data;
    },
  });
}

/** Run the current coding question against its visible sample test cases. */
export function useRunCode() {
  return useMutation({
    mutationFn: async (payload: {
      attemptId: string;
      sessionToken: string;
      questionId: string;
      code: string;
    }) => {
      const { data } = await apiClient.post<{ code_result: CodeRunSummary }>(
        `/assessments/attempts/${payload.attemptId}/run-code`,
        {
          session_token: payload.sessionToken,
          question_id: payload.questionId,
          code: payload.code,
        }
      );
      return data.code_result;
    },
  });
}

// ---------------------------------------------------------------------------
// Manual review of descriptive answers (TPO/admin)
// ---------------------------------------------------------------------------
export function usePendingReviews() {
  return useQuery({
    queryKey: ["assessments", "review", "pending"],
    queryFn: async () => {
      const { data } = await apiClient.get<PendingReviewItem[]>("/assessments/review/pending");
      return data;
    },
  });
}

export function useAttemptReview(attemptId: string | null) {
  return useQuery({
    queryKey: ["assessments", "attempts", attemptId, "review"],
    queryFn: async () => {
      const { data } = await apiClient.get<AttemptReviewResponse>(
        `/assessments/attempts/${attemptId}/review`
      );
      return data;
    },
    enabled: Boolean(attemptId),
  });
}

export function useGradeDescriptive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      attemptId: string;
      questionId: string;
      marksAwarded: number;
      feedback?: string;
    }) => {
      const { data } = await apiClient.post<ManualGradeResponse>(
        `/assessments/attempts/${payload.attemptId}/grade`,
        {
          question_id: payload.questionId,
          marks_awarded: payload.marksAwarded,
          feedback: payload.feedback ?? null,
        }
      );
      return data;
    },
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["assessments", "review", "pending"] });
      queryClient.invalidateQueries({
        queryKey: ["assessments", "attempts", variables.attemptId, "review"],
      });
      queryClient.invalidateQueries({
        queryKey: ["assessments", "attempts", variables.attemptId, "results"],
      });
    },
  });
}
