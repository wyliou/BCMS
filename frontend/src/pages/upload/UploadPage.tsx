import { useState } from 'react';
import { Stack, Title, Button, Group, Paper, Text, Skeleton, FileInput } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { AxiosError } from 'axios';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/auth-store';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { StatusBadge, UploadStatus } from '../../components/StatusBadge';
import { DataTable } from '../../components/DataTable';
import { RouteGuard } from '../../components/RouteGuard';
import { downloadTemplate } from '../../api/templates';
import { useBudgetUpload } from '../../features/budget-uploads/useBudgetUpload';
import { listCycles } from '../../api/cycles';
import { BudgetUploadRead } from '../../api/budget-uploads';

/** Maximum allowed file size in bytes (10 MB). */
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024;

/**
 * Formats a byte count to a human-readable string.
 *
 * @param bytes - Number of bytes.
 * @returns Human-readable file size string.
 */
function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Maps BudgetUploadRead status to UploadStatus badge value.
 *
 * @param status - The API status string.
 * @returns The UploadStatus badge value.
 */
function toUploadStatus(status: BudgetUploadRead['status'] | 'not_uploaded'): UploadStatus {
  if (status === 'Valid') return 'uploaded';
  return 'not_uploaded';
}

/**
 * UploadPage allows FilingUnitManagers to download their budget template
 * and upload their completed budget Excel file for the current open cycle.
 *
 * @returns The upload page component.
 */
export default function UploadPage() {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);
  const orgUnitId = user?.org_unit_id ?? null;

  const [uploadError, setUploadError] = useState<AxiosError | null>(null);
  const [fileSizeError, setFileSizeError] = useState<string | null>(null);
  const [templateError, setTemplateError] = useState<string | null>(null);

  // Resolve the current open cycle
  const cycleQuery = useQuery({
    queryKey: ['cycles', { status: 'Open' }],
    queryFn: () => listCycles({ status: 'Open' }),
    staleTime: 60000,
  });

  const openCycle = cycleQuery.data?.[0] ?? null;
  const cycleId = openCycle?.id ?? null;

  const { versionsQuery, uploadMutation } = useBudgetUpload(cycleId, orgUnitId);

  const latestVersion = versionsQuery.data?.[0] ?? null;
  const currentStatus: UploadStatus = latestVersion
    ? toUploadStatus(latestVersion.status)
    : 'not_uploaded';

  const handleDownloadTemplate = async () => {
    if (!cycleId || !orgUnitId) return;
    setTemplateError(null);
    try {
      await downloadTemplate(cycleId, orgUnitId, `budget-template-${cycleId}.xlsx`);
    } catch (err) {
      const axErr = err as AxiosError<{ error?: { code?: string } }>;
      if (axErr.response?.data?.error?.code === 'TPL_002') {
        setTemplateError(t('upload.error.template_not_found'));
      } else {
        setTemplateError(t('errors.network_error'));
      }
    }
  };

  const handleFileChange = (file: File | null) => {
    if (!file) return;
    setFileSizeError(null);
    setUploadError(null);

    // Client-side size check before API call
    if (file.size > MAX_FILE_SIZE_BYTES) {
      setFileSizeError(t('upload.error.file_too_large'));
      return;
    }

    if (!cycleId || !orgUnitId) return;

    uploadMutation.mutate(
      { cycleId, orgUnitId, file },
      {
        onSuccess: () => {
          notifications.show({ message: t('upload.upload_success'), color: 'green' });
        },
        onError: (err) => {
          setUploadError(err);
        },
      },
    );
  };

  // Version history table columns
  const columns: ColumnDef<BudgetUploadRead, unknown>[] = [
    {
      accessorKey: 'version',
      header: t('upload.table.version'),
    },
    {
      accessorKey: 'uploaded_at',
      header: t('upload.table.uploaded_at'),
      cell: ({ getValue }) => new Date(getValue() as string).toLocaleString('zh-TW'),
    },
    {
      accessorKey: 'row_count',
      header: t('upload.table.row_count'),
    },
    {
      accessorKey: 'file_size_bytes',
      header: t('upload.table.file_size'),
      cell: ({ getValue }) => formatBytes(getValue() as number),
    },
    {
      id: 'status',
      header: t('upload.table.status'),
      cell: ({ row }) => <StatusBadge status={toUploadStatus(row.original.status)} />,
    },
  ];

  const noCycle = !cycleQuery.isLoading && !openCycle;

  return (
    <RouteGuard roles={['FilingUnitManager']}>
      <Stack gap="md" p="md">
        <Group justify="space-between">
          <Title order={2}>{t('upload.page_title')}</Title>
          <Button
            variant="subtle"
            size="xs"
            onClick={() => versionsQuery.refetch()}
            aria-label={t('upload.manual_refresh')}
          >
            {t('upload.manual_refresh')}
          </Button>
        </Group>

        {/* Loading state */}
        {cycleQuery.isLoading && <Skeleton height={60} />}

        {/* No open cycle state */}
        {noCycle && (
          <Paper p="xl" withBorder>
            <Text c="dimmed" ta="center">
              {t('upload.no_open_cycle')}
            </Text>
          </Paper>
        )}

        {openCycle && (
          <Stack gap="md">
            {/* Current status */}
            <Paper p="md" withBorder>
              <Group>
                <Text fw={600}>{t('upload.current_status')}:</Text>
                <StatusBadge status={currentStatus} />
              </Group>
            </Paper>

            {/* Template download */}
            <Paper p="md" withBorder>
              <Stack gap="xs">
                <Button variant="outline" onClick={handleDownloadTemplate} disabled={!orgUnitId}>
                  {t('upload.download_template')}
                </Button>
                {templateError && (
                  <Text size="sm" c="red">
                    {templateError}
                  </Text>
                )}
              </Stack>
            </Paper>

            {/* File upload */}
            <Paper p="md" withBorder>
              <Stack gap="xs">
                <FileInput
                  label={t('upload.upload_file')}
                  accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  onChange={handleFileChange}
                  disabled={uploadMutation.isPending || !orgUnitId}
                  error={fileSizeError}
                />
                {uploadMutation.isPending && (
                  <Text size="sm" c="dimmed">
                    {t('common.loading')}
                  </Text>
                )}
                {uploadError && <ErrorDisplay error={uploadError} />}
              </Stack>
            </Paper>

            {/* Version history */}
            <Paper p="md" withBorder>
              <Title order={4} mb="sm">
                {t('upload.version_history')}
              </Title>
              {versionsQuery.isLoading ? (
                <Skeleton height={120} />
              ) : versionsQuery.isError ? (
                <ErrorDisplay error={versionsQuery.error as AxiosError} />
              ) : (
                <DataTable
                  data={versionsQuery.data ?? []}
                  columns={columns}
                  emptyMessage="upload.no_versions"
                  aria-label={t('upload.version_history')}
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
