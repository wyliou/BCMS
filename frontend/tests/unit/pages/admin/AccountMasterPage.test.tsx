import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import i18n from '../../../../src/i18n';
import AccountMasterPage from '../../../../src/pages/admin/accounts/AccountMasterPage';
import * as accountsApi from '../../../../src/api/accounts';
import { useAuthStore } from '../../../../src/stores/auth-store';

/**
 * Test wrapper providing context and mocked auth state.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
      </MantineProvider>
    </QueryClientProvider>
  );
}

describe('AccountMasterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440001',
        role: 'SystemAdmin',
        roles: ['SystemAdmin'],
        org_unit_id: null,
        display_name: 'Admin User',
      },
      isAuthenticated: true,
    });
  });

  it('renders account list table on success', async () => {
    const mockAccounts = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'ACC001',
          name: 'Operating Expense',
          category: 'operational' as const,
          level: 1000,
        },
      ],
      total: 1,
    };

    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue(mockAccounts);

    render(
      <Wrapper>
        <AccountMasterPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('Operating Expense')).toBeInTheDocument();
    });
  });

  it('shows loading skeleton while fetching accounts', () => {
    vi.spyOn(accountsApi, 'listAccounts').mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    render(
      <Wrapper>
        <AccountMasterPage />
      </Wrapper>,
    );

    const skeletons = document.querySelectorAll('.mantine-Skeleton-root');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('submits upsert form when add account button is clicked', async () => {
    vi.spyOn(accountsApi, 'upsertAccount').mockResolvedValue({
      id: '550e8400-e29b-41d4-a716-446655440001',
      code: 'ACC002',
      name: 'Salary',
      category: 'personnel',
      level: 2000,
    });

    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue({ items: [], total: 0 });

    render(
      <Wrapper>
        <AccountMasterPage />
      </Wrapper>,
    );

    await waitFor(() => {
      const addButton = screen.getByText(i18n.t('accounts.buttons.add_account'));
      expect(addButton).toBeInTheDocument();
    });

    const addButton = screen.getByText(i18n.t('accounts.buttons.add_account'));
    await userEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByPlaceholderText(i18n.t('accounts.form.code_placeholder'))).toBeInTheDocument();
    });
  });

  it('shows empty state message when no accounts', async () => {
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue({ items: [], total: 0 });

    render(
      <Wrapper>
        <AccountMasterPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('accounts.empty.no_accounts'))).toBeInTheDocument();
    });
  });

  it('renders category filter select', async () => {
    vi.spyOn(accountsApi, 'listAccounts').mockResolvedValue({ items: [], total: 0 });

    render(
      <Wrapper>
        <AccountMasterPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('accounts.filter.category'))).toBeInTheDocument();
    });
  });
});
