import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import i18n from '../../../../src/i18n';
import OrgTreePage from '../../../../src/pages/admin/org-units/OrgTreePage';
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

describe('OrgTreePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Set SystemAdmin role for editable tests
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

  it('renders org units table on success', async () => {
    const mockOrgUnits = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'ORG001',
          name: 'Finance Department',
          level_code: '1000',
          is_filing_unit: true,
          has_manager: true,
          warnings: [],
          excluded_for_cycle_ids: [],
        },
      ],
      total: 1,
    };

    vi.spyOn(adminApi, 'listOrgUnits').mockResolvedValue(mockOrgUnits);

    render(
      <Wrapper>
        <OrgTreePage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('Finance Department')).toBeInTheDocument();
    });
  });

  it('shows loading skeleton while fetching org units', () => {
    vi.spyOn(adminApi, 'listOrgUnits').mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    render(
      <Wrapper>
        <OrgTreePage />
      </Wrapper>,
    );

    // Skeleton rows should be visible
    const skeletons = document.querySelectorAll('.mantine-Skeleton-root');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('shows empty state message when no org units', async () => {
    vi.spyOn(adminApi, 'listOrgUnits').mockResolvedValue({ items: [], total: 0 });

    render(
      <Wrapper>
        <OrgTreePage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('org_tree.empty.no_units'))).toBeInTheDocument();
    });
  });

  it('displays read-only badge when user is not SystemAdmin', async () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440002',
        role: 'FinanceAdmin',
        roles: ['FinanceAdmin'],
        org_unit_id: null,
        display_name: 'Finance User',
      },
      isAuthenticated: true,
    });

    vi.spyOn(adminApi, 'listOrgUnits').mockResolvedValue({ items: [], total: 0 });

    render(
      <Wrapper>
        <OrgTreePage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('org_tree.info.read_only'))).toBeInTheDocument();
    });
  });

  it('opens edit modal when edit button is clicked', async () => {
    const mockOrgUnits = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          code: 'ORG001',
          name: 'Finance Department',
          level_code: '1000',
          is_filing_unit: true,
          has_manager: true,
          warnings: [],
          excluded_for_cycle_ids: [],
        },
      ],
      total: 1,
    };

    vi.spyOn(adminApi, 'listOrgUnits').mockResolvedValue(mockOrgUnits);

    render(
      <Wrapper>
        <OrgTreePage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('Finance Department')).toBeInTheDocument();
    });

    const editButton = screen.getByText(i18n.t('org_tree.buttons.edit'));
    await userEvent.click(editButton);

    await waitFor(() => {
      expect(screen.getByText(i18n.t('org_tree.modal.title'))).toBeInTheDocument();
    });
  });
});
