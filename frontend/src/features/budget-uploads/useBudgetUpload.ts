import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { uploadBudget, listUploadVersions, BudgetUploadRead } from '../../api/budget-uploads';

/**
 * Hook wrapping uploadBudget mutation and listUploadVersions query.
 * org_unit_id must come from the auth store — never from URL params.
 *
 * @param cycleId - The open cycle UUID. Pass null to disable queries.
 * @param orgUnitId - The authenticated user's org unit UUID.
 * @returns Query result for version list and mutation for file upload.
 */
export function useBudgetUpload(cycleId: string | null, orgUnitId: string | null) {
  const queryClient = useQueryClient();

  const versionsQuery = useQuery<BudgetUploadRead[], AxiosError>({
    queryKey: ['uploadVersions', cycleId, orgUnitId],
    queryFn: () => listUploadVersions(cycleId!, orgUnitId!),
    enabled: cycleId !== null && orgUnitId !== null,
    staleTime: 30000,
  });

  const uploadMutation = useMutation<
    BudgetUploadRead,
    AxiosError,
    { cycleId: string; orgUnitId: string; file: File }
  >({
    mutationFn: ({ cycleId: cid, orgUnitId: oid, file }) => uploadBudget(cid, oid, file),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ['uploadVersions', variables.cycleId, variables.orgUnitId],
      });
    },
  });

  return { versionsQuery, uploadMutation };
}
