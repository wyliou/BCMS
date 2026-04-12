import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { http, HttpResponse } from 'msw';
import i18n from '../../../../src/i18n';
import DashboardPage from '../../../../src/pages/dashboard/DashboardPage';
import { useAuthStore } from '../../../../src/stores/auth-store';
import { server } from '../../../setup';

const CYCLE_ID = '550e8400-e29b-41d4-a716-446655440099';

const MOCK_CYCLES = [
  {
    id: CYCLE_ID,
    fiscal_year: 2026,
    deadline: '2026-06-30',
    reporting_currency: 'TWD',
    status: 'Open',
    opened_at: '2026-01-01T00:00:00Z',
    closed_at: null,
    reopened_at: null,
  },
];

const MOCK_DASHBOARD = {
  cycle: { id: CYCLE_ID, fiscal_year: 2026, deadline: '2026-06-30', status: 'Open' },
  items: [
    {
      org_unit_id: 'unit-1',
      org_unit_name: 'Unit A',
      status: 'not_downloaded',
      last_uploaded_at: null,
      version: null,
      recipient_user_id: 'user-1',
      recipient_email: 'a@test.com',
    },
    {
      org_unit_id: 'unit-2',
      org_unit_name: 'Unit B',
      status: 'uploaded',
      last_uploaded_at: '2026-04-01T10:00:00Z',
      version: 2,
      recipient_user_id: 'user-2',
      recipient_email: 'b@test.com',
    },
    {
      org_unit_id: 'unit-3',
      org_unit_name: 'Unit C',
      status: 'resubmit_requested',
      last_uploaded_at: '2026-03-15T08:00:00Z',
      version: 1,
      recipient_user_id: 'user-3',
      recipient_email: 'c@test.com',
    },
  ],
  summary: {
    total: 3,
    uploaded: 1,
    not_downloaded: 1,
    downloaded: 0,
    resubmit_requested: 1,
  },
  data_freshness: { snapshot_at: '2026-04-12T00:00:00Z', stale: false },
};

const MOCK_FAILED_NOTIFICATIONS = { items: [] };

/**
 * Creates a fresh QueryClient for test isolation.
 */
function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

/**
 * Renders the DashboardPage with all required providers.
 */
function renderPage() {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/dashboard']}>
            <DashboardPage />
          </MemoryRouter>
        </I18nextProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

function setupDefaultHandlers() {
  server.use(
    http.get('*/cycles', () => HttpResponse.json(MOCK_CYCLES)),
    http.get(`*/cycles/${CYCLE_ID}/dashboard`, () => HttpResponse.json(MOCK_DASHBOARD)),
    http.get('*/notifications/failed', () => HttpResponse.json(MOCK_FAILED_NOTIFICATIONS)),
    // Reason: Catch resubmit-request history calls from the ResubmitModal
    http.get('*/resubmit-requests', () => HttpResponse.json([])),
  );
}

describe('DashboardPage', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        role: 'FinanceAdmin',
        roles: ['FinanceAdmin'],
        org_unit_id: null,
        display_name: 'Admin',
      },
      isAuthenticated: true,
      isLoading: false,
    });
    setupDefaultHandlers();
  });

  it('renders summary cards and status grid on success', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // Verify summary cards are present
    expect(screen.getByText(i18n.t('dashboard.summary.total'))).toBeInTheDocument();

    // Verify the total count card shows "3"
    expect(screen.getByText('3')).toBeInTheDocument();

    // Verify table rows
    expect(screen.getByText('Unit B')).toBeInTheDocument();
    expect(screen.getByText('Unit C')).toBeInTheDocument();
  });

  it('shows stale data banner when data_freshness.stale is true', async () => {
    server.use(
      http.get(`*/cycles/${CYCLE_ID}/dashboard`, () =>
        HttpResponse.json({
          ...MOCK_DASHBOARD,
          data_freshness: { snapshot_at: '2026-04-12T00:00:00Z', stale: true },
        }),
      ),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(i18n.t('dashboard.freshness.stale'))).toBeInTheDocument();
    });

    // Data should still be displayed (not cleared)
    expect(screen.getByText('Unit A')).toBeInTheDocument();
  });

  it('CompanyReviewer sees report link, not status grid', () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440001',
        role: 'CompanyReviewer',
        roles: ['CompanyReviewer'],
        org_unit_id: null,
        display_name: 'Reviewer',
      },
      isAuthenticated: true,
      isLoading: false,
    });

    renderPage();

    // Should show the report link banner
    expect(
      screen.getByText(i18n.t('dashboard.company_reviewer.report_link'), { exact: false }),
    ).toBeInTheDocument();

    // Should NOT show the status grid
    expect(screen.queryByText(i18n.t('dashboard.summary.total'))).not.toBeInTheDocument();
  });

  it('opens resubmit modal on button click', async () => {
    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // Reason: "通知重傳" appears as both button text in table rows and modal title
    const resubmitButtons = screen.getAllByRole('button', {
      name: i18n.t('dashboard.actions.resubmit'),
    });
    await user.click(resubmitButtons[0]);

    // Reason: The ResubmitModal title includes both resubmit label and unit name
    await waitFor(() => {
      // Verify the modal's reason textarea label is present (proves modal opened)
      expect(screen.getByText(i18n.t('resubmit.reason_label'))).toBeInTheDocument();
    });
  });

  it('failed notifications section visible to FinanceAdmin', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // FinanceAdmin sees the failed notifications panel
    // Reason: Accordion may duplicate text in aria attributes, use getAllByText
    const failedTitles = screen.getAllByText(
      i18n.t('dashboard.failed_notifications.title'),
      { exact: false },
    );
    expect(failedTitles.length).toBeGreaterThanOrEqual(1);
  });
});
