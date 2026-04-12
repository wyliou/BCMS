import { useQuery, useMutation, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import { listUsers, patchUser, deactivateUser, User, UsersList } from '../../api/admin';

/**
 * Parameters for listing users.
 */
export interface UsersListParams {
  page?: number;
  size?: number;
}

/**
 * Hook to fetch paginated user list.
 *
 * @param params - Pagination parameters.
 * @returns Query result with users, loading, and error states.
 */
export function useUsers(
  params: UsersListParams = { page: 1, size: 50 },
): UseQueryResult<UsersList> {
  return useQuery({
    queryKey: ['users', params],
    queryFn: () => listUsers(params),
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to patch a user's roles and/or org unit.
 *
 * @returns Mutation object for user updates.
 */
export function usePatchUser(): UseMutationResult<
  User,
  AxiosError,
  { userId: string; updates: { roles?: string[]; org_unit_id?: string | null } }
> {
  return useMutation({
    mutationFn: ({ userId, updates }) => patchUser(userId, updates),
  });
}

/**
 * Hook to deactivate a user.
 *
 * @returns Mutation object for user deactivation.
 */
export function useDeactivateUser(): UseMutationResult<User, AxiosError, string> {
  return useMutation({
    mutationFn: (userId) => deactivateUser(userId),
  });
}
