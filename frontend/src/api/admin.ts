import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for an organization unit.
 */
const OrgUnitSchema = z.object({
  id: z.string().uuid(),
  code: z.string(),
  name: z.string(),
  level_code: z.string(),
  is_filing_unit: z.boolean(),
  has_manager: z.boolean(),
  warnings: z.array(z.string()).optional(),
  excluded_for_cycle_ids: z.array(z.string().uuid()).optional(),
});

export type OrgUnit = z.infer<typeof OrgUnitSchema>;

/**
 * Zod schema for the org units list response.
 */
const OrgUnitsListSchema = z.object({
  items: z.array(OrgUnitSchema),
  total: z.number().int(),
});

export type OrgUnitsList = z.infer<typeof OrgUnitsListSchema>;

/**
 * Zod schema for a user.
 */
const UserSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  email: z.string().email(),
  roles: z.array(z.string()),
  org_unit_id: z.string().uuid().nullable(),
  is_active: z.boolean(),
});

export type User = z.infer<typeof UserSchema>;

/**
 * Zod schema for the users list response.
 */
const UsersListSchema = z.object({
  items: z.array(UserSchema),
  total: z.number().int(),
  page: z.number().int(),
  size: z.number().int(),
});

export type UsersList = z.infer<typeof UsersListSchema>;

/**
 * Fetches all organization units.
 *
 * @returns List of organization units.
 * @throws AxiosError if the request fails.
 */
export async function listOrgUnits(): Promise<OrgUnitsList> {
  const response = await apiClient.get<unknown>('/admin/org-units');
  return OrgUnitsListSchema.parse(response.data);
}

/**
 * Updates an organization unit's excluded cycles.
 *
 * @param id - The org unit ID.
 * @param excludedForCycleIds - Array of cycle IDs to exclude.
 * @returns The updated org unit.
 * @throws AxiosError if the request fails.
 */
export async function patchOrgUnit(id: string, excludedForCycleIds: string[]): Promise<OrgUnit> {
  const response = await apiClient.patch<unknown>(`/admin/org-units/${id}`, {
    excluded_for_cycle_ids: excludedForCycleIds,
  });
  return OrgUnitSchema.parse(response.data);
}

/**
 * Fetches a paginated list of users.
 *
 * @param params - Query parameters: page, size.
 * @returns Paginated user list.
 * @throws AxiosError if the request fails.
 */
export async function listUsers(params: { page?: number; size?: number }): Promise<UsersList> {
  const response = await apiClient.get<unknown>('/admin/users', { params });
  return UsersListSchema.parse(response.data);
}

/**
 * Updates a user's roles and/or org unit assignment.
 *
 * @param userId - The user ID.
 * @param updates - Object with roles and/or org_unit_id.
 * @returns The updated user.
 * @throws AxiosError if the request fails.
 */
export async function patchUser(
  userId: string,
  updates: { roles?: string[]; org_unit_id?: string | null },
): Promise<User> {
  const response = await apiClient.patch<unknown>(`/admin/users/${userId}`, updates);
  return UserSchema.parse(response.data);
}

/**
 * Deactivates a user.
 *
 * @param userId - The user ID.
 * @returns The deactivated user.
 * @throws AxiosError if the request fails.
 */
export async function deactivateUser(userId: string): Promise<User> {
  const response = await apiClient.post<unknown>(`/admin/users/${userId}/deactivate`);
  return UserSchema.parse(response.data);
}
