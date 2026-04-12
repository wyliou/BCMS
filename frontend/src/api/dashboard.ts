import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a single dashboard item (filing unit status row).
 */
const DashboardItemSchema = z.object({
  org_unit_id: z.string(),
  org_unit_name: z.string(),
  status: z.enum(['not_downloaded', 'downloaded', 'uploaded', 'resubmit_requested']),
  last_uploaded_at: z.string().nullable(),
  version: z.number().nullable(),
  recipient_user_id: z.string(),
  recipient_email: z.string(),
});

export type DashboardItem = z.infer<typeof DashboardItemSchema>;

/**
 * Zod schema for the dashboard summary.
 */
const DashboardSummarySchema = z.object({
  total: z.number(),
  uploaded: z.number(),
  not_downloaded: z.number(),
  downloaded: z.number(),
  resubmit_requested: z.number(),
});

export type DashboardSummary = z.infer<typeof DashboardSummarySchema>;

/**
 * Zod schema for the full dashboard response.
 */
const DashboardResponseSchema = z.object({
  cycle: z.object({
    id: z.string(),
    fiscal_year: z.number(),
    deadline: z.string(),
    status: z.enum(['Open', 'Closed']),
  }),
  items: z.array(DashboardItemSchema),
  summary: DashboardSummarySchema,
  data_freshness: z.object({
    snapshot_at: z.string(),
    stale: z.boolean(),
  }),
});

export type DashboardResponse = z.infer<typeof DashboardResponseSchema>;

/**
 * Fetches the dashboard data for a given cycle.
 *
 * @param cycleId - The cycle ID.
 * @param params - Optional query parameters: status, org_unit_id, limit, offset.
 * @returns The validated dashboard response.
 */
export async function getDashboard(
  cycleId: string,
  params?: {
    status?: string;
    org_unit_id?: string;
    limit?: number;
    offset?: number;
  },
): Promise<DashboardResponse> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/dashboard`, { params });
  return DashboardResponseSchema.parse(response.data);
}
