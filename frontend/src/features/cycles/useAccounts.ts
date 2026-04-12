import { useQuery, useMutation, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import { AxiosError } from 'axios';
import {
  listAccounts,
  upsertAccount,
  importActuals,
  Account,
  AccountsList,
  ImportSummary,
} from '../../api/accounts';

/**
 * Hook to fetch the accounts list, optionally filtered by category.
 *
 * @param category - Optional category filter.
 * @returns Query result with accounts, loading, and error states.
 */
export function useAccounts(category?: string): UseQueryResult<AccountsList> {
  return useQuery({
    queryKey: ['accounts', category],
    queryFn: () => listAccounts(category),
    staleTime: 60000, // 1 minute
  });
}

/**
 * Hook to upsert an account.
 *
 * @returns Mutation object for account upsert.
 */
export function useUpsertAccount(): UseMutationResult<
  Account,
  AxiosError,
  {
    code: string;
    name: string;
    category: 'operational' | 'personnel' | 'shared_cost';
    level: number;
  }
> {
  return useMutation({
    mutationFn: (account) => upsertAccount(account),
  });
}

/**
 * Hook to import actuals from a file.
 *
 * @returns Mutation object for actuals import.
 */
export function useImportActuals(): UseMutationResult<
  ImportSummary,
  AxiosError,
  { cycleId: string; file: File }
> {
  return useMutation({
    mutationFn: ({ cycleId, file }) => importActuals(cycleId, file),
  });
}
