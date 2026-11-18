import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type {
  CategoryCreateRequest,
  CategoryResponse,
  ImportCommitResponse,
  ImportPreviewResponse,
  QuestionAdminResponse,
  QuestionCreateRequest,
  QuestionFilters,
  QuestionStatsResponse,
  QuestionUpdateRequest,
} from "@/types/question";

const CATEGORIES_KEY = ["admin", "categories"] as const;
const QUESTIONS_KEY = (filters: QuestionFilters) =>
  ["admin", "questions", JSON.stringify(filters ?? {})] as const;
const STATS_KEY = ["admin", "questions", "stats"] as const;

function normalizeFilters(filters?: QuestionFilters | string, difficulty?: string): QuestionFilters {
  if (typeof filters === "string") {
    return { category_id: filters, difficulty };
  }
  return filters ?? {};
}

/** Download an authenticated backend response as a browser file. */
async function downloadFile(path: string, params: Record<string, unknown> | undefined, filename: string) {
  const { data } = await apiClient.get<Blob>(path, { params, responseType: "blob" });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function useCategories() {
  return useQuery({
    queryKey: CATEGORIES_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<CategoryResponse[]>("/questions/categories");
      return data;
    },
  });
}

export function useCreateCategory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CategoryCreateRequest) => {
      const { data } = await apiClient.post<CategoryResponse>("/questions/categories", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: CATEGORIES_KEY });
    },
  });
}

export function useQuestions(filters?: QuestionFilters | string, difficulty?: string) {
  const normalized = normalizeFilters(filters, difficulty);
  return useQuery({
    queryKey: QUESTIONS_KEY(normalized),
    queryFn: async () => {
      const params = Object.fromEntries(
        Object.entries(normalized).filter(([, value]) => value !== undefined && value !== "")
      );
      const { data } = await apiClient.get<QuestionAdminResponse[]>("/questions", { params });
      return data;
    },
  });
}

export function useQuestionStats() {
  return useQuery({
    queryKey: STATS_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<QuestionStatsResponse>("/questions/stats");
      return data;
    },
  });
}

function invalidateAllQuestionLists(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["admin", "questions"] });
}

export function useCreateQuestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: QuestionCreateRequest) => {
      const { data } = await apiClient.post<QuestionAdminResponse>("/questions", payload);
      return data;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export function useUpdateQuestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: QuestionUpdateRequest }) => {
      const { data } = await apiClient.put<QuestionAdminResponse>(`/questions/${id}`, payload);
      return data;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export function useSetQuestionStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: "active" | "inactive" }) => {
      const { data } = await apiClient.patch<QuestionAdminResponse>(`/questions/${id}/status`, null, {
        params: { status },
      });
      return data;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export function useDeleteQuestion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/questions/${id}`);
      return id;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export function useImportQuestions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: QuestionCreateRequest[]) => {
      const { data } = await apiClient.post<QuestionAdminResponse[]>("/questions/import", payload);
      return data;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export function usePreviewQuestionImport() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const { data } = await apiClient.post<ImportPreviewResponse>("/questions/import/preview", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      return data;
    },
  });
}

export function useCommitQuestionImport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (questions: QuestionCreateRequest[]) => {
      const { data } = await apiClient.post<ImportCommitResponse>("/questions/import/commit", { questions });
      return data;
    },
    onSuccess: () => invalidateAllQuestionLists(queryClient),
  });
}

export async function exportQuestions(categoryId?: string, difficulty?: string): Promise<QuestionAdminResponse[]> {
  const { data } = await apiClient.get<QuestionAdminResponse[]>("/questions/export", {
    params: { category_id: categoryId || undefined, difficulty: difficulty || undefined },
  });
  return data;
}

export function downloadQuestionTemplate() {
  return downloadFile("/questions/export/template", undefined, "placer-question-import-template.xlsx");
}

export function downloadQuestionWorkbook(filters: QuestionFilters = {}) {
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && value !== "")
  );
  return downloadFile("/questions/export/excel", params, "placer-question-bank.xlsx");
}

export async function downloadImportErrorReport(preview: ImportPreviewResponse) {
  const { data } = await apiClient.post<Blob>("/questions/import/error-report", preview, {
    responseType: "blob",
  });
  const url = URL.createObjectURL(data);
  const link = document.createElement("a");
  link.href = url;
  link.download = "question-import-errors.csv";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
