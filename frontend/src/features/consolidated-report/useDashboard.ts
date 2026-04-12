import { useQuery, useMutation, useQueryClient, UseQueryResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { getDashboard, DashboardResponse } from '../../api/dashboard';
import {
  listFailedNotifications,
  resendNotification,
  FailedNotificationsResponse,
  ResendResponse,
} from '../../api/notifications';
import { listCycles, CycleRead } from '../../api/cycles';

/**
 * Hook to fetch available cycles for page-level cycle selectors.
 *
 * @returns Query result with the list of cycles.
 */
export function useCycleSelector(): UseQueryResult<CycleRead[]> {
  return useQuery({
    queryKey: ['cycles'],
    queryFn: () => listCycles(),
    staleTime: 60_000,
  });
}

/**
 * Hook wrapping getDashboard() with 5-second polling (FCR-006).
 * Stops polling when browser tab is hidden.
 *
 * @param cycleId - The selected cycle ID, or null if none selected.
 * @param statusFilter - Optional status filter string.
 * @returns Query result with dashboard data.
 */
export function useDashboard(
  cycleId: string | null,
  statusFilter?: string,
): UseQueryResult<DashboardResponse> {
  return useQuery({
    queryKey: ['dashboard', cycleId, statusFilter],
    queryFn: () => {
      if (!cycleId) {
        // Reason: This should never be called when cycleId is null due to enabled guard
        throw new Error('No cycle selected');
      }
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      return getDashboard(cycleId, params);
    },
    enabled: !!cycleId,
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  });
}

/**
 * Hook to fetch failed notifications (FinanceAdmin only).
 *
 * @param enabled - Whether to enable the query.
 * @returns Query result with failed notification items.
 */
export function useFailedNotifications(
  enabled: boolean,
): UseQueryResult<FailedNotificationsResponse> {
  return useQuery({
    queryKey: ['failedNotifications'],
    queryFn: () => listFailedNotifications(),
    enabled,
    staleTime: 30_000,
  });
}

/**
 * Mutation hook to resend a failed notification.
 * Invalidates the failedNotifications query on success.
 *
 * @returns Mutation result for resending notifications.
 */
export function useResendNotification() {
  const queryClient = useQueryClient();
  return useMutation<
    ResendResponse,
    AxiosError,
    { notificationId: string; recipientEmail: string }
  >({
    mutationFn: ({ notificationId, recipientEmail }) =>
      resendNotification(notificationId, recipientEmail),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['failedNotifications'] });
    },
  });
}
