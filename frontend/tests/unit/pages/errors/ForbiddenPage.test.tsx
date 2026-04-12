import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../../src/i18n';
import ForbiddenPage from '../../../../src/pages/errors/ForbiddenPage';

/**
 * Wrapper for ForbiddenPage tests.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter>{children}</MemoryRouter>
      </I18nextProvider>
    </MantineProvider>
  );
}

describe('ForbiddenPage', () => {
  it('renders the 403 heading', () => {
    render(
      <Wrapper>
        <ForbiddenPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.forbidden_title'))).toBeInTheDocument();
  });

  it('renders the forbidden message', () => {
    render(
      <Wrapper>
        <ForbiddenPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.forbidden_message'))).toBeInTheDocument();
  });

  it('renders the back-to-home button', () => {
    render(
      <Wrapper>
        <ForbiddenPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.back_home'))).toBeInTheDocument();
  });

  it('does not render a retry button or spinner', () => {
    render(
      <Wrapper>
        <ForbiddenPage />
      </Wrapper>,
    );
    expect(screen.queryByText(i18n.t('common.retry'))).not.toBeInTheDocument();
    expect(document.querySelector('.mantine-Loader-root')).not.toBeInTheDocument();
  });
});
