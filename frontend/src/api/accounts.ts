import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for an account.
 */
const AccountSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
  category: z.enum(['operational', 'personnel', 'shared_cost']),
  level: z.number().int(),
});

export type Account = z.infer<typeof AccountSchema>;

/**
 * Zod schema for the accounts list response.
 */
const AccountsListSchema = z.object({
  items: z.array(AccountSchema),
  total: z.number().int(),
});

export type AccountsList = z.infer<typeof AccountsListSchema>;

/**
 * Zod schema for import summary.
 */
const ImportSummarySchema = z.object({
  total_rows: z.number().int(),
  imported_rows: z.number().int(),
  errors: z.array(
    z.object({
      row: z.number().int(),
      column: z.string(),
      code: z.string(),
      reason: z.string(),
    }),
  ),
});

export type ImportSummary = z.infer<typeof ImportSummarySchema>;

/**
 * Fetches accounts, optionally filtered by category.
 *
 * @param category - Optional filter: 'operational', 'personnel', or 'shared_cost'.
 * @returns List of accounts.
 * @throws AxiosError if the request fails.
 */
export async function listAccounts(category?: string): Promise<AccountsList> {
  const response = await apiClient.get<unknown>('/accounts', {
    params: category ? { category } : {},
  });
  return AccountsListSchema.parse(response.data);
}

/**
 * Upserts an account by code. Creates if not found, updates if exists.
 *
 * @param account - Account data with code, name, category, level.
 * @returns The created or updated account.
 * @throws AxiosError if the request fails.
 */
export async function upsertAccount(account: {
  code: string;
  name: string;
  category: 'operational' | 'personnel' | 'shared_cost';
  level: number;
}): Promise<Account> {
  const response = await apiClient.post<unknown>('/accounts', account);
  return AccountSchema.parse(response.data);
}

/**
 * Imports actuals for a cycle from a CSV or XLSX file.
 *
 * @param cycleId - The cycle ID.
 * @param file - The CSV or XLSX file.
 * @returns Import summary with counts and error details.
 * @throws AxiosError if the request fails.
 */
export async function importActuals(cycleId: string, file: File): Promise<ImportSummary> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await apiClient.post<unknown>(`/cycles/${cycleId}/actuals`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return ImportSummarySchema.parse(response.data);
}
