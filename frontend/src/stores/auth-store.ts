import { create } from 'zustand';
import { fetchMe, logout as apiLogout, WhoAmIResponse } from '../api/auth';

/**
 * Shape of the Zustand auth store slice.
 */
interface AuthState {
  user: WhoAmIResponse | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  fetchUser: () => Promise<void>;
  logout: () => Promise<void>;
  hasRole: (...roles: string[]) => boolean;
  hasAnyRole: (...roles: string[]) => boolean;
}

/**
 * Zustand auth store. Holds the current user profile, authentication
 * status, and helpers for role-based checks.
 *
 * Auth state is derived from GET /auth/me. No tokens are stored.
 * Page refresh triggers a new fetchUser() call.
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,

  /**
   * Fetches the current user profile from the API.
   * On success, sets user and isAuthenticated.
   * On failure, clears auth state silently.
   */
  async fetchUser() {
    set({ isLoading: true });
    try {
      const user = await fetchMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch {
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },

  /**
   * Logs out the current user by calling the API and clearing local state.
   * Navigates to / after clearing state.
   */
  async logout() {
    try {
      await apiLogout();
    } finally {
      set({ user: null, isAuthenticated: false });
      window.location.href = '/';
    }
  },

  /**
   * Returns true if ALL specified roles are present in the user's roles array.
   *
   * @param roles - Roles that must all be present.
   * @returns Whether the user has every specified role.
   */
  hasRole(...roles: string[]): boolean {
    const { user } = get();
    if (!user) return false;
    return roles.every((role) => user.roles.includes(role));
  },

  /**
   * Returns true if AT LEAST ONE of the specified roles is present.
   *
   * @param roles - Roles to check against.
   * @returns Whether the user has any one of the specified roles.
   */
  hasAnyRole(...roles: string[]): boolean {
    const { user } = get();
    if (!user) return false;
    return roles.some((role) => user.roles.includes(role));
  },
}));
