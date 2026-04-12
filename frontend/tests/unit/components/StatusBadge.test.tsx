import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../src/i18n';
import { theme } from '../../../src/styles/theme';
import { StatusBadge } from '../../../src/components/StatusBadge';

/**
 * Test wrapper providing Mantine theme and i18n context.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider theme={theme}>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </MantineProvider>
  );
}

describe('StatusBadge', () => {
  it('renders uploaded status with correct label', () => {
    render(
      <Wrapper>
        <StatusBadge status="uploaded" />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('status.uploaded'))).toBeInTheDocument();
  });

  it('renders not_uploaded status with correct label', () => {
    render(
      <Wrapper>
        <StatusBadge status="not_uploaded" />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('status.not_uploaded'))).toBeInTheDocument();
  });

  it('renders resubmit status with correct label', () => {
    render(
      <Wrapper>
        <StatusBadge status="resubmit" />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('status.resubmit'))).toBeInTheDocument();
  });

  it('renders overdue status with correct label', () => {
    render(
      <Wrapper>
        <StatusBadge status="overdue" />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('status.overdue'))).toBeInTheDocument();
  });

  it('does not contain hardcoded hex color strings in rendered output', () => {
    const { container } = render(
      <Wrapper>
        <StatusBadge status="uploaded" />
      </Wrapper>,
    );
    const html = container.innerHTML;
    // These hex values should only exist in theme.ts, not in rendered DOM attributes
    expect(html).not.toContain('#16A34A');
    expect(html).not.toContain('#6B7280');
    expect(html).not.toContain('#D97706');
    expect(html).not.toContain('#DC2626');
  });
});
