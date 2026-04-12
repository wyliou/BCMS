import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { AxiosError, AxiosHeaders } from 'axios';
import i18n from '../../../src/i18n';
import { ErrorDisplay } from '../../../src/components/ErrorDisplay';

/**
 * Test wrapper providing Mantine and i18n context.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </MantineProvider>
  );
}

/**
 * Helper to create an AxiosError with a specific response data shape.
 */
function makeAxiosError(data: unknown, status = 400): AxiosError {
  const error = new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, undefined, {
    data,
    status,
    statusText: 'Bad Request',
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
  return error;
}

describe('ErrorDisplay', () => {
  it('returns null when error is null', () => {
    render(
      <Wrapper>
        <ErrorDisplay error={null} />
      </Wrapper>,
    );
    // Reason: MantineProvider injects <style> tags, so check for Alert absence instead
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('renders network error message for non-Axios errors', () => {
    const error = new Error('Network failure');
    render(
      <Wrapper>
        <ErrorDisplay error={error} />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.network_error'))).toBeInTheDocument();
  });

  it('renders error code and message from envelope', () => {
    const error = makeAxiosError({
      error: { code: 'UPLOAD_007', message: 'Validation failed' },
    });
    render(
      <Wrapper>
        <ErrorDisplay error={error} />
      </Wrapper>,
    );
    expect(screen.getByText('UPLOAD_007')).toBeInTheDocument();
    expect(screen.getByText('Validation failed')).toBeInTheDocument();
  });

  it('shows detail toggle and expands row-level errors', async () => {
    const user = userEvent.setup();
    const error = makeAxiosError({
      error: {
        code: 'UPLOAD_007',
        message: 'Validation failed',
        details: [{ row: 1, column: 'amount', code: 'INVALID', reason: 'Bad value' }],
      },
    });

    render(
      <Wrapper>
        <ErrorDisplay error={error} />
      </Wrapper>,
    );

    const toggleBtn = screen.getByText(i18n.t('errors.show_details'));
    expect(toggleBtn).toBeInTheDocument();

    await user.click(toggleBtn);
    expect(screen.getByText('Bad value')).toBeInTheDocument();
  });

  it('renders request_id when present', () => {
    const error = makeAxiosError({
      error: { code: 'ERR', message: 'Fail' },
      request_id: 'req-123',
    });

    render(
      <Wrapper>
        <ErrorDisplay error={error} />
      </Wrapper>,
    );

    expect(screen.getByText(/req-123/)).toBeInTheDocument();
  });
});
