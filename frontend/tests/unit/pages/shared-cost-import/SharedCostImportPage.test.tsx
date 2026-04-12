import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AxiosError, AxiosResponse, AxiosHeaders } from 'axios';
import i18n from '../../../../src/i18n';
import { useAuthStore } from '../../../../src/stores/auth-store';
import { server } from '../../../setup';
import SharedCostImportPage from '../../../../src/pages/shared-cost-import/SharedCostImportPage';
import * as sharedCostsApi from '../../../../src/api/shared-costs';

/**
 * Creates a fresh QueryClient for each test.
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

const OPEN_CYCLE = {
  id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  fiscal_year: 2025,
  deadline: '2025-03-31',
  reporting_currency: 'TWD',
  status: 'Open',
  opened_at: '2025-01-01T00:00:00Z',
  closed_at: null,
  reopened_at: null,
};

beforeEach(() => {
  useAuthStore.setState({
    user: {
      user_id: 'aaaaaaaa-1111-2222-3333-444444444444',
      role: 'FinanceAdmin',
      roles: ['FinanceAdmin'],
      org_unit_id: null,
      display_name: 'Finance Admin',
    },
    isAuthenticated: true,
    isLoading: false,
  });
});

describe('SharedCostImportPage', () => {
  it('renders file upload zone and empty version history', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/shared-cost-imports', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <SharedCostImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('shared_cost_import.import_file'))).toBeInTheDocument();
      expect(screen.getByText(i18n.t('shared_cost_import.no_versions'))).toBeInTheDocument();
    });
  });

  it('shows SHARED_004 row-level errors via ErrorDisplay', async () => {
    // Reason: axios FormData + MSW in Node hangs; mock the API function directly
    const err = new AxiosError(
      'Batch validation failed',
      'ERR_BAD_REQUEST',
      undefined,
      undefined,
      {
        status: 400,
        data: {
          error: {
            code: 'SHARED_004',
            message: 'Batch validation failed',
            details: [
              {
                row: 5,
                column: 'account_code',
                code: 'SHARED_002',
                reason: 'not shared_cost category',
              },
            ],
          },
        },
        headers: new AxiosHeaders(),
        config: { headers: new AxiosHeaders() },
        statusText: 'Bad Request',
      } as AxiosResponse,
    );
    const spy = vi.spyOn(sharedCostsApi, 'importSharedCosts').mockRejectedValue(err);

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/shared-cost-imports', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <SharedCostImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('shared_cost_import.import_file'))).toBeInTheDocument();
    });

    const file = new File(['dept_id,account_code,amount\nD001,S001,5000'], 'shared.csv', {
      type: 'text/csv',
    });
    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
    fireEvent.change(fileInput);

    await waitFor(
      () => {
        expect(screen.getByText('SHARED_004')).toBeInTheDocument();
      },
      { timeout: 3000 },
    );

    spy.mockRestore();
  });

  it('disables upload and shows no-cycle message when no open cycle', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <SharedCostImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('shared_cost_import.no_open_cycle'))).toBeInTheDocument();
    });

    // File input should not be present when no cycle
    expect(
      screen.queryByLabelText(i18n.t('shared_cost_import.import_file')),
    ).not.toBeInTheDocument();
  });

  it('shows loading indicator during import', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/shared-cost-imports', () => HttpResponse.json([])),
      http.post('*/cycles/*/shared-cost-imports', async () => {
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(
          {
            id: 'cccccccc-1111-2222-3333-444444444444',
            cycle_id: OPEN_CYCLE.id,
            uploader_user_id: 'dddddddd-1111-2222-3333-444444444444',
            uploaded_at: new Date().toISOString(),
            filename: 'shared.csv',
            version: 1,
            affected_org_units_summary: ['D001'],
          },
          { status: 201 },
        );
      }),
    );

    render(
      <Wrapper>
        <SharedCostImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('shared_cost_import.import_file'))).toBeInTheDocument();
    });

    const file = new File(['data'], 'shared.csv', { type: 'text/csv' });
    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
    fireEvent.change(fileInput);

    expect(screen.getByText(i18n.t('common.loading'))).toBeInTheDocument();
  });

  it('shows new version row after successful import', async () => {
    const record = {
      id: 'cccccccc-2222-3333-4444-555555555555',
      cycle_id: OPEN_CYCLE.id,
      uploader_user_id: 'dddddddd-2222-3333-4444-555555555555',
      uploaded_at: '2025-01-15T10:00:00Z',
      filename: 'shared_costs.xlsx',
      version: 2,
      affected_org_units_summary: ['D001', 'D002', 'D003'],
    };

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/shared-cost-imports', () => HttpResponse.json([record])),
    );

    render(
      <Wrapper>
        <SharedCostImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('shared_costs.xlsx')).toBeInTheDocument();
      expect(screen.getByText('D001, D002, D003')).toBeInTheDocument();
    });
  });
});
