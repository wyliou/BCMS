import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import i18n from '../../../../src/i18n';
import NotFoundPage from '../../../../src/pages/errors/NotFoundPage';

/**
 * Wrapper for NotFoundPage tests.
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

describe('NotFoundPage', () => {
  it('renders the 404 heading', () => {
    render(
      <Wrapper>
        <NotFoundPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.not_found_title'))).toBeInTheDocument();
  });

  it('renders the not found message', () => {
    render(
      <Wrapper>
        <NotFoundPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.not_found_message'))).toBeInTheDocument();
  });

  it('renders the back-to-home button', () => {
    render(
      <Wrapper>
        <NotFoundPage />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('errors.back_home'))).toBeInTheDocument();
  });

  it('heading is an h1 element', () => {
    render(
      <Wrapper>
        <NotFoundPage />
      </Wrapper>,
    );
    const heading = screen.getByText(i18n.t('errors.not_found_title'));
    expect(heading.tagName).toBe('H1');
  });
});
