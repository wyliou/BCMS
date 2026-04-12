import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { http, HttpResponse } from 'msw';
import i18n from '../../../../src/i18n';
import ConsolidatedReportPage from '../../../../src/pages/reports/ConsolidatedReportPage';
import { useAuthStore } from '../../../../src/stores/auth-store';
import { server } from '../../../setup';

// Reason: mock download helpers to avoid actual file downloads in tests
vi.mock('../../../../src/lib/download', () => ({
  downloadBlob: vi.fn().mockResolvedValue(undefined),
  pollAndDownload: vi.fn().mockResolvedValue(undefined),
}));

import { downloadBlob, pollAndDownload } from '../../../../src/lib/download';

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

const MOCK_REPORT = {
  cycle_id: CYCLE_ID,
  rows: [
    {
      org_unit_id: 'unit-1',
      org_unit_name: 'Unit A',
      account_code: '6100',
      account_name: 'Salary',
      actual: '100000.00',
      operational_budget: '120000.00',
      personnel_budget: null,
      shared_cost: null,
      delta_amount: '20000.00',
      delta_pct: '16.7%',
      budget_status: 'uploaded',
    },
    {
      org_unit_id: 'unit-2',
      org_unit_name: 'Unit B',
      account_code: '6200',
      account_name: 'Travel',
      actual: '0',
      operational_budget: null,
      personnel_budget: '50000.00',
      shared_cost: '30000.00',
      delta_amount: null,
      delta_pct: 'N/A',
      budget_status: 'not_uploaded',
    },
  ],
  reporting_currency: 'TWD',
  budget_last_updated_at: '2026-04-10T08:00:00Z',
  personnel_last_updated_at: '2026-04-09T12:00:00Z',
  shared_cost_last_updated_at: null,
};

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
 * Renders the ConsolidatedReportPage with all required providers.
 */
function renderPage() {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MantineProvider>
        <I18nextProvider i18n={i18n}>
          <MemoryRouter initialEntries={['/reports']}>
            <ConsolidatedReportPage />
          </MemoryRouter>
        </I18nextProvider>
      </MantineProvider>
    </QueryClientProvider>,
  );
}

function setupDefaultHandlers() {
  server.use(
    http.get('*/cycles', () => HttpResponse.json(MOCK_CYCLES)),
    http.get(`*/cycles/${CYCLE_ID}/reports/consolidated`, () =>
      HttpResponse.json(MOCK_REPORT),
    ),
  );
}

describe('ConsolidatedReportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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

  it('renders three-column-group table with correct column headers', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // Reason: Column group and leaf column headers share the same text ("人力預算", "公攤費用")
    // so we use getAllByText and verify they appear at least once
    expect(
      screen.getByText(i18n.t('report.column_groups.operational_budget')),
    ).toBeInTheDocument();
    const personnelHeaders = screen.getAllByText(i18n.t('report.column_groups.personnel_budget'));
    expect(personnelHeaders.length).toBeGreaterThanOrEqual(1);
    const sharedCostHeaders = screen.getAllByText(i18n.t('report.column_groups.shared_cost'));
    expect(sharedCostHeaders.length).toBeGreaterThanOrEqual(1);
  });

  it('null personnel_budget and shared_cost display as dash', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // Unit A has null personnel_budget and shared_cost
    const dashes = screen.getAllByText('\u2014');
    // Should have at least 2 dashes for the null personnel/shared values
    expect(dashes.length).toBeGreaterThanOrEqual(2);
  });

  it('delta_pct N/A renders correctly', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('N/A')).toBeInTheDocument();
    });
  });

  it('budget_status not_uploaded shows translated text', async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit B')).toBeInTheDocument();
    });

    // Reason: "未上傳" may appear multiple times; verify at least one
    const notUploadedElements = screen.getAllByText(i18n.t('report.status.not_uploaded'));
    expect(notUploadedElements.length).toBeGreaterThanOrEqual(1);
  });

  it('export async flow: pollAndDownload called on 202 response', async () => {
    server.use(
      http.post(`*/cycles/${CYCLE_ID}/reports/exports`, () =>
        HttpResponse.json({ mode: 'async', job_id: 'job-1' }, { status: 202 }),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    // Open the export menu dropdown
    const exportButton = screen.getByText(i18n.t('report.export.button'));
    await user.click(exportButton);

    // Reason: Mantine Menu renders dropdown items after click; wait for them
    await waitFor(() => {
      expect(screen.getByText(i18n.t('report.export.xlsx'))).toBeInTheDocument();
    });

    const xlsxItem = screen.getByText(i18n.t('report.export.xlsx'));
    await user.click(xlsxItem);

    await waitFor(() => {
      expect(pollAndDownload).toHaveBeenCalledWith(
        '/exports/job-1',
        '/exports/job-1/file',
      );
    });
  });

  it('export sync flow: downloadBlob called on 201 response', async () => {
    server.use(
      http.post(`*/cycles/${CYCLE_ID}/reports/exports`, () =>
        HttpResponse.json(
          {
            mode: 'sync',
            file_url: '/exports/file-1.csv',
            expires_at: '2026-04-13T00:00:00Z',
          },
          { status: 201 },
        ),
      ),
    );

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Unit A')).toBeInTheDocument();
    });

    const exportButton = screen.getByText(i18n.t('report.export.button'));
    await user.click(exportButton);

    await waitFor(() => {
      expect(screen.getByText(i18n.t('report.export.csv'))).toBeInTheDocument();
    });

    const csvItem = screen.getByText(i18n.t('report.export.csv'));
    await user.click(csvItem);

    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledWith('/exports/file-1.csv', 'report.csv');
    });
  });
});
