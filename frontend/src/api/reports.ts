import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a consolidated report row.
 */
const ConsolidatedReportRowSchema = z.object({
  org_unit_id: z.string(),
  org_unit_name: z.string(),
  account_code: z.string(),
  account_name: z.string(),
  actual: z.string().nullable(),
  operational_budget: z.string().nullable(),
  personnel_budget: z.string().nullable(),
  shared_cost: z.string().nullable(),
  delta_amount: z.string().nullable(),
  delta_pct: z.string(),
  budget_status: z.enum(['uploaded', 'not_uploaded', 'resubmit_requested']),
});

export type ConsolidatedReportRow = z.infer<typeof ConsolidatedReportRowSchema>;

/**
 * Zod schema for the full consolidated report response.
 */
const ConsolidatedReportSchema = z.object({
  cycle_id: z.string(),
  rows: z.array(ConsolidatedReportRowSchema),
  reporting_currency: z.string(),
  budget_last_updated_at: z.string().nullable(),
  personnel_last_updated_at: z.string().nullable(),
  shared_cost_last_updated_at: z.string().nullable(),
});

export type ConsolidatedReport = z.infer<typeof ConsolidatedReportSchema>;

/**
 * Zod schema for the sync export response (201).
 */
const SyncExportResponseSchema = z.object({
  mode: z.literal('sync'),
  file_url: z.string(),
  expires_at: z.string(),
});

/**
 * Zod schema for the async export response (202).
 */
const AsyncExportResponseSchema = z.object({
  mode: z.literal('async'),
  job_id: z.string(),
});

/**
 * Union schema for the export response.
 */
const ExportResponseSchema = z.discriminatedUnion('mode', [
  SyncExportResponseSchema,
  AsyncExportResponseSchema,
]);

export type ExportResponse = z.infer<typeof ExportResponseSchema>;

/**
 * Fetches the consolidated report for a cycle.
 *
 * @param cycleId - The cycle ID.
 * @returns The consolidated report data.
 */
export async function getConsolidatedReport(cycleId: string): Promise<ConsolidatedReport> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/reports/consolidated`);
  return ConsolidatedReportSchema.parse(response.data);
}

/**
 * Starts a report export job.
 *
 * @param cycleId - The cycle ID.
 * @param format - The export format: 'xlsx' or 'csv'.
 * @returns Sync (201) or async (202) export response.
 */
export async function startExport(
  cycleId: string,
  format: 'xlsx' | 'csv',
): Promise<ExportResponse> {
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/reports/exports`, null, {
    params: { format },
  });
  return ExportResponseSchema.parse(response.data);
}
