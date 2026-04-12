import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../src/i18n';
import { theme } from '../../../src/styles/theme';
import { ShellLayout } from '../../../src/components/ShellLayout';
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
 * Wrapper providing all required contexts for ShellLayout tests.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider theme={theme}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </MantineProvider>
  );
}

describe('ShellLayout', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
    // Reason: Prevent fetchUser calls during tests from hitting unhandled endpoints
    server.use(
      http.get('*/auth/me', () => {
        return HttpResponse.json(makeUser(['FinanceAdmin']));
      }),
    );
  });

  it('renders FinanceAdmin nav items correctly', () => {
    useAuthStore.setState({
      user: makeUser(['FinanceAdmin']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper>
        <ShellLayout />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('nav.dashboard'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('nav.reports'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('nav.shared_cost_import'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('nav.cycle_admin'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('nav.account_master'))).toBeInTheDocument();
    // Should NOT show upload or user admin
    expect(screen.queryByText(i18n.t('nav.upload'))).not.toBeInTheDocument();
    expect(screen.queryByText(i18n.t('nav.user_admin'))).not.toBeInTheDocument();
  });

  it('renders only Upload for FilingUnitManager', () => {
    useAuthStore.setState({
      user: makeUser(['FilingUnitManager']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper>
        <ShellLayout />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('nav.upload'))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t('nav.dashboard'))).not.toBeInTheDocument();
  });

  it('renders only Personnel Import for HRAdmin', () => {
    useAuthStore.setState({
      user: makeUser(['HRAdmin']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper>
        <ShellLayout />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('nav.personnel_import'))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t('nav.dashboard'))).not.toBeInTheDocument();
  });

  it('renders only Audit Log for ITSecurityAuditor', () => {
    useAuthStore.setState({
      user: makeUser(['ITSecurityAuditor']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper>
        <ShellLayout />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('nav.audit_log'))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t('nav.dashboard'))).not.toBeInTheDocument();
  });

  it('calls logout on logout button click', async () => {
    const user = userEvent.setup();

    server.use(
      http.post('*/auth/logout', () => {
        return new HttpResponse(null, { status: 204 });
      }),
    );

    useAuthStore.setState({
      user: makeUser(['FinanceAdmin']),
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <Wrapper>
        <ShellLayout />
      </Wrapper>,
    );

    const logoutBtn = screen.getByText(i18n.t('common.logout'));
    await user.click(logoutBtn);

    // After logout, store should be cleared
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
  });
});
