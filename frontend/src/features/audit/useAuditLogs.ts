import { useQuery, useMutation, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  queryAuditLogs,
  verifyChain,
  AuditLogsResponse,
  VerifyChainResponse,
} from '../../api/audit';

/**
 * Parameters for querying audit logs.
 */
export interface AuditLogsQueryParams {
  user_id?: string;
  action?: string;
  resource_type?: string;
  resource_id?: string;
  from?: string;
  to?: string;
  page?: number;
  size?: number;
}

/**
 * Hook to fetch paginated audit logs with optional filters.
 *
 * @param params - Query parameters.
 * @returns Query result with audit logs, loading, and error states.
 */
export function useAuditLogs(params: AuditLogsQueryParams): UseQueryResult<AuditLogsResponse> {
  return useQuery({
    queryKey: ['audit-logs', params],
    queryFn: () => queryAuditLogs(params),
    staleTime: 30000, // 30 seconds
  });
}

/**
 * Hook to verify the audit log chain integrity.
 *
 * @returns Mutation object for chain verification.
 */
export function useVerifyChain(): UseMutationResult<
  VerifyChainResponse,
  AxiosError,
  { from?: string; to?: string }
> {
  return useMutation({
    mutationFn: ({ from, to }) => verifyChain(from, to),
  });
}
