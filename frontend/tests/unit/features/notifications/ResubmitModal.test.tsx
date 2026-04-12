import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n from '../../../../src/i18n';
import { useAuthStore } from '../../../../src/stores/auth-store';
import { server } from '../../../setup';
import { ResubmitModal } from '../../../../src/features/notifications/ResubmitModal';

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

const CYCLE_ID = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';
const ORG_UNIT_ID = 'bbbbbbbb-cccc-dddd-eeee-ffffffffffff';
const REQUESTER_ID = 'cccccccc-dddd-eeee-ffff-000000000000';

const MODAL_PROPS = {
  opened: true,
  onClose: () => {},
  cycleId: CYCLE_ID,
  orgUnitId: ORG_UNIT_ID,
  orgUnitName: 'Test Unit',
  recipientUserId: 'dddddddd-eeee-ffff-0000-111111111111',
  recipientEmail: 'manager@example.com',
  latestVersion: 3,
};

beforeEach(() => {
  useAuthStore.setState({
    user: {
      user_id: REQUESTER_ID,
      role: 'FinanceAdmin',
      roles: ['FinanceAdmin'],
      org_unit_id: null,
      display_name: 'Finance Admin',
    },
    isAuthenticated: true,
    isLoading: false,
  });

  server.use(
    http.get('*/resubmit-requests', () => HttpResponse.json([])),
  );
});

describe('ResubmitModal', () => {
  it('renders form with reason textarea and target_version input', async () => {
    render(
      <Wrapper>
        <ResubmitModal {...MODAL_PROPS} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('resubmit.reason_label'))).toBeInTheDocument();
      expect(screen.getByText(i18n.t('resubmit.target_version_label'))).toBeInTheDocument();
    });
  });

  it('submits createResubmitRequest with requester_user_id from auth store', async () => {
    let requestBody: Record<string, unknown> | null = null;
    server.use(
      http.post('*/resubmit-requests', async ({ request }) => {
        requestBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: 'eeeeeeee-ffff-0000-1111-222222222222',
            cycle_id: CYCLE_ID,
            org_unit_id: ORG_UNIT_ID,
            requester_id: REQUESTER_ID,
            target_version: 3,
            reason: 'Need resubmit',
            requested_at: new Date().toISOString(),
          },
          { status: 201 },
        );
      }),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <ResubmitModal {...MODAL_PROPS} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText(i18n.t('resubmit.reason_placeholder'))).toBeInTheDocument();
    });

    const reasonInput = screen.getByPlaceholderText(i18n.t('resubmit.reason_placeholder'));
    await user.type(reasonInput, 'Need resubmit');
    await user.click(screen.getByText(i18n.t('resubmit.submit')));

    await waitFor(() => {
      expect(requestBody).not.toBeNull();
      expect(requestBody?.requester_user_id).toBe(REQUESTER_ID);
      expect(requestBody?.reason).toBe('Need resubmit');
    });
  });

  it('shows ErrorDisplay on NOTIFY_002 error', async () => {
    server.use(
      http.post('*/resubmit-requests', () =>
        HttpResponse.json(
          { error: { code: 'NOTIFY_002', message: 'Audit log write failed' } },
          { status: 500 },
        ),
      ),
    );

    const user = userEvent.setup();
    render(
      <Wrapper>
        <ResubmitModal {...MODAL_PROPS} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText(i18n.t('resubmit.reason_placeholder'))).toBeInTheDocument();
    });

    await user.type(
      screen.getByPlaceholderText(i18n.t('resubmit.reason_placeholder')),
      'Some reason',
    );
    await user.click(screen.getByText(i18n.t('resubmit.submit')));

    await waitFor(() => {
      expect(screen.getByText('NOTIFY_002')).toBeInTheDocument();
    });
  });

  it('shows history of past requests in history section', async () => {
    server.use(
      http.get('*/resubmit-requests', () =>
        HttpResponse.json([
          {
            id: 'eeeeeeee-1111-2222-3333-444444444444',
            cycle_id: CYCLE_ID,
            org_unit_id: ORG_UNIT_ID,
            requester_id: REQUESTER_ID,
            target_version: 2,
            reason: 'First resubmit reason',
            requested_at: '2025-01-10T09:00:00Z',
          },
          {
            id: 'eeeeeeee-5555-6666-7777-888888888888',
            cycle_id: CYCLE_ID,
            org_unit_id: ORG_UNIT_ID,
            requester_id: REQUESTER_ID,
            target_version: null,
            reason: 'Second resubmit reason',
            requested_at: '2025-01-15T09:00:00Z',
          },
        ]),
      ),
    );

    render(
      <Wrapper>
        <ResubmitModal {...MODAL_PROPS} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText('First resubmit reason')).toBeInTheDocument();
      expect(screen.getByText('Second resubmit reason')).toBeInTheDocument();
    });
  });

  it('shows validation error when submitting empty reason', async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <ResubmitModal {...MODAL_PROPS} />
      </Wrapper>,
    );

    await waitFor(() => {
      expect(screen.getByText(i18n.t('resubmit.submit'))).toBeInTheDocument();
    });

    // Submit without filling reason
    await user.click(screen.getByText(i18n.t('resubmit.submit')));

    await waitFor(() => {
      expect(
        screen.getByText(i18n.t('resubmit.error.reason_required')),
      ).toBeInTheDocument();
    });
  });
});
