import { lazy, Suspense, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Center, Loader } from '@mantine/core';
import { RouteGuard } from '../components/RouteGuard';
import { ShellLayout } from '../components/ShellLayout';
import { useAuthStore } from '../stores/auth-store';

// Public pages (not lazy — lightweight)
import LoginPage from '../pages/auth/LoginPage';
import ForbiddenPage from '../pages/errors/ForbiddenPage';
import NotFoundPage from '../pages/errors/NotFoundPage';

// Lazy-loaded protected pages
const UploadPage = lazy(() => import('../pages/upload/UploadPage'));
const DashboardPage = lazy(() => import('../pages/dashboard/DashboardPage'));
const ConsolidatedReportPage = lazy(() => import('../pages/reports/ConsolidatedReportPage'));
const PersonnelImportPage = lazy(() => import('../pages/personnel-import/PersonnelImportPage'));
const SharedCostImportPage = lazy(() => import('../pages/shared-cost-import/SharedCostImportPage'));
const CycleAdminPage = lazy(() => import('../pages/admin/cycles/CycleAdminPage'));
const AccountMasterPage = lazy(() => import('../pages/admin/accounts/AccountMasterPage'));
const OrgTreePage = lazy(() => import('../pages/admin/org-units/OrgTreePage'));
const UserAdminPage = lazy(() => import('../pages/admin/users/UserAdminPage'));
const AuditLogPage = lazy(() => import('../pages/audit/AuditLogPage'));

/**
 * Centered loader displayed while lazy-loaded page chunks are fetched.
 *
 * @returns A centered spinner element.
 */
function PageLoader() {
  return (
    <Center h="100vh">
      <Loader />
    </Center>
  );
}

/**
 * AppRouter declares all application routes using React Router.
 * Initializes auth state on mount and lazy-loads protected pages.
 *
 * @returns The router tree with all routes.
 */
export default function AppRouter() {
  const { isAuthenticated, isLoading, fetchUser } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated && !isLoading) {
      fetchUser();
    }
    // Reason: Only run once on mount to initialize auth from cookies
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Suspense fallback={<PageLoader />}>
      <Routes>
        {/* Public routes */}
        <Route path="/" element={<LoginPage />} />
        <Route path="/403" element={<ForbiddenPage />} />

        {/* Protected routes inside ShellLayout */}
        <Route element={<ShellLayout />}>
          <Route
            path="/upload"
            element={
              <RouteGuard roles={['FilingUnitManager']}>
                <UploadPage />
              </RouteGuard>
            }
          />
          <Route
            path="/dashboard"
            element={
              <RouteGuard
                roles={['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin']}
              >
                <DashboardPage />
              </RouteGuard>
            }
          />
          <Route
            path="/reports"
            element={
              <RouteGuard
                roles={['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin']}
              >
                <ConsolidatedReportPage />
              </RouteGuard>
            }
          />
          <Route
            path="/personnel-import"
            element={
              <RouteGuard roles={['HRAdmin', 'SystemAdmin']}>
                <PersonnelImportPage />
              </RouteGuard>
            }
          />
          <Route
            path="/shared-cost-import"
            element={
              <RouteGuard roles={['FinanceAdmin', 'SystemAdmin']}>
                <SharedCostImportPage />
              </RouteGuard>
            }
          />
          <Route
            path="/admin/cycles"
            element={
              <RouteGuard roles={['FinanceAdmin', 'SystemAdmin']}>
                <CycleAdminPage />
              </RouteGuard>
            }
          />
          <Route
            path="/admin/accounts"
            element={
              <RouteGuard roles={['FinanceAdmin', 'SystemAdmin']}>
                <AccountMasterPage />
              </RouteGuard>
            }
          />
          <Route
            path="/admin/org-units"
            element={
              <RouteGuard roles={['SystemAdmin']}>
                <OrgTreePage />
              </RouteGuard>
            }
          />
          <Route
            path="/admin/users"
            element={
              <RouteGuard roles={['SystemAdmin']}>
                <UserAdminPage />
              </RouteGuard>
            }
          />
          <Route
            path="/audit"
            element={
              <RouteGuard roles={['ITSecurityAuditor', 'SystemAdmin']}>
                <AuditLogPage />
              </RouteGuard>
            }
          />
        </Route>

        {/* Catch-all 404 */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  );
}
