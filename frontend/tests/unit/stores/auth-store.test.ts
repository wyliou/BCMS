import { describe, it, expect, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../setup';
import { useAuthStore } from '../../../src/stores/auth-store';

const validUser = {
  user_id: '550e8400-e29b-41d4-a716-446655440000',
  role: 'FinanceAdmin',
  roles: ['FinanceAdmin', 'SystemAdmin'],
  org_unit_id: '660e8400-e29b-41d4-a716-446655440000',
  display_name: 'Test User',
};

describe('auth-store', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it('fetchUser sets user and isAuthenticated on success', async () => {
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json(validUser);
      }),
    );

    await useAuthStore.getState().fetchUser();
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.user?.display_name).toBe('Test User');
    expect(state.isLoading).toBe(false);
  });

  it('fetchUser clears state on error', async () => {
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json({}, { status: 500 });
      }),
      http.post('*/auth/refresh', () => {
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await useAuthStore.getState().fetchUser();
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBeNull();
    expect(state.isLoading).toBe(false);
  });

  it('logout clears user and isAuthenticated', async () => {
    useAuthStore.setState({
      user: validUser,
      isAuthenticated: true,
    });

    server.use(
      http.post('*/auth/logout', () => {
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await useAuthStore.getState().logout();
    const state = useAuthStore.getState();
    expect(state.user).toBeNull();
    expect(state.isAuthenticated).toBe(false);
  });

  it('hasRole returns true when user has all specified roles', () => {
    useAuthStore.setState({ user: validUser, isAuthenticated: true });
    expect(useAuthStore.getState().hasRole('FinanceAdmin')).toBe(true);
    expect(useAuthStore.getState().hasRole('FinanceAdmin', 'SystemAdmin')).toBe(true);
    expect(useAuthStore.getState().hasRole('HRAdmin')).toBe(false);
  });

  it('hasAnyRole returns true when user has at least one role', () => {
    useAuthStore.setState({ user: validUser, isAuthenticated: true });
    expect(useAuthStore.getState().hasAnyRole('HRAdmin', 'FinanceAdmin')).toBe(true);
    expect(useAuthStore.getState().hasAnyRole('HRAdmin', 'ITSecurityAuditor')).toBe(false);
  });

  it('hasRole and hasAnyRole return false when user is null', () => {
    expect(useAuthStore.getState().hasRole('FinanceAdmin')).toBe(false);
    expect(useAuthStore.getState().hasAnyRole('FinanceAdmin')).toBe(false);
  });
});
