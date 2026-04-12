import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a budget cycle.
 */
const CycleReadSchema = z.object({
  id: z.string().uuid(),
  fiscal_year: z.number().int(),
  deadline: z.string(),
  reporting_currency: z.string(),
  status: z.enum(['Draft', 'Open', 'Closed']),
  opened_at: z.string().nullable(),
  closed_at: z.string().nullable(),
  reopened_at: z.string().nullable(),
});

export type CycleRead = z.infer<typeof CycleReadSchema>;

/**
 * Zod schema for filing unit info with manager check.
 */
const FilingUnitInfoReadSchema = z.object({
  org_unit_id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
  has_manager: z.boolean(),
  excluded: z.boolean(),
  warnings: z.array(z.string()),
});

export type FilingUnitInfoRead = z.infer<typeof FilingUnitInfoReadSchema>;

/**
 * Zod schema for a template generation result.
 */
const TemplateGenerationResultSchema = z.object({
  org_unit_id: z.string().uuid(),
  status: z.string(),
  error: z.string().optional(),
});

export type TemplateGenerationResult = z.infer<typeof TemplateGenerationResultSchema>;

/**
 * Zod schema for the open cycle response.
 */
const OpenCycleResponseSchema = z.object({
  cycle: CycleReadSchema,
  transition: z.string(),
  generation_summary: z.object({
    total: z.number().int(),
    generated: z.number().int(),
    errors: z.number().int(),
    error_details: z.array(TemplateGenerationResultSchema),
  }),
  dispatch_summary: z.object({
    total_recipients: z.number().int(),
    sent: z.number().int(),
    errors: z.number().int(),
  }),
});

export type OpenCycleResponse = z.infer<typeof OpenCycleResponseSchema>;

/**
 * Zod schema for a reminder schedule entry.
 */
const ReminderScheduleReadSchema = z.object({
  id: z.string().uuid(),
  cycle_id: z.string().uuid(),
  days_before: z.number().int(),
});

export type ReminderScheduleRead = z.infer<typeof ReminderScheduleReadSchema>;

/**
 * Fetches all budget cycles, optionally filtered by fiscal year or status.
 *
 * @param params - Optional query params (fiscal_year, status).
 * @returns Array of validated CycleRead objects.
 */
export async function listCycles(params?: {
  fiscal_year?: number;
  status?: string;
}): Promise<CycleRead[]> {
  const response = await apiClient.get<unknown>('/cycles', { params });
  return z.array(CycleReadSchema).parse(response.data);
}

/**
 * Fetches a single cycle by ID.
 *
 * @param cycleId - The cycle UUID.
 * @returns The validated CycleRead object.
 */
export async function getCycle(cycleId: string): Promise<CycleRead> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}`);
  return CycleReadSchema.parse(response.data);
}

/**
 * Creates a new budget cycle.
 *
 * @param data - Cycle creation payload.
 * @returns The newly created CycleRead.
 */
export async function createCycle(data: {
  fiscal_year: number;
  deadline: string;
  reporting_currency: string;
}): Promise<CycleRead> {
  const response = await apiClient.post<unknown>('/cycles', data);
  return CycleReadSchema.parse(response.data);
}

/**
 * Fetches filing units for a cycle to check manager assignments.
 *
 * @param cycleId - The cycle UUID.
 * @returns Array of filing unit info with manager flags.
 */
export async function getFilingUnits(cycleId: string): Promise<FilingUnitInfoRead[]> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/filing-units`);
  return z.array(FilingUnitInfoReadSchema).parse(response.data);
}

/**
 * Opens a cycle, triggering template generation and email dispatch.
 *
 * @param cycleId - The cycle UUID.
 * @returns The open cycle response with generation and dispatch summaries.
 */
export async function openCycle(cycleId: string): Promise<OpenCycleResponse> {
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/open`);
  return OpenCycleResponseSchema.parse(response.data);
}

/**
 * Closes a cycle, preventing further uploads.
 *
 * @param cycleId - The cycle UUID.
 * @returns The updated CycleRead.
 */
export async function closeCycle(cycleId: string): Promise<CycleRead> {
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/close`);
  return CycleReadSchema.parse(response.data);
}

/**
 * Reopens a closed cycle with a required reason.
 *
 * @param cycleId - The cycle UUID.
 * @param reason - The reason for reopening.
 * @returns The updated CycleRead.
 */
export async function reopenCycle(cycleId: string, reason: string): Promise<CycleRead> {
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/reopen`, { reason });
  return CycleReadSchema.parse(response.data);
}

/**
 * Sets the reminder schedule for a cycle.
 *
 * @param cycleId - The cycle UUID.
 * @param daysBefore - Array of positive integers for days before deadline.
 * @returns Array of updated reminder schedule entries.
 */
export async function setReminders(
  cycleId: string,
  daysBefore: number[],
): Promise<ReminderScheduleRead[]> {
  const response = await apiClient.patch<unknown>(`/cycles/${cycleId}/reminders`, {
    days_before: daysBefore,
  });
  return z.array(ReminderScheduleReadSchema).parse(response.data);
}
