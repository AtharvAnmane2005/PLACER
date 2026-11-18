import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type {
  PlacementEligibilityResponse,
  PlacementGenerationRequest,
  PlacementGenerationResponse,
  PlacementParticipationResponse,
  PlacementRevisionRequest,
} from "@/types/assessment";

export function usePlacementEligibility() {
  return useMutation({
    mutationFn: async (payload: PlacementGenerationRequest) => {
      const { data } = await apiClient.post<PlacementEligibilityResponse>(
        "/assessments/placement/eligibility",
        payload
      );
      return data;
    },
  });
}

export function useGeneratePlacementAssessment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: PlacementGenerationRequest) => {
      const { data } = await apiClient.post<PlacementGenerationResponse>(
        "/assessments/placement/generate",
        payload
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

export function useRevisePlacementAssessment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({
      assessmentId,
      payload,
    }: {
      assessmentId: string;
      payload: PlacementRevisionRequest;
    }) => {
      const { data } = await apiClient.post<PlacementGenerationResponse>(
        `/assessments/placement/${assessmentId}/revise`,
        payload
      );
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["assessments"] });
    },
  });
}

export function usePlacementParticipation(driveId: string | null, assessmentId: string | null) {
  return useQuery({
    queryKey: ["assessments", "placement", "participation", driveId, assessmentId],
    queryFn: async () => {
      const { data } = await apiClient.get<PlacementParticipationResponse>(
        `/assessments/placement/${driveId}/participation`,
        { params: { assessment_id: assessmentId } }
      );
      return data;
    },
    enabled: Boolean(driveId && assessmentId),
  });
}
