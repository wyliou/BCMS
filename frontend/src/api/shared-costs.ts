import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a shared cost upload record.
 */
const SharedCostUploadReadSchema = z.object({
  id: z.string().uuid(),
  cycle_id: z.string().uuid(),
  uploader_user_id: z.string().uuid(),
  uploaded_at: z.string(),
  filename: z.string(),
  version: z.number().int(),
  affected_org_units_summary: z.array(z.string()),
});

export type SharedCostUploadRead = z.infer<typeof SharedCostUploadReadSchema>;

/**
 * Uploads a shared cost file (CSV or XLSX) for a given cycle.
 * Sends as multipart/form-data.
 *
 * @param cycleId - The cycle UUID.
 * @param file - The CSV or XLSX file to import.
 * @returns The created SharedCostUploadRead record.
 */
export async function importSharedCosts(
  cycleId: string,
  file: File,
): Promise<SharedCostUploadRead> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/shared-cost-imports`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return SharedCostUploadReadSchema.parse(response.data);
}

/**
 * Fetches all shared cost import versions for a given cycle.
 *
 * @param cycleId - The cycle UUID.
 * @returns Array of SharedCostUploadRead records.
 */
export async function listSharedCostVersions(cycleId: string): Promise<SharedCostUploadRead[]> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/shared-cost-imports`);
  return z.array(SharedCostUploadReadSchema).parse(response.data);
}

/**
 * Fetches a single shared cost import record by upload ID.
 *
 * @param uploadId - The upload UUID.
 * @returns The SharedCostUploadRead record.
 */
export async function getSharedCostImport(uploadId: string): Promise<SharedCostUploadRead> {
  const response = await apiClient.get<unknown>(`/shared-cost-imports/${uploadId}`);
  return SharedCostUploadReadSchema.parse(response.data);
}
