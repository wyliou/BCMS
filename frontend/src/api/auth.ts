import { z } from 'zod';
import { apiClient } from './client';

/**
 * Zod schema for the /auth/me response payload.
 */
const WhoAmISchema = z.object({
  user_id: z.string().uuid(),
  role: z.string().nullable(),
  roles: z.array(z.string()),
  org_unit_id: z.string().uuid().nullable(),
  display_name: z.string(),
});

/** Type inferred from the WhoAmI zod schema. */
export type WhoAmIResponse = z.infer<typeof WhoAmISchema>;

/**
 * Fetches the currently authenticated user profile from GET /auth/me.
 * Validates the response against the WhoAmI schema.
 *
 * @returns The validated user profile.
 */
export async function fetchMe(): Promise<WhoAmIResponse> {
  const response = await apiClient.get('/auth/me');
  return WhoAmISchema.parse(response.data);
}

/**
 * Logs out the current user by calling POST /auth/logout.
 * The server clears session cookies on its side.
 */
export async function logout(): Promise<void> {
  await apiClient.post('/auth/logout');
}
