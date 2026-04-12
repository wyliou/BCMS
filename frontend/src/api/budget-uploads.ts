import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a budget upload record.
 */
const BudgetUploadReadSchema = z.object({
  id: z.string().uuid(),
  cycle_id: z.string().uuid(),
  org_unit_id: z.string().uuid(),
  version: z.number().int(),
  uploader_id: z.string().uuid(),
  row_count: z.number().int(),
  file_size_bytes: z.number().int(),
  status: z.enum(['Pending', 'Valid', 'Invalid']),
  uploaded_at: z.string(),
});

export type BudgetUploadRead = z.infer<typeof BudgetUploadReadSchema>;

/**
 * Uploads a budget Excel file for a given cycle and org unit.
 * Sends as multipart/form-data.
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID (from auth store; never from URL).
 * @param file - The .xlsx file to upload (must be ≤10 MB).
 * @returns The created BudgetUploadRead record.
 */
export async function uploadBudget(
  cycleId: string,
  orgUnitId: string,
  file: File,
): Promise<BudgetUploadRead> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/uploads/${orgUnitId}`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return BudgetUploadReadSchema.parse(response.data);
}

/**
 * Fetches all upload versions for a given cycle and org unit.
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID.
 * @returns Array of BudgetUploadRead records (newest first from API).
 */
export async function listUploadVersions(
  cycleId: string,
  orgUnitId: string,
): Promise<BudgetUploadRead[]> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/uploads/${orgUnitId}`);
  return z.array(BudgetUploadReadSchema).parse(response.data);
}

/**
 * Fetches a single upload record by ID.
 *
 * @param uploadId - The upload UUID.
 * @returns The BudgetUploadRead record.
 */
export async function getUpload(uploadId: string): Promise<BudgetUploadRead> {
  const response = await apiClient.get<unknown>(`/uploads/${uploadId}`);
  return BudgetUploadReadSchema.parse(response.data);
}
