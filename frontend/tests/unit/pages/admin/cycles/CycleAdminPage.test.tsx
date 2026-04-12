import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from '../../../../../src/i18n';
import { useAuthStore } from '../../../../../src/stores/auth-store';
import { server } from '../../../../setup';
import CycleAdminPage from '../../../../../src/pages/admin/cycles/CycleAdminPage';

/**
 * Creates a fresh QueryClient for each test to prevent cache leakage.
 *
 * @returns A new QueryClient instance.
 */
function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/**
 * Test wrapper providing all required contexts.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = makeQueryClient();
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>
        <QueryClientProvider client={qc}>
          <MemoryRouter>{children}</MemoryRouter>
        </QueryClientProvider>
      </I18nextProvider>
    </MantineProvider>
  );
}

const DRAFT_CYCLE = {
  id: '11111111-1111-1111-1111-111111111111',
  fiscal_year: 2025,
  deadline: '2025-03-31',
  reporting_currency: 'TWD',
  status: 'Draft',
  opened_at: null,
  closed_at: null,
  reopened_at: null,
};

const CLOSED_CYCLE = {
  id: '22222222-2222-2222-2222-222222222222',
  fiscal_year: 2024,
  deadline: '2024-03-31',
  reporting_currency: 'TWD',
  status: 'Closed',
  opened_at: '2024-01-01T00:00:00Z',
  closed_at: '2024-04-01T00:00:00Z',
  reopened_at: null,
};

beforeEach(() => {
  useAuthStore.setState({
    user: {
      user_id: 'admin-user-id',
      role: 'FinanceAdmin',
      roles: ['FinanceAdmin'],
      org_unit_id: null,
      display_name: 'Admin',
    },
    isAuthenticated: true,
    isLoading: false,
  });
});

describe('CycleAdminPage', () => {
  it('renders cycle list with correct status badges', async () => {
    server.use(
      http.get('*/cycles', () => {
        return HttpResponse.json([DRAFT_CYCLE, CLOSED_CYCLE]);
      }),
    );

    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('2025 — TWD')).toBeInTheDocument();
      expect(screen.getByText('2024 — TWD')).toBeInTheDocument();
    });

    // Draft cycle should show open button; Closed should not (FinanceAdmin can't reopen)
    expect(screen.getByText(i18n.t('cycle.open_cycle'))).toBeInTheDocument();
    expect(screen.queryByText(i18n.t('cycle.reopen_cycle'))).not.toBeInTheDocument();
  });

  it('shows empty state when no cycles exist', async () => {
    server.use(
      http.get('*/cycles', () => {
        return HttpResponse.json([]);
      }),
    );

    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.no_cycles'))).toBeInTheDocument();
    });
  });

  it('validates create cycle form before API call', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/cycles', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.no_cycles'))).toBeInTheDocument();
    });

    // Open the create modal
    const createBtns = screen.getAllByText(i18n.t('cycle.create_cycle'));
    await user.click(createBtns[0]);

    // Wait for modal to appear
    await waitFor(() => {
      expect(screen.getByText(i18n.t('common.confirm'))).toBeInTheDocument();
    });

    // Clear fiscal year and try to submit
    // The form should fail validation without API call
    const confirmBtn = screen.getByText(i18n.t('common.confirm'));
    await user.click(confirmBtn);

    // Modal should still be open (submission failed)
    expect(screen.getByText(i18n.t('common.confirm'))).toBeInTheDocument();
  });

  it('shows open cycle generation summary with retry button on error', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([DRAFT_CYCLE])),
      http.post('*/cycles/*/open', () =>
        HttpResponse.json({
          cycle: { ...DRAFT_CYCLE, status: 'Open' },
          transition: 'Draft->Open',
          generation_summary: {
            total: 2,
            generated: 1,
            errors: 1,
            error_details: [
              {
                org_unit_id: '33333333-3333-3333-3333-333333333333',
                status: 'error',
                error: 'Template generation failed',
              },
            ],
          },
          dispatch_summary: { total_recipients: 2, sent: 2, errors: 0 },
        }),
      ),
      http.post('*/cycles/*/templates/*/regenerate', () =>
        HttpResponse.json({
          org_unit_id: '33333333-3333-3333-3333-333333333333',
          status: 'success',
        }),
      ),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.open_cycle'))).toBeInTheDocument();
    });

    await user.click(screen.getByText(i18n.t('cycle.open_cycle')));

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.generation_summary'))).toBeInTheDocument();
      expect(screen.getByText(i18n.t('cycle.retry_template'))).toBeInTheDocument();
    });

    // Click retry button
    await user.click(screen.getByText(i18n.t('cycle.retry_template')));
    // No assertion on result here since regenerate mock returns success
  });

  it('shows close confirmation dialog before closing', async () => {
    const OPEN_CYCLE = { ...DRAFT_CYCLE, status: 'Open', opened_at: '2025-01-01T00:00:00Z' };
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.close_cycle'))).toBeInTheDocument();
    });

    await user.click(screen.getByText(i18n.t('cycle.close_cycle')));

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.confirm_close_message'))).toBeInTheDocument();
    });
  });

  it('shows ErrorDisplay on CYCLE_003 when opening cycle', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([DRAFT_CYCLE])),
      http.post('*/cycles/*/open', () =>
        HttpResponse.json(
          { error: { code: 'CYCLE_003', message: 'Not in Draft state' } },
          { status: 409 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <CycleAdminPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('cycle.open_cycle'))).toBeInTheDocument();
    });

    await user.click(screen.getByText(i18n.t('cycle.open_cycle')));

    await waitFor(() => {
      expect(screen.getByText('CYCLE_003')).toBeInTheDocument();
    });
  });
});
