import { useState } from 'react';
import { Stack, Title, Button, Group, Paper, Text, Skeleton, FileInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { AxiosError } from 'axios';
import { useQuery } from '@tanstack/react-query';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { DataTable } from '../../components/DataTable';
import { RouteGuard } from '../../components/RouteGuard';
import { listCycles } from '../../api/cycles';
import { useSharedCostImport } from '../../features/shared-cost-import/useSharedCostImport';
import { SharedCostUploadRead } from '../../api/shared-costs';

/**
 * SharedCostImportPage allows FinanceAdmins to upload CSV/XLSX shared cost files
 * for the current open cycle and view import version history.
 *
 * @returns The shared cost import page component.
 */
export default function SharedCostImportPage() {
  const { t } = useTranslation();
  const [importError, setImportError] = useState<AxiosError | null>(null);

  // Resolve the current open cycle
  const cycleQuery = useQuery({
    queryKey: ['cycles', { status: 'Open' }],
    queryFn: () => listCycles({ status: 'Open' }),
    staleTime: 60000,
  });

  const openCycle = cycleQuery.data?.[0] ?? null;
  const cycleId = openCycle?.id ?? null;

  const { versionsQuery, importMutation } = useSharedCostImport(cycleId);

  const handleFileChange = (file: File | null) => {
    if (!file || !cycleId) return;
    setImportError(null);

    importMutation.mutate(
      { cycleId, file },
      {
        onSuccess: () => {
          notifications.show({ message: t('shared_cost_import.import_success'), color: 'green' });
        },
        onError: (err) => {
          setImportError(err);
        },
      },
    );
  };

  // Version history table columns
  const columns: ColumnDef<SharedCostUploadRead, unknown>[] = [
    {
      accessorKey: 'version',
      header: t('shared_cost_import.table.version'),
    },
    {
      accessorKey: 'uploaded_at',
      header: t('shared_cost_import.table.uploaded_at'),
      cell: ({ getValue }) => new Date(getValue() as string).toLocaleString('zh-TW'),
    },
    {
      accessorKey: 'filename',
      header: t('shared_cost_import.table.filename'),
    },
    {
      accessorKey: 'affected_org_units_summary',
      header: t('shared_cost_import.table.affected_units'),
      cell: ({ getValue }) => {
        const units = getValue() as string[];
        if (units.length <= 5) return units.join(', ');
        return `${units.slice(0, 5).join(', ')} ... (+${units.length - 5})`;
      },
    },
  ];

  const noCycle = !cycleQuery.isLoading && !openCycle;
  const fileInputDisabled = !cycleId || importMutation.isPending;
  const fileInputErrorId = importError ? 'shared-cost-import-file-error' : undefined;

  return (
    <RouteGuard roles={['FinanceAdmin']}>
      <Stack gap="md" p="md">
        <Group justify="space-between">
          <Title order={2}>{t('shared_cost_import.page_title')}</Title>
          <Button
            variant="subtle"
            size="xs"
            onClick={() => versionsQuery.refetch()}
            aria-label={t('shared_cost_import.manual_refresh')}
          >
            {t('shared_cost_import.manual_refresh')}
          </Button>
        </Group>

        {/* Loading state */}
        {cycleQuery.isLoading && <Skeleton height={60} />}

        {/* No open cycle state */}
        {noCycle && (
          <Paper p="xl" withBorder>
            <Text c="dimmed" ta="center">
              {t('shared_cost_import.no_open_cycle')}
            </Text>
          </Paper>
        )}

        {openCycle && (
          <Stack gap="md">
            {/* File upload zone */}
            <Paper p="md" withBorder>
              <Stack gap="xs">
                <Text size="sm" c="dimmed">
                  {t('shared_cost_import.file_hint')}
                </Text>
                <FileInput
                  label={t('shared_cost_import.import_file')}
                  accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={handleFileChange}
                  disabled={fileInputDisabled}
                  aria-describedby={fileInputErrorId}
                />
                {importMutation.isPending && (
                  <Text size="sm" c="dimmed">
                    {t('common.loading')}
                  </Text>
                )}
                {importError && <ErrorDisplay error={importError} />}
              </Stack>
            </Paper>

            {/* Version history */}
            <Paper p="md" withBorder>
              <Title order={4} mb="sm">
                {t('shared_cost_import.version_history')}
              </Title>
              {versionsQuery.isLoading ? (
                <Skeleton height={120} />
              ) : versionsQuery.isError ? (
                <ErrorDisplay error={versionsQuery.error as AxiosError} />
              ) : (
                <DataTable
                  data={versionsQuery.data ?? []}
                  columns={columns}
                  emptyMessage="shared_cost_import.no_versions"
                  aria-label={t('shared_cost_import.version_history')}
                  enablePagination={false}
                />
              )}
            </Paper>
          </Stack>
        )}
      </Stack>
    </RouteGuard>
  );
}
