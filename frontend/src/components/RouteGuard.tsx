import { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { useAuthStore } from '../stores/auth-store';

/**
 * Props for the RouteGuard component.
 */
interface RouteGuardProps {
  /** Required roles — access is granted if the user has at least one. */
  roles: string[];
  /** Child content to render when access is granted. */
  children: ReactNode;
}

/**
 * RouteGuard wraps protected routes and checks the auth store for required roles.
 * - Loading: renders a spinner (no redirect).
 * - Not authenticated: redirects to / (login).
 * - Authenticated but wrong role: redirects to /403.
 * - Authorized: renders children.
 *
 * Empty roles array means any authenticated user has access.
 *
 * @param props - The guard props.
 * @returns The guarded content or a redirect/spinner.
 */
export function RouteGuard({ roles, children }: RouteGuardProps) {
  const { isLoading, isAuthenticated, hasAnyRole } = useAuthStore();

  if (isLoading) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  // Reason: empty roles array = any authenticated user is allowed
  if (roles.length > 0 && !hasAnyRole(...roles)) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
