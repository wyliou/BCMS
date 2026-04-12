import { Component, ErrorInfo, ReactNode } from 'react';
import { Alert, Text, Button } from '@mantine/core';
import i18n from '../i18n';

/**
 * Props for the ErrorBoundary component.
 */
interface ErrorBoundaryProps {
  /** Child components to render. */
  children: ReactNode;
  /** Optional custom fallback UI to display on error. */
  fallback?: ReactNode;
}

/**
 * Internal state for the ErrorBoundary.
 */
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

/**
 * ErrorBoundary catches unhandled React render errors in its subtree
 * and displays a fallback UI instead of crashing the application.
 *
 * Must be a class component — React 18 does not support hooks-based error boundaries.
 */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Reason: console.error is acceptable here per spec — browser devtools need the stack trace
    console.error('ErrorBoundary caught:', error, info);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <Alert color="red" title={i18n.t('errors.boundary_title')}>
          <Text>{i18n.t('errors.boundary_message')}</Text>
          <Button mt="sm" onClick={() => window.location.reload()}>
            {i18n.t('common.refresh')}
          </Button>
        </Alert>
      );
    }

    return this.props.children;
  }
}
