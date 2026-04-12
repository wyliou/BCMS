import { describe, it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../../setup';
import { fetchMe, logout } from '../../../src/api/auth';

const validUser = {
  user_id: '550e8400-e29b-41d4-a716-446655440000',
  role: 'FinanceAdmin',
  roles: ['FinanceAdmin'],
  org_unit_id: '660e8400-e29b-41d4-a716-446655440000',
  display_name: 'Test User',
};

describe('auth API', () => {
  it('fetchMe returns validated WhoAmIResponse on valid response', async () => {
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json(validUser);
      }),
    );

    const result = await fetchMe();
    expect(result.user_id).toBe(validUser.user_id);
    expect(result.display_name).toBe('Test User');
    expect(result.roles).toEqual(['FinanceAdmin']);
  });

  it('fetchMe throws zod error on invalid response shape', async () => {
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json({ invalid: true });
      }),
    );

    await expect(fetchMe()).rejects.toThrow();
  });

  it('logout calls POST /auth/logout', async () => {
    let called = false;
    server.use(
      http.post('*/auth/logout', () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logout();
    expect(called).toBe(true);
  });

  it('fetchMe propagates error on 503', async () => {
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json({}, { status: 503 });
      }),
      // Reason: intercept the refresh that the 401 interceptor might try
      http.post('*/auth/refresh', () => {
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(fetchMe()).rejects.toThrow();
  });
});
