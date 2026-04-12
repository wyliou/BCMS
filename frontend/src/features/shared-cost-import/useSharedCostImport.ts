import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  importSharedCosts,
  listSharedCostVersions,
  SharedCostUploadRead,
} from '../../api/shared-costs';

/**
 * Hook wrapping importSharedCosts mutation and listSharedCostVersions query.
 *
 * @param cycleId - The open cycle UUID. Pass null to disable queries.
 * @returns Query result for version list and mutation for file import.
 */
export function useSharedCostImport(cycleId: string | null) {
  const queryClient = useQueryClient();

  const versionsQuery = useQuery<SharedCostUploadRead[], AxiosError>({
    queryKey: ['sharedCostVersions', cycleId],
    queryFn: () => listSharedCostVersions(cycleId!),
    enabled: cycleId !== null,
    staleTime: 30000,
  });

  const importMutation = useMutation<
    SharedCostUploadRead,
    AxiosError,
    { cycleId: string; file: File }
  >({
    mutationFn: ({ cycleId: cid, file }) => importSharedCosts(cid, file),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['sharedCostVersions', variables.cycleId] });
    },
  });

  return { versionsQuery, importMutation };
}
