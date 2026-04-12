import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from '../../../src/i18n';
import { theme } from '../../../src/styles/theme';
import AppRouter from '../../../src/routes';
import { useAuthStore } from '../../../src/stores/auth-store';
import { http, HttpResponse } from 'msw';
import { server } from '../../setup';

const makeUser = (roles: string[]) => ({
  user_id: '550e8400-e29b-41d4-a716-446655440000',
  role: roles[0] ?? null,
  roles,
  org_unit_id: null,
  display_name: 'Test User',
});

/**
 * Full wrapper providing all contexts needed for route testing.
 */
function Wrapper({
  children,
  initialEntries = ['/'],
}: {
  children: React.ReactNode;
  initialEntries?: string[];
}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <MantineProvider theme={theme}>
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </MantineProvider>
  );
}

describe('AppRouter', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json({}, { status: 401 });
      }),
      http.post('*/auth/refresh', () => {
        return HttpResponse.json({}, { status: 401 });
      }),
    );
  });

  it('renders login page at /', () => {
    render(
      <Wrapper>
        <AppRouter />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('auth.login_title'))).toBeInTheDocument();
  });

  it('renders 403 page at /403', () => {
    render(
      <Wrapper initialEntries={['/403']}>
        <AppRouter />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.forbidden_title'))).toBeInTheDocument();
  });

  it('renders 404 page for unknown routes', () => {
    render(
      <Wrapper initialEntries={['/unknown-route']}>
        <AppRouter />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.not_found_title'))).toBeInTheDocument();
  });

  it('redirects unauthenticated user from /dashboard to /', () => {
    render(
      <Wrapper initialEntries={['/dashboard']}>
        <AppRouter />
      </Wrapper>,
    );
    // RouteGuard redirects to /, which shows LoginPage
    expect(screen.getByText(i18n.t('auth.login_title'))).toBeInTheDocument();
  });

  it('renders dashboard for authorized FinanceAdmin', async () => {
    // Reason: Set up MSW handlers for auth + dashboard page API calls
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json(makeUser(['FinanceAdmin']));
      }),
      http.get('*/cycles', () => HttpResponse.json([])),
      http.get('*/notifications/failed', () => HttpResponse.json({ items: [] })),
    );

    useAuthStore.setState({
      user: makeUser(['FinanceAdmin']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper initialEntries={['/dashboard']}>
        <AppRouter />
      </Wrapper>,
    );

    // Lazy-loaded page should render; DashboardPage shows no-cycle prompt when cycles=[]
    expect(await screen.findByText('尚未開放週期')).toBeInTheDocument();
  });
});
