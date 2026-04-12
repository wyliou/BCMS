import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for an individual audit log entry.
 */
const AuditLogReadSchema = z.object({
  id: z.string().uuid(),
  user_id: z.string().uuid(),
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string().nullable(),
  ip_address: z.string(),
  timestamp: z.string().datetime(),
  details: z.record(z.unknown()).nullable(),
});

export type AuditLogRead = z.infer<typeof AuditLogReadSchema>;

/**
 * Zod schema for the paginated audit log response.
 */
const AuditLogsResponseSchema = z.object({
  items: z.array(AuditLogReadSchema),
  total: z.number().int(),
  page: z.number().int(),
  size: z.number().int(),
});

export type AuditLogsResponse = z.infer<typeof AuditLogsResponseSchema>;

/**
 * Zod schema for chain verification response.
 */
const VerifyChainResponseSchema = z.object({
  verified: z.boolean(),
  range: z.tuple([z.string().datetime().optional(), z.string().datetime().optional()]),
  chain_length: z.number().int(),
});

export type VerifyChainResponse = z.infer<typeof VerifyChainResponseSchema>;

/**
 * Queries audit logs with optional filters and pagination.
 *
 * @param params - Query parameters: user_id, action, resource_type, resource_id, from, to, page, size.
 * @returns Paginated list of audit log entries.
 * @throws AxiosError if the request fails (e.g., AUDIT_002 for bad params).
 */
export async function queryAuditLogs(params: {
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  from?: string;
  to?: string;
  page?: number;
  size?: number;
}): Promise<AuditLogsResponse> {
  const response = await apiClient.get<unknown>('/audit-logs', { params });
  return AuditLogsResponseSchema.parse(response.data);
}

/**
 * Verifies the integrity of the audit log chain.
 *
 * @param from - Start of date range (ISO-8601).
 * @param to - End of date range (ISO-8601).
 * @returns Chain verification result with verified status and chain length.
 * @throws AxiosError if the request fails.
 */
export async function verifyChain(from?: string, to?: string): Promise<VerifyChainResponse> {
  const response = await apiClient.get<unknown>('/audit-logs/verify', {
    params: { from, to },
  });
  return VerifyChainResponseSchema.parse(response.data);
}

/**
 * Exports audit logs as CSV for a given date range.
 *
 * @param from - Start of date range (ISO-8601).
 * @param to - End of date range (ISO-8601).
 * @returns Promise that resolves when the download completes.
 */
export async function exportAuditLogs(from?: string, to?: string): Promise<void> {
  const { downloadBlob } = await import('../lib/download');
  const params = new URLSearchParams();
  if (from) params.append('from', from);
  if (to) params.append('to', to);
  const url = `/audit-logs/export?${params.toString()}`;
  await downloadBlob(url, 'audit-log.csv');
}
