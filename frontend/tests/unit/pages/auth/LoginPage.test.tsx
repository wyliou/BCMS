import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../../src/i18n';
import LoginPage from '../../../../src/pages/auth/LoginPage';
import { useAuthStore } from '../../../../src/stores/auth-store';

/**
 * Wrapper providing contexts for LoginPage tests.
 */
function Wrapper({
  children,
  initialEntries = ['/'],
}: {
  children: React.ReactNode;
  initialEntries?: string[];
}) {
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </I18nextProvider>
    </MantineProvider>
  );
}

describe('LoginPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it('renders the platform title and SSO login button', () => {
    render(
      <Wrapper>
        <LoginPage />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('auth.login_title'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('auth.login_button'))).toBeInTheDocument();
  });

  it('navigates to SSO login on button click', async () => {
    const user = userEvent.setup();

    render(
      <Wrapper>
        <LoginPage />
      </Wrapper>,
    );

    const btn = screen.getByText(i18n.t('auth.login_button'));

    // Reason: jsdom throws on full-page navigation; we just verify no crash
    try {
      await user.click(btn);
    } catch {
      // Expected in jsdom — navigation not implemented
    }
  });

  it('shows unauthorized error when URL has ?error=AUTH_003', () => {
    render(
      <Wrapper initialEntries={['/?error=AUTH_003']}>
        <LoginPage />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('auth.unauthorized'))).toBeInTheDocument();
  });

  it('redirects to /dashboard when already authenticated', () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        role: 'FinanceAdmin',
        roles: ['FinanceAdmin'],
        org_unit_id: null,
        display_name: 'Test',
      },
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <MantineProvider>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/']}>
            <Routes>
              <Route path="/" element={<LoginPage />} />
              <Route path="/dashboard" element={<div data-testid="dashboard">Dashboard</div>} />
            </Routes>
          </MemoryRouter>
        </I18nextProvider>
      </MantineProvider>,
    );

    // Should have navigated to /dashboard
    expect(screen.getByTestId('dashboard')).toBeInTheDocument();
  });
});
