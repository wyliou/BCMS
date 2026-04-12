import { useQuery, useMutation, UseQueryResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  getConsolidatedReport,
  startExport,
  ConsolidatedReport,
  ExportResponse,
} from '../../api/reports';

/**
 * Hook wrapping getConsolidatedReport() with 1-minute staleTime.
 * Data does not auto-refresh; user triggers manually via refetch().
 *
 * @param cycleId - The selected cycle ID, or null if none selected.
 * @returns Query result with the consolidated report data.
 */
export function useConsolidatedReport(cycleId: string | null): UseQueryResult<ConsolidatedReport> {
  return useQuery({
    queryKey: ['consolidated-report', cycleId],
    queryFn: () => {
      if (!cycleId) {
        throw new Error('No cycle selected');
      }
      return getConsolidatedReport(cycleId);
    },
    enabled: !!cycleId,
    staleTime: 60_000,
  });
}

/**
 * Mutation hook to start a report export.
 *
 * @returns Mutation result for triggering exports.
 */
export function useStartExport() {
  return useMutation<ExportResponse, AxiosError, { cycleId: string; format: 'xlsx' | 'csv' }>({
    mutationFn: ({ cycleId, format }) => startExport(cycleId, format),
  });
}
