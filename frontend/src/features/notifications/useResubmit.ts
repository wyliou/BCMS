import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  createResubmitRequest,
  listResubmitRequests,
  ResubmitRequestRead,
  CreateResubmitRequestPayload,
} from '../../api/notifications';

/**
 * Hook wrapping createResubmitRequest mutation and listResubmitRequests query.
 * Fetches history only when the modal is open (enabled flag).
 *
 * @param cycleId - The cycle UUID.
 * @param orgUnitId - The org unit UUID.
 * @param enabled - Whether to fetch history (true when modal is open).
 * @returns Query result for request history and mutation for creating a request.
 */
export function useResubmit(cycleId: string, orgUnitId: string, enabled: boolean) {
  const queryClient = useQueryClient();

  const historyQuery = useQuery<ResubmitRequestRead[], AxiosError>({
    queryKey: ['resubmitRequests', cycleId, orgUnitId],
    queryFn: () => listResubmitRequests(cycleId, orgUnitId),
    enabled,
    staleTime: 10000,
  });

  const createMutation = useMutation<ResubmitRequestRead, AxiosError, CreateResubmitRequestPayload>(
    {
      mutationFn: (payload) => createResubmitRequest(payload),
      onSuccess: () => {
        // Invalidate dashboard so status updates to "已通知重傳"
        queryClient.invalidateQueries({ queryKey: ['dashboard', cycleId] });
        queryClient.invalidateQueries({ queryKey: ['resubmitRequests', cycleId, orgUnitId] });
      },
    },
  );

  return { historyQuery, createMutation };
}
