import { useQuery, useMutation, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { listOrgUnits, patchOrgUnit, OrgUnit, OrgUnitsList } from '../../api/admin';

/**
 * Hook to fetch the organization units list.
 *
 * @returns Query result with org units, loading, and error states.
 */
export function useOrgUnits(): UseQueryResult<OrgUnitsList> {
  return useQuery({
    queryKey: ['org-units'],
    queryFn: () => listOrgUnits(),
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to update an organization unit's excluded cycles.
 *
 * @returns Mutation object for org unit updates.
 */
export function usePatchOrgUnit(): UseMutationResult<
  OrgUnit,
  AxiosError,
  { id: string; excludedForCycleIds: string[] }
> {
  return useMutation({
    mutationFn: ({ id, excludedForCycleIds }) => patchOrgUnit(id, excludedForCycleIds),
  });
}
