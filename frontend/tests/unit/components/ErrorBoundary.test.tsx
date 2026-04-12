import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../src/i18n';
import { ErrorBoundary } from '../../../src/components/ErrorBoundary';

/**
 * Component that throws during render for testing error boundaries.
 */
function ThrowingChild(): React.ReactNode {
  throw new Error('Test error');
}

/**
 * Wrapper providing theme and i18n for ErrorBoundary tests.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </MantineProvider>
  );
}

describe('ErrorBoundary', () => {
  // Suppress React error boundary console output during tests
  const originalError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it('renders children normally when no error occurs', () => {
    render(
      <Wrapper>
        <ErrorBoundary>
          <div data-testid="child">OK</div>
        </ErrorBoundary>
      </Wrapper>,
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('displays fallback UI when a child throws during render', () => {
    render(
      <Wrapper>
        <ErrorBoundary>
          <ThrowingChild />
        </ErrorBoundary>
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('errors.boundary_title'))).toBeInTheDocument();
  });

  it('renders the refresh button in fallback UI', () => {
    render(
      <Wrapper>
        <ErrorBoundary>
          <ThrowingChild />
        </ErrorBoundary>
      </Wrapper>,
    );

    expect(screen.getByText(i18n.t('common.refresh'))).toBeInTheDocument();
  });

  it('renders custom fallback when provided', () => {
    render(
      <Wrapper>
        <ErrorBoundary fallback={<div data-testid="custom">Custom Fallback</div>}>
          <ThrowingChild />
        </ErrorBoundary>
      </Wrapper>,
    );

    expect(screen.getByTestId('custom')).toBeInTheDocument();
  });
});
