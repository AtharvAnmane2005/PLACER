import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api-client";
import type {
  AdminActivity,
  AdminAnalytics,
  AdminApplicationFiltersResponse,
  AdminApplicationQuery,
  AdminApplicationRecordsResponse,
  DriveApplicantsResponse,
  DriveAssessmentRanking,
  DriveParticipantsResponse,
  StudentAnalytics,
  TpoAnalytics,
  TpoApplicationAnalytics,
  TpoApplicationRecordsResponse,
  TpoCompanySort,
} from "@/types/analytics";

export function useTpoAnalytics() {
  return useQuery({
    queryKey: ["analytics", "tpo"],
    queryFn: async () => {
      const { data } = await apiClient.get<TpoAnalytics>("/analytics/tpo");
      return data;
    },
  });
}

/** The authenticated student's own dashboard analytics. */
export function useStudentAnalytics() {
  return useQuery({
    queryKey: ["analytics", "student", "me"],
    queryFn: async () => {
      const { data } = await apiClient.get<StudentAnalytics>("/analytics/student/me");
      return data;
    },
  });
}

export interface TpoApplicationAnalyticsParams {
  dateFrom?: string;
  dateTo?: string;
  topN?: number;
  companySort?: TpoCompanySort;
}

/**
 * Application analytics for the TPO's own drives. Every filter is part of the
 * query key so a date/sort change can never display another combination's
 * data, and `keepPreviousData` keeps the current charts visible while the
 * filtered request is in flight.
 */
export function useTpoApplicationAnalytics(params: TpoApplicationAnalyticsParams = {}) {
  const { dateFrom, dateTo, topN = 8, companySort = "applications" } = params;
  return useQuery({
    queryKey: ["analytics", "tpo", "applications", dateFrom ?? "", dateTo ?? "", topN, companySort] as const,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await apiClient.get<TpoApplicationAnalytics>("/analytics/tpo/applications", {
        params: {
          ...(dateFrom ? { date_from: dateFrom } : {}),
          ...(dateTo ? { date_to: dateTo } : {}),
          top_n: topN,
          company_sort: companySort,
        },
      });
      return data;
    },
  });
}

/**
 * Paginated application rows behind the TPO dashboard charts. Each chart
 * interaction supplies its own filter, so the list always matches the number
 * the user clicked. `enabled` lets the dashboard avoid a request until a
 * drill-down is actually opened.
 */
export interface TpoApplicationRecordsParams {
  status?: string;
  companyId?: string;
  department?: string;
  driveId?: string;
  dateFrom?: string;
  dateTo?: string;
  page?: number;
  limit?: number;
  enabled?: boolean;
}

export function useTpoApplicationRecords(params: TpoApplicationRecordsParams = {}) {
  const {
    status,
    companyId,
    department,
    driveId,
    dateFrom,
    dateTo,
    page = 1,
    limit = 20,
    enabled = true,
  } = params;
  return useQuery({
    queryKey: [
      "analytics",
      "tpo",
      "applications",
      "records",
      status ?? "",
      companyId ?? "",
      department ?? "",
      driveId ?? "",
      dateFrom ?? "",
      dateTo ?? "",
      page,
      limit,
    ] as const,
    enabled,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await apiClient.get<TpoApplicationRecordsResponse>(
        "/analytics/tpo/applications/records",
        {
          params: {
            ...(status ? { status } : {}),
            ...(companyId ? { company_id: companyId } : {}),
            ...(department ? { department } : {}),
            ...(driveId ? { drive_id: driveId } : {}),
            ...(dateFrom ? { date_from: dateFrom } : {}),
            ...(dateTo ? { date_to: dateTo } : {}),
            page,
            limit,
          },
        }
      );
      return data;
    },
  });
}

/**
 * Per-drive analytics detail (rankings / applicants / participants), shown
 * inside each drive's expanded breakdown. `enabled` keeps a closed drive
 * from issuing requests; every parameter is part of the query key so a
 * page/search change can never display another combination's results, and
 * `keepPreviousData` keeps the current list visible while the next page or
 * search result loads.
 */
export function useDriveRanking(driveId: string | null) {
  return useQuery({
    queryKey: ["analytics", "tpo", "drive", driveId, "ranking"] as const,
    enabled: Boolean(driveId),
    queryFn: async () => {
      const { data } = await apiClient.get<DriveAssessmentRanking>(
        `/analytics/tpo/drives/${driveId}/ranking`
      );
      return data;
    },
  });
}

export function useDriveApplicants(driveId: string | null, page: number, search: string) {
  const trimmed = search.trim();
  return useQuery({
    queryKey: ["analytics", "tpo", "drive", driveId, "applicants", page, trimmed] as const,
    enabled: Boolean(driveId),
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await apiClient.get<DriveApplicantsResponse>(
        `/analytics/tpo/drives/${driveId}/applicants`,
        { params: { page, limit: 20, ...(trimmed ? { search: trimmed } : {}) } }
      );
      return data;
    },
  });
}

export function useDriveParticipants(driveId: string | null, page: number, search: string) {
  const trimmed = search.trim();
  return useQuery({
    queryKey: ["analytics", "tpo", "drive", driveId, "participants", page, trimmed] as const,
    enabled: Boolean(driveId),
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await apiClient.get<DriveParticipantsResponse>(
        `/analytics/tpo/drives/${driveId}/participants`,
        { params: { page, limit: 20, ...(trimmed ? { search: trimmed } : {}) } }
      );
      return data;
    },
  });
}

export function useAdminAnalytics() {
  return useQuery({
    queryKey: ["analytics", "admin"],
    queryFn: async () => {
      const { data } = await apiClient.get<AdminAnalytics>("/analytics/admin");
      return data;
    },
  });
}

/** System-wide user distribution, departments and monthly activity. */
export function useAdminActivity() {
  return useQuery({
    queryKey: ["analytics", "admin", "activity"],
    queryFn: async () => {
      const { data } = await apiClient.get<AdminActivity>("/analytics/admin/activity");
      return data;
    },
  });
}

/**
 * Cross-drive application workspace for admins. Every filter is part of the
 * query key, so changing a filter can never show another combination's rows,
 * and `keepPreviousData` keeps the table stable while the next page loads.
 */
export function useAdminApplications(params: AdminApplicationQuery = {}) {
  const {
    status,
    company_id,
    drive_id,
    department,
    assessment_completion = "all",
    date_from,
    date_to,
    page = 1,
    limit = 20,
  } = params;
  return useQuery({
    queryKey: [
      "analytics",
      "admin",
      "applications",
      status ?? "",
      company_id ?? "",
      drive_id ?? "",
      department ?? "",
      assessment_completion,
      date_from ?? "",
      date_to ?? "",
      page,
      limit,
    ] as const,
    placeholderData: keepPreviousData,
    queryFn: async () => {
      const { data } = await apiClient.get<AdminApplicationRecordsResponse>(
        "/analytics/admin/applications",
        {
          params: {
            ...(status ? { status } : {}),
            ...(company_id ? { company_id } : {}),
            ...(drive_id ? { drive_id } : {}),
            ...(department ? { department } : {}),
            assessment_completion,
            ...(date_from ? { date_from } : {}),
            ...(date_to ? { date_to } : {}),
            page,
            limit,
          },
        }
      );
      return data;
    },
  });
}

/** Live company / drive / department options for the admin workspace. */
export function useAdminApplicationFilters() {
  return useQuery({
    queryKey: ["analytics", "admin", "applications", "filters"] as const,
    queryFn: async () => {
      const { data } = await apiClient.get<AdminApplicationFiltersResponse>(
        "/analytics/admin/applications/filters"
      );
      return data;
    },
  });
}
