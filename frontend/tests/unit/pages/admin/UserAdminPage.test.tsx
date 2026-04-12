import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import i18n from '../../../../src/i18n';
import UserAdminPage from '../../../../src/pages/admin/users/UserAdminPage';
import * as adminApi from '../../../../src/api/admin';
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

describe('UserAdminPage', () => {
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

  it('renders paginated user table on success', async () => {
    const mockUsers = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          name: 'John Doe',
          email: 'john@example.com',
          roles: ['FinanceAdmin'],
          org_unit_id: null,
          is_active: true,
        },
      ],
      total: 1,
      page: 1,
      size: 50,
    };

    vi.spyOn(adminApi, 'listUsers').mockResolvedValue(mockUsers);

    render(
      <Wrapper>
        <UserAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });
  });

  it('shows loading skeleton while fetching users', () => {
    vi.spyOn(adminApi, 'listUsers').mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    render(
      <Wrapper>
        <UserAdminPage />
      </Wrapper>,
    );

    const skeletons = document.querySelectorAll('.mantine-Skeleton-root');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('opens edit roles modal when edit button is clicked', async () => {
    const mockUsers = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          name: 'John Doe',
          email: 'john@example.com',
          roles: ['FinanceAdmin'],
          org_unit_id: null,
          is_active: true,
        },
      ],
      total: 1,
      page: 1,
      size: 50,
    };

    vi.spyOn(adminApi, 'listUsers').mockResolvedValue(mockUsers);

    render(
      <Wrapper>
        <UserAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    const editButton = screen.getByText(i18n.t('users.buttons.edit_roles'));
    await userEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByText(i18n.t('users.modal.edit_roles_title'))).toBeInTheDocument();
    });
  });

  it('shows empty state message when no users', async () => {
    vi.spyOn(adminApi, 'listUsers').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
    });

    render(
      <Wrapper>
        <UserAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('users.empty.no_users'))).toBeInTheDocument();
    });
  });

  it('opens deactivate confirmation modal when deactivate button is clicked', async () => {
    const mockUsers = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          name: 'John Doe',
          email: 'john@example.com',
          roles: ['FinanceAdmin'],
          org_unit_id: null,
          is_active: true,
        },
      ],
      total: 1,
      page: 1,
      size: 50,
    };

    vi.spyOn(adminApi, 'listUsers').mockResolvedValue(mockUsers);

    render(
      <Wrapper>
        <UserAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('John Doe')).toBeInTheDocument();
    });

    // Find and click the deactivate button
    const deactivateButtons = screen.getAllByText(i18n.t('users.buttons.deactivate'));
    // Filter out the confirm button from modal (only the action button)
    if (deactivateButtons.length > 0) {
      await userEvent.click(deactivateButtons[0]);
    }

    // Wait for the modal to appear
    await waitFor(() => {
      expect(screen.getByText(i18n.t('users.modal.deactivate_title'))).toBeInTheDocument();
    });
  });
});
