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
import PersonnelImportPage from '../../../../src/pages/personnel-import/PersonnelImportPage';
import * as personnelApi from '../../../../src/api/personnel';

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
      role: 'HRAdmin',
      roles: ['HRAdmin'],
      org_unit_id: null,
      display_name: 'HR Admin',
    },
    isAuthenticated: true,
    isLoading: false,
  });
});

describe('PersonnelImportPage', () => {
  it('renders file upload zone and empty version history', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/personnel-imports', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <PersonnelImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('personnel_import.import_file'))).toBeInTheDocument();
      expect(screen.getByText(i18n.t('personnel_import.no_versions'))).toBeInTheDocument();
    });
  });

  it('shows PERS_004 row-level errors via ErrorDisplay', async () => {
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
            code: 'PERS_004',
            message: 'Batch validation failed',
            details: [{ row: 3, column: 'dept_id', code: 'PERS_001', reason: 'not in org tree' }],
          },
        },
        headers: new AxiosHeaders(),
        config: { headers: new AxiosHeaders() },
        statusText: 'Bad Request',
      } as AxiosResponse,
    );
    const spy = vi.spyOn(personnelApi, 'importPersonnel').mockRejectedValue(err);

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/personnel-imports', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <PersonnelImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('personnel_import.import_file'))).toBeInTheDocument();
    });

    const file = new File(['dept_id,account_code,amount\nD001,P001,1000'], 'data.csv', {
      type: 'text/csv',
    });
    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
    fireEvent.change(fileInput);

    await waitFor(
      () => {
        expect(screen.getByText('PERS_004')).toBeInTheDocument();
      },
      { timeout: 3000 },
    );

    spy.mockRestore();
  });

  it('shows loading indicator during import', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/personnel-imports', () => HttpResponse.json([])),
      http.post('*/cycles/*/personnel-imports', async () => {
        // Delay response to test loading state
        await new Promise((r) => setTimeout(r, 100));
        return HttpResponse.json(
          {
            id: 'cccccccc-1111-2222-3333-444444444444',
            cycle_id: OPEN_CYCLE.id,
            uploader_user_id: 'aaaaaaaa-1111-2222-3333-444444444444',
            uploaded_at: new Date().toISOString(),
            filename: 'data.csv',
            file_hash: 'abc123',
            version: 1,
            affected_org_units_summary: ['D001'],
          },
          { status: 201 },
        );
      }),
    );

    render(
      <Wrapper>
        <PersonnelImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('personnel_import.import_file'))).toBeInTheDocument();
    });

    const file = new File(['data'], 'data.csv', { type: 'text/csv' });
    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [file], configurable: true });
    fireEvent.change(fileInput);

    // Loading indicator should appear briefly
    expect(screen.getByText(i18n.t('common.loading'))).toBeInTheDocument();
  });

  it('shows no-cycle state when no open cycle', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <PersonnelImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('personnel_import.no_open_cycle'))).toBeInTheDocument();
    });
  });

  it('shows new version row after successful import', async () => {
    const importRecord = {
      id: 'cccccccc-2222-3333-4444-555555555555',
      cycle_id: OPEN_CYCLE.id,
      uploader_user_id: 'aaaaaaaa-1111-2222-3333-444444444444',
      uploaded_at: '2025-01-15T10:00:00Z',
      filename: 'personnel.csv',
      file_hash: 'abc12345def67890',
      version: 1,
      affected_org_units_summary: ['D001', 'D002'],
    };

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/personnel-imports', () => HttpResponse.json([importRecord])),
    );

    render(
      <Wrapper>
        <PersonnelImportPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('personnel.csv')).toBeInTheDocument();
    });

    // File hash truncated to 8 chars
    expect(screen.getByText('abc12345')).toBeInTheDocument();
  });
});
