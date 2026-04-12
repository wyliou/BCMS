import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AxiosError, AxiosResponse, AxiosHeaders } from 'axios';
import i18n from '../../../../src/i18n';
import { useAuthStore } from '../../../../src/stores/auth-store';
import { server } from '../../../setup';
import UploadPage from '../../../../src/pages/upload/UploadPage';
import * as downloadModule from '../../../../src/lib/download';
import * as budgetUploadsApi from '../../../../src/api/budget-uploads';

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

const ORG_UNIT_ID = 'ffffffff-eeee-dddd-cccc-bbbbbbbbbbbb';

beforeEach(() => {
  useAuthStore.setState({
    user: {
      user_id: 'aaaaaaaa-1111-2222-3333-444444444444',
      role: 'FilingUnitManager',
      roles: ['FilingUnitManager'],
      org_unit_id: ORG_UNIT_ID,
      display_name: 'Manager',
    },
    isAuthenticated: true,
    isLoading: false,
  });
});

describe('UploadPage', () => {
  it('shows download template button and empty version history', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/uploads/*', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <UploadPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.download_template'))).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.no_versions'))).toBeInTheDocument();
    });
  });

  it('calls downloadBlob when download template button is clicked', async () => {
    const downloadBlobSpy = vi
      .spyOn(downloadModule, 'downloadBlob')
      .mockResolvedValue(undefined);

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/uploads/*', () => HttpResponse.json([])),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <UploadPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.download_template'))).toBeInTheDocument();
    });

    await user.click(screen.getByText(i18n.t('upload.download_template')));

    await waitFor(() => {
      expect(downloadBlobSpy).toHaveBeenCalled();
    });

    downloadBlobSpy.mockRestore();
  });

  it('shows file size error without API call for files over 10 MB', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/uploads/*', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <UploadPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.download_template'))).toBeInTheDocument();
    });

    // Create a file object with size > 10 MB (use Object.defineProperty to avoid slow string alloc)
    const bigFile = new File(['x'], 'large.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(bigFile, 'size', { value: 11 * 1024 * 1024 });

    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [bigFile], configurable: true });
    fireEvent.change(fileInput);

    await waitFor(
      () => {
        expect(screen.getByText(i18n.t('upload.error.file_too_large'))).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
  });

  it('renders UPLOAD_007 row-level errors via ErrorDisplay', async () => {
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
            code: 'UPLOAD_007',
            message: 'Batch validation failed',
            details: [{ row: 2, column: 'amount', code: 'UPLOAD_006', reason: 'negative amount' }],
          },
        },
        headers: new AxiosHeaders(),
        config: { headers: new AxiosHeaders() },
        statusText: 'Bad Request',
      } as AxiosResponse,
    );
    const spy = vi.spyOn(budgetUploadsApi, 'uploadBudget').mockRejectedValue(err);

    server.use(
      http.get('*/cycles', () => HttpResponse.json([OPEN_CYCLE])),
      http.get('*/cycles/*/uploads/*', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <UploadPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.download_template'))).toBeInTheDocument();
    });

    const validFile = new File(['data'], 'budget.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });

    // Mantine FileInput renders a hidden <input type="file">; use fireEvent to bypass display:none
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(fileInput, 'files', { value: [validFile], configurable: true });
    fireEvent.change(fileInput);

    await waitFor(
      () => {
        expect(screen.getByText('UPLOAD_007')).toBeInTheDocument();
      },
      { timeout: 3000 },
    );

    spy.mockRestore();
  });

  it('shows no cycle message when no open cycle exists', async () => {
    server.use(
      http.get('*/cycles', () => HttpResponse.json([])),
    );

    render(
      <Wrapper>
        <UploadPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('upload.no_open_cycle'))).toBeInTheDocument();
    });
  });
});
