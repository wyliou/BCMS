import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { MantineProvider } from '@mantine/core';
import { RouteGuard } from '../../../src/components/RouteGuard';
import { useAuthStore } from '../../../src/stores/auth-store';

/**
 * Wrapper that provides routing and Mantine context for tests.
 */
function TestWrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <MemoryRouter>{children}</MemoryRouter>
    </MantineProvider>
  );
}

describe('RouteGuard', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });

  it('renders a spinner when isLoading is true', () => {
    useAuthStore.setState({ isLoading: true });

    render(
      <TestWrapper>
        <RouteGuard roles={['FinanceAdmin']}>
          <div data-testid="protected">Protected Content</div>
        </RouteGuard>
      </TestWrapper>,
    );

    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
    // Mantine Loader renders an SVG with role="presentation" or a span
    expect(document.querySelector('.mantine-Loader-root')).toBeInTheDocument();
  });

  it('redirects to / when not authenticated', () => {
    useAuthStore.setState({ isAuthenticated: false, isLoading: false });

    render(
      <TestWrapper>
        <RouteGuard roles={['FinanceAdmin']}>
          <div data-testid="protected">Protected Content</div>
        </RouteGuard>
      </TestWrapper>,
    );

    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
  });

  it('renders children when user has a matching role', () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        role: 'FinanceAdmin',
        roles: ['FinanceAdmin'],
        org_unit_id: null,
        display_name: 'Test',
      },
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <TestWrapper>
        <RouteGuard roles={['FinanceAdmin']}>
          <div data-testid="protected">Protected Content</div>
        </RouteGuard>
      </TestWrapper>,
    );

    expect(screen.getByTestId('protected')).toBeInTheDocument();
  });

  it('redirects to /403 when user has no matching role', () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        role: 'HRAdmin',
        roles: ['HRAdmin'],
        org_unit_id: null,
        display_name: 'Test',
      },
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <TestWrapper>
        <RouteGuard roles={['SystemAdmin']}>
          <div data-testid="protected">Protected Content</div>
        </RouteGuard>
      </TestWrapper>,
    );

    expect(screen.queryByTestId('protected')).not.toBeInTheDocument();
  });

  it('grants access when user has one of multiple allowed roles', () => {
    useAuthStore.setState({
      user: {
        user_id: '550e8400-e29b-41d4-a716-446655440000',
        role: 'FinanceAdmin',
        roles: ['FinanceAdmin'],
        org_unit_id: null,
        display_name: 'Test',
      },
      isAuthenticated: true,
      isLoading: false,
    });

    render(
      <TestWrapper>
        <RouteGuard roles={['FinanceAdmin', 'SystemAdmin']}>
          <div data-testid="protected">Protected Content</div>
        </RouteGuard>
      </TestWrapper>,
    );

    expect(screen.getByTestId('protected')).toBeInTheDocument();
  });
});
