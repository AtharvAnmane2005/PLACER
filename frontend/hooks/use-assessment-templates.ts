import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type {
  AssessmentTemplateResponse,
  AssessmentTemplateUpsertRequest,
  TemplatePresetResponse,
  TemplateStatus,
} from "@/types/assessment";

const TEMPLATES_KEY = ["assessments", "templates"] as const;
const PRESETS_KEY = ["assessments", "templates", "presets"] as const;

export function useTemplatePresets() {
  return useQuery({
    queryKey: PRESETS_KEY,
    queryFn: async () => {
      const { data } = await apiClient.get<TemplatePresetResponse[]>("/assessments/templates/presets");
      return data;
    },
  });
}

export function useTemplates(status?: TemplateStatus) {
  return useQuery({
    queryKey: [...TEMPLATES_KEY, status ?? "all"] as const,
    queryFn: async () => {
      const { data } = await apiClient.get<AssessmentTemplateResponse[]>("/assessments/templates", {
        params: { status: status ?? undefined },
      });
      return data;
    },
  });
}

export function useTemplate(templateId: string | null) {
  return useQuery({
    queryKey: [...TEMPLATES_KEY, templateId] as const,
    queryFn: async () => {
      const { data } = await apiClient.get<AssessmentTemplateResponse>(`/assessments/templates/${templateId}`);
      return data;
    },
    enabled: Boolean(templateId),
  });
}

function useInvalidateTemplates() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY });
}

export function useCreateTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: async (payload: AssessmentTemplateUpsertRequest) => {
      const { data } = await apiClient.post<AssessmentTemplateResponse>("/assessments/templates", payload);
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useUpdateTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: async ({ id, payload }: { id: string; payload: AssessmentTemplateUpsertRequest }) => {
      const { data } = await apiClient.put<AssessmentTemplateResponse>(`/assessments/templates/${id}`, payload);
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useDuplicateTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: async (id: string) => {
      const { data } = await apiClient.post<AssessmentTemplateResponse>(`/assessments/templates/${id}/duplicate`);
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useSetTemplateStatus() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: async ({ id, status }: { id: string; status: TemplateStatus }) => {
      const { data } = await apiClient.patch<AssessmentTemplateResponse>(
        `/assessments/templates/${id}/status`,
        null,
        { params: { status } }
      );
      return data;
    },
    onSuccess: invalidate,
  });
}

export function useDeleteTemplate() {
  const invalidate = useInvalidateTemplates();
  return useMutation({
    mutationFn: async (id: string) => {
      await apiClient.delete(`/assessments/templates/${id}`);
      return id;
    },
    onSuccess: invalidate,
  });
}
