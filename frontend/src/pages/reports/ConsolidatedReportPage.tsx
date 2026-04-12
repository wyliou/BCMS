import { useState, useEffect, useMemo } from 'react';
import {
  Container,
  Stack,
  Group,
  Title,
  Select,
  Button,
  Alert,
  Text,
  Skeleton,
  Menu,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { DataTable } from '../../components/DataTable';
import { useCycleSelector } from '../../features/consolidated-report/useDashboard';
import {
  useConsolidatedReport,
  useStartExport,
} from '../../features/consolidated-report/useConsolidatedReport';
import { buildReportColumns } from '../../features/consolidated-report/reportColumns';
import { downloadBlob, pollAndDownload } from '../../lib/download';
import { formatLocalDateTime } from '../../lib/format-date';
import { ConsolidatedReportRow } from '../../api/reports';
import { ColumnDef } from '@tanstack/react-table';

/**
 * ConsolidatedReportPage displays the multi-source consolidated report
 * with three column groups (operational, personnel, shared cost) and export controls.
 *
 * @returns The consolidated report page component.
 */
export default function ConsolidatedReportPage() {
  const { t } = useTranslation();

  const [cycleId, setCycleId] = useState<string | null>(null);
  const [exportError, setExportError] = useState<Error | null>(null);

  const { data: cycles, isLoading: cyclesLoading } = useCycleSelector();
  const {
    data: report,
    isLoading: reportLoading,
    isError: reportError,
    error: reportErrorObj,
    refetch,
  } = useConsolidatedReport(cycleId);

  const exportMutation = useStartExport();

  // Reason: Auto-select the latest Open cycle on mount
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

  // Reason: Cast needed because column groups use ColumnDef<T> (any value type)
  // while DataTable expects ColumnDef<T, unknown>
  const columns = useMemo(
    () => buildReportColumns(t) as ColumnDef<ConsolidatedReportRow, unknown>[],
    [t],
  );

  const handleExport = async (format: 'xlsx' | 'csv') => {
    if (!cycleId) return;
    setExportError(null);
    try {
      const result = await exportMutation.mutateAsync({ cycleId, format });
      if (result.mode === 'sync') {
        const ext = format === 'xlsx' ? 'xlsx' : 'csv';
        await downloadBlob(result.file_url, `report.${ext}`);
      } else {
        const pollUrl = `/exports/${result.job_id}`;
        const fileUrl = `/exports/${result.job_id}/file`;
        await pollAndDownload(pollUrl, fileUrl);
      }
    } catch (err) {
      setExportError(err instanceof Error ? err : new Error(String(err)));
    }
  };

  const isLoading = cyclesLoading || reportLoading;
  const isExporting = exportMutation.isPending;

  return (
    <Container size="xl" py="xl">
      <Stack gap="lg">
        {/* Header */}
        <Group justify="space-between">
          <Title order={2}>{t('nav.reports')}</Title>
          <Group>
            {cyclesLoading ? (
              <Skeleton width={200} height={36} />
            ) : (
              <Select
                data={cycleOptions}
                value={cycleId}
                onChange={(val) => setCycleId(val)}
                aria-label={t('report.cycle_selector')}
                w={200}
              />
            )}
            <Button variant="default" onClick={() => refetch()}>
              {t('common.refresh')}
            </Button>
            <Menu>
              <Menu.Target>
                <Button loading={isExporting} disabled={isExporting || !cycleId}>
                  {t('report.export.button')}
                </Button>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Item onClick={() => handleExport('xlsx')}>
                  {t('report.export.xlsx')}
                </Menu.Item>
                <Menu.Item onClick={() => handleExport('csv')}>{t('report.export.csv')}</Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Group>

        {/* Export error */}
        {exportError && (
          <Alert color="red">
            <Group justify="space-between">
              <Text>{exportError.message}</Text>
              <Button size="xs" variant="subtle" onClick={() => setExportError(null)}>
                {t('common.retry')}
              </Button>
            </Group>
          </Alert>
        )}

        {/* Error state */}
        {reportError && <ErrorDisplay error={reportErrorObj} />}

        {/* Metadata header */}
        {report && (
          <Group gap="lg">
            <Text size="sm" c="dimmed">
              {t('report.metadata.currency')}: {report.reporting_currency}
            </Text>
            <Text size="sm" c="dimmed">
              {t('report.metadata.budget_updated')}:{' '}
              {formatLocalDateTime(report.budget_last_updated_at)}
            </Text>
            <Text size="sm" c="dimmed">
              {t('report.metadata.personnel_updated')}:{' '}
              {formatLocalDateTime(report.personnel_last_updated_at)}
            </Text>
            <Text size="sm" c="dimmed">
              {t('report.metadata.shared_cost_updated')}:{' '}
              {formatLocalDateTime(report.shared_cost_last_updated_at)}
            </Text>
          </Group>
        )}

        {/* Data table */}
        {!reportError && (
          <DataTable<ConsolidatedReportRow>
            data={report?.rows ?? []}
            columns={columns}
            isLoading={isLoading}
            emptyMessage="report.empty"
            enableSorting={true}
            aria-label={t('report.table.label')}
          />
        )}
      </Stack>
    </Container>
  );
}
