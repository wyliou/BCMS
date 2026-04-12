import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { BrowserRouter } from 'react-router-dom';
import i18n from './i18n';
import { theme } from './styles/theme';
import { QueryProvider } from './providers/QueryProvider';
import { ErrorBoundary } from './components/ErrorBoundary';
import AppRouter from './routes';

import '@mantine/core/styles.css';

/**
 * Root application component that wires all providers together.
 * Provider order (outermost to innermost):
 * ErrorBoundary > MantineProvider > I18nextProvider > QueryProvider > BrowserRouter > AppRouter
 *
 * @returns The fully wired application tree.
 */
export default function App() {
  return (
    <ErrorBoundary>
      <MantineProvider theme={theme}>
        <I18nextProvider i18n={i18n}>
          <QueryProvider>
            <BrowserRouter>
              <AppRouter />
            </BrowserRouter>
          </QueryProvider>
        </I18nextProvider>
      </MantineProvider>
    </ErrorBoundary>
  );
}
