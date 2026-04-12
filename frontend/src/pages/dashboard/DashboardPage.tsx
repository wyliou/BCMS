import { useState, useEffect, useCallback } from 'react';
import {
  Container,
  Stack,
  Group,
  Title,
  Select,
  Button,
  Alert,
  Anchor,
  Skeleton,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { useAuthStore } from '../../stores/auth-store';
import { useCycleSelector, useDashboard } from '../../features/consolidated-report/useDashboard';
import { DashboardItem } from '../../api/dashboard';
import { ResubmitModal } from '../../features/notifications/ResubmitModal';
import { SummaryCards } from './SummaryCards';
import { StatusGrid } from './StatusGrid';
import { FailedNotificationsPanel } from './FailedNotificationsPanel';

/**
 * DashboardPage shows the filing status dashboard for FinanceAdmin,
 * UplineReviewer, and CompanyReviewer roles.
 *
 * - Auto-selects the latest Open cycle on mount
 * - Polls every 5 seconds via useDashboard
 * - CompanyReviewer sees only a link to /reports
 * - FinanceAdmin sees failed notifications section
 *
 * @returns The dashboard page component.
 */
export default function DashboardPage() {
  const { t } = useTranslation();
  const { hasRole } = useAuthStore();

  const isCompanyReviewer = hasRole('CompanyReviewer');
  const isFinanceAdmin = hasRole('FinanceAdmin');
  const canResubmit = isFinanceAdmin || hasRole('UplineReviewer');

  // Reason: cycleId is page-local UI state, not global — per spec
  const [cycleId, setCycleId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [orgUnitSearch, setOrgUnitSearch] = useState('');
  const [resubmitItem, setResubmitItem] = useState<DashboardItem | null>(null);

  const { data: cycles, isLoading: cyclesLoading } = useCycleSelector();
  const {
    data: dashboard,
    isLoading: dashLoading,
    isError: dashError,
    error: dashErrorObj,
    refetch,
  } = useDashboard(cycleId, statusFilter);

  // Reason: Auto-select the latest Open cycle on mount when cycles load
  useEffect(() => {
    if (cycles && cycles.length > 0 && !cycleId) {
      const openCycle = cycles.find((c) => c.status === 'Open');
      setCycleId(openCycle?.id ?? cycles[0].id);
    }
  }, [cycles, cycleId]);

  const cycleOptions = (cycles ?? []).map((c) => ({
    value: c.id,
    label: `${c.fiscal_year} (${c.status})`,
  }));

  const handleStatusFilter = useCallback((status: string | undefined) => {
    setStatusFilter(status);
  }, []);

  const handleResubmit = useCallback((item: DashboardItem) => {
    setResubmitItem(item);
  }, []);

  // CompanyReviewer: no status grid, just a link to /reports
  if (isCompanyReviewer) {
    return (
      <Container size="lg" py="xl">
        <Stack gap="lg">
          <Title order={2}>{t('nav.dashboard')}</Title>
          <Alert color="blue">
            {t('dashboard.company_reviewer.report_link')}{' '}
            <Anchor component={Link} to="/reports">
              {t('nav.reports')}
            </Anchor>
          </Alert>
        </Stack>
      </Container>
    );
  }

  const isLoading = cyclesLoading || dashLoading;
  const isStale = dashboard?.data_freshness?.stale === true;

  // No open cycle available
  if (!cyclesLoading && cycles && cycles.length === 0) {
    return (
      <Container size="lg" py="xl">
        <Stack gap="lg">
          <Title order={2}>{t('nav.dashboard')}</Title>
          <Alert color="yellow">{t('dashboard.no_cycle.prompt')}</Alert>
        </Stack>
      </Container>
    );
  }

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between">
          <Title order={2}>{t('nav.dashboard')}</Title>
          <Group>
            {cyclesLoading ? (
              <Skeleton width={200} height={36} />
            ) : (
              <Select
                data={cycleOptions}
                value={cycleId}
                onChange={(val) => {
                  setCycleId(val);
                  setStatusFilter(undefined);
                  setOrgUnitSearch('');
                }}
                aria-label={t('dashboard.cycle_selector')}
                w={200}
              />
            )}
            <Button variant="default" onClick={() => refetch()}>
              {t('common.refresh')}
            </Button>
          </Group>
        </Group>

        {/* Stale data banner */}
        {isStale && <Alert color="yellow">{t('dashboard.freshness.stale')}</Alert>}

        {/* Error state */}
        {dashError && <ErrorDisplay error={dashErrorObj} />}

        {/* Summary cards */}
        <SummaryCards
          summary={dashboard?.summary}
          isLoading={isLoading}
          onStatusFilter={handleStatusFilter}
        />

        {/* Status grid */}
        <StatusGrid
          items={dashboard?.items ?? []}
          isLoading={dashLoading}
          statusFilter={statusFilter}
          onStatusFilterChange={handleStatusFilter}
          orgUnitSearch={orgUnitSearch}
          onOrgUnitSearchChange={setOrgUnitSearch}
          canResubmit={canResubmit}
          onResubmit={handleResubmit}
        />

        {/* Failed notifications (FinanceAdmin only) */}
        <FailedNotificationsPanel enabled={isFinanceAdmin} />

        {/* Resubmit modal */}
        {resubmitItem && cycleId && (
          <ResubmitModal
            opened={!!resubmitItem}
            onClose={() => setResubmitItem(null)}
            cycleId={cycleId}
            orgUnitId={resubmitItem.org_unit_id}
            orgUnitName={resubmitItem.org_unit_name}
            recipientUserId={resubmitItem.recipient_user_id}
            recipientEmail={resubmitItem.recipient_email}
            latestVersion={resubmitItem.version}
          />
        )}
      </Stack>
    </Container>
  );
}
