import { z } from 'zod';
import { apiClient } from './client';
import { downloadBlob } from '../lib/download';

/**
 * Zod schema for template generation result.
 */
const TemplateGenerationResultSchema = z.object({
  org_unit_id: z.string().uuid(),
  status: z.string(),
  error: z.string().optional(),
});

export type TemplateGenerationResult = z.infer<typeof TemplateGenerationResultSchema>;

/**
 * Downloads the budget template for a given cycle and org unit.
 * Triggers a browser file save via downloadBlob.
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID.
 * @param filename - Optional filename override.
 */
export async function downloadTemplate(
  cycleId: string,
  orgUnitId: string,
  filename = 'budget-template.xlsx',
): Promise<void> {
  const url = `/cycles/${cycleId}/templates/${orgUnitId}/download`;
  await downloadBlob(url, filename);
}

/**
 * Regenerates the budget template for a specific org unit within a cycle.
 * Used to retry failed template generation after opening a cycle.
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID.
 * @returns The template generation result for the unit.
 */
export async function regenerateTemplate(
  cycleId: string,
  orgUnitId: string,
): Promise<TemplateGenerationResult> {
  const response = await apiClient.post<unknown>(
    `/cycles/${cycleId}/templates/${orgUnitId}/regenerate`,
  );
  return TemplateGenerationResultSchema.parse(response.data);
}
