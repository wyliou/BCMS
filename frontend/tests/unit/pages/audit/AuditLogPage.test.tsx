import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import i18n from '../../../../src/i18n';
import AuditLogPage from '../../../../src/pages/audit/AuditLogPage';
import * as auditApi from '../../../../src/api/audit';

/**
 * Test wrapper providing Mantine, i18n, and React Query context.
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

describe('AuditLogPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders filter form and loading skeleton on initial load', async () => {
    vi.spyOn(auditApi, 'queryAuditLogs').mockImplementation(
      () => new Promise(() => {}), // Never resolves
    );

    render(
      <Wrapper>
        <AuditLogPage />
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('audit.form.user_id'))).toBeInTheDocument();
    expect(screen.getByText(i18n.t('audit.buttons.search'))).toBeInTheDocument();
  });

  it('displays paginated audit logs on success', async () => {
    const mockLogs = {
      items: [
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          user_id: '550e8400-e29b-41d4-a716-446655440002',
          action: 'budget_upload.accepted',
          resource_type: 'budget',
          resource_id: '550e8400-e29b-41d4-a716-446655440003',
          ip_address: '192.168.1.1',
          timestamp: '2026-04-12T10:00:00Z',
          details: null,
        },
      ],
      total: 1,
      page: 1,
      size: 50,
    };

    vi.spyOn(auditApi, 'queryAuditLogs').mockResolvedValue(mockLogs);

    render(
      <Wrapper>
        <AuditLogPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('budget_upload.accepted')).toBeInTheDocument();
    });
  });

  it('shows empty state when no logs are found', async () => {
    vi.spyOn(auditApi, 'queryAuditLogs').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
    });

    render(
      <Wrapper>
        <AuditLogPage />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('audit.empty.no_results'))).toBeInTheDocument();
    });
  });

  it('disables export button when date range is not set', async () => {
    vi.spyOn(auditApi, 'queryAuditLogs').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
    });

    render(
      <Wrapper>
        <AuditLogPage />
      </Wrapper>,
    );

    await waitFor(() => {
      const exportButton = screen.getByText(i18n.t('audit.buttons.export'));
      expect(exportButton.closest('button')).toBeDisabled();
    });
  });

  it('calls verifyChain mutation when verify button is clicked', async () => {
    const verifySpy = vi.spyOn(auditApi, 'verifyChain').mockResolvedValue({
      verified: true,
      range: ['2026-04-01T00:00:00Z', '2026-04-12T23:59:59Z'],
      chain_length: 100,
    });

    vi.spyOn(auditApi, 'queryAuditLogs').mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      size: 50,
    });

    render(
      <Wrapper>
        <AuditLogPage />
      </Wrapper>,
    );

    const fromInput = screen.getByLabelText(i18n.t('audit.form.from'));
    const toInput = screen.getByLabelText(i18n.t('audit.form.to'));

    await userEvent.type(fromInput, '2026-04-01T00:00');
    await userEvent.type(toInput, '2026-04-12T23:59');

    const verifyButton = screen.getByText(i18n.t('audit.buttons.verify'));
    await userEvent.click(verifyButton);

    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalled();
    });
  });
});
