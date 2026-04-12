import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  listCycles,
  getCycle,
  createCycle,
  openCycle,
  closeCycle,
  reopenCycle,
  setReminders,
  getFilingUnits,
  CycleRead,
  FilingUnitInfoRead,
  OpenCycleResponse,
  ReminderScheduleRead,
} from '../../api/cycles';
import { regenerateTemplate } from '../../api/templates';

/**
 * Hook to fetch all budget cycles.
 *
 * @param params - Optional filter params (fiscal_year, status).
 * @returns TanStack Query result for cycle list.
 */
export function useCycleList(params?: { fiscal_year?: number; status?: string }) {
  return useQuery<CycleRead[], AxiosError>({
    queryKey: ['cycles', params],
    queryFn: () => listCycles(params),
    staleTime: 30000,
  });
}

/**
 * Hook to fetch filing units for a specific cycle (for pre-open check).
 *
 * @param cycleId - The cycle UUID. Pass null to disable the query.
 * @returns TanStack Query result for filing unit list.
 */
export function useFilingUnits(cycleId: string | null) {
  return useQuery<FilingUnitInfoRead[], AxiosError>({
    queryKey: ['filingUnits', cycleId],
    queryFn: () => getFilingUnits(cycleId!),
    enabled: cycleId !== null,
    staleTime: 30000,
  });
}

/**
 * Hook for creating a new budget cycle.
 *
 * @returns Mutation object for cycle creation. Invalidates ['cycles'] on success.
 */
export function useCreateCycle() {
  const queryClient = useQueryClient();
  return useMutation<
    CycleRead,
    AxiosError,
    { fiscal_year: number; deadline: string; reporting_currency: string }
  >({
    mutationFn: (data) => createCycle(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
    },
  });
}

/**
 * Hook for opening a cycle. Triggers template generation and email dispatch.
 *
 * @returns Mutation object for opening a cycle. Invalidates the cycle on success.
 */
export function useOpenCycle() {
  const queryClient = useQueryClient();
  return useMutation<OpenCycleResponse, AxiosError, string>({
    mutationFn: (cycleId) => openCycle(cycleId),
    onSuccess: (_data, cycleId) => {
      queryClient.invalidateQueries({ queryKey: ['cycles', cycleId] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
    },
  });
}

/**
 * Hook for closing a cycle.
 *
 * @returns Mutation object for closing a cycle. Invalidates the cycle on success.
 */
export function useCloseCycle() {
  const queryClient = useQueryClient();
  return useMutation<CycleRead, AxiosError, string>({
    mutationFn: (cycleId) => closeCycle(cycleId),
    onSuccess: (_data, cycleId) => {
      queryClient.invalidateQueries({ queryKey: ['cycles', cycleId] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
    },
  });
}

/**
 * Hook for reopening a closed cycle (SystemAdmin only).
 *
 * @returns Mutation object for reopening a cycle. Invalidates the cycle on success.
 */
export function useReopenCycle() {
  const queryClient = useQueryClient();
  return useMutation<CycleRead, AxiosError, { cycleId: string; reason: string }>({
    mutationFn: ({ cycleId, reason }) => reopenCycle(cycleId, reason),
    onSuccess: (_data, { cycleId }) => {
      queryClient.invalidateQueries({ queryKey: ['cycles', cycleId] });
      queryClient.invalidateQueries({ queryKey: ['cycles'] });
    },
  });
}

/**
 * Hook for setting the reminder schedule of a cycle.
 *
 * @returns Mutation object for setting reminders. Invalidates reminder queries on success.
 */
export function useSetReminders() {
  const queryClient = useQueryClient();
  return useMutation<ReminderScheduleRead[], AxiosError, { cycleId: string; daysBefore: number[] }>(
    {
      mutationFn: ({ cycleId, daysBefore }) => setReminders(cycleId, daysBefore),
      onSuccess: (_data, { cycleId }) => {
        queryClient.invalidateQueries({ queryKey: ['reminders', cycleId] });
      },
    },
  );
}

/**
 * Hook for regenerating a template for a specific org unit.
 * Does not invalidate any queries; caller updates local state directly.
 *
 * @returns Mutation object for template regeneration.
 */
export function useRegenerateTemplate() {
  return useMutation<
    { org_unit_id: string; status: string; error?: string },
    AxiosError,
    { cycleId: string; orgUnitId: string }
  >({
    mutationFn: ({ cycleId, orgUnitId }) => regenerateTemplate(cycleId, orgUnitId),
  });
}

/**
 * Aggregated useCycles hook providing all cycle-related query and mutation hooks.
 * Used by CycleAdminPage for convenient access to all cycle operations.
 *
 * @param params - Optional filter params for the cycle list query.
 * @returns Object containing all cycle hooks.
 */
export function useCycles(params?: { fiscal_year?: number; status?: string }) {
  const cycleListQuery = useCycleList(params);
  const createCycleMutation = useCreateCycle();
  const openCycleMutation = useOpenCycle();
  const closeCycleMutation = useCloseCycle();
  const reopenCycleMutation = useReopenCycle();
  const setRemindersMutation = useSetReminders();
  const regenerateTemplateMutation = useRegenerateTemplate();

  return {
    cycleListQuery,
    createCycleMutation,
    openCycleMutation,
    closeCycleMutation,
    reopenCycleMutation,
    setRemindersMutation,
    regenerateTemplateMutation,
  };
}

export { getCycle };
