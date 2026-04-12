import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for a personnel import record.
 */
const PersonnelImportReadSchema = z.object({
  id: z.string().uuid(),
  cycle_id: z.string().uuid(),
  uploader_user_id: z.string().uuid(),
  uploaded_at: z.string(),
  filename: z.string(),
  file_hash: z.string(),
  version: z.number().int(),
  affected_org_units_summary: z.array(z.string()),
});

export type PersonnelImportRead = z.infer<typeof PersonnelImportReadSchema>;

/**
 * Uploads a personnel budget file (CSV or XLSX) for a given cycle.
 * Sends as multipart/form-data.
 *
 * @param cycleId - The cycle UUID.
 * @param file - The CSV or XLSX file to import.
 * @returns The created PersonnelImportRead record.
 */
export async function importPersonnel(cycleId: string, file: File): Promise<PersonnelImportRead> {
  const form = new FormData();
  form.append('file', file);
  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/personnel-imports`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return PersonnelImportReadSchema.parse(response.data);
}

/**
 * Fetches all personnel import versions for a given cycle.
 *
 * @param cycleId - The cycle UUID.
 * @returns Array of PersonnelImportRead records.
 */
export async function listPersonnelVersions(cycleId: string): Promise<PersonnelImportRead[]> {
  const response = await apiClient.get<unknown>(`/cycles/${cycleId}/personnel-imports`);
  return z.array(PersonnelImportReadSchema).parse(response.data);
}

/**
 * Fetches a single personnel import record by ID.
 *
 * @param importId - The import UUID.
 * @returns The PersonnelImportRead record.
 */
export async function getPersonnelImport(importId: string): Promise<PersonnelImportRead> {
  const response = await apiClient.get<unknown>(`/personnel-imports/${importId}`);
  return PersonnelImportReadSchema.parse(response.data);
}
