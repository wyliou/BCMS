import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { importPersonnel, listPersonnelVersions, PersonnelImportRead } from '../../api/personnel';

/**
 * Hook wrapping importPersonnel mutation and listPersonnelVersions query.
 *
 * @param cycleId - The open cycle UUID. Pass null to disable queries.
 * @returns Query result for version list and mutation for file import.
 */
export function usePersonnelImport(cycleId: string | null) {
  const queryClient = useQueryClient();

  const versionsQuery = useQuery<PersonnelImportRead[], AxiosError>({
    queryKey: ['personnelVersions', cycleId],
    queryFn: () => listPersonnelVersions(cycleId!),
    enabled: cycleId !== null,
    staleTime: 30000,
  });

  const importMutation = useMutation<
    PersonnelImportRead,
    AxiosError,
    { cycleId: string; file: File }
  >({
    mutationFn: ({ cycleId: cid, file }) => importPersonnel(cid, file),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['personnelVersions', variables.cycleId] });
    },
  });

  return { versionsQuery, importMutation };
}
