import { useState, useMemo } from 'react';
import {
  Container,
  Stack,
  Group,
  Button,
  TextInput,
  Select,
  Tabs,
  Modal,
  Text,
  Badge,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '../../components/DataTable';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import {
  useAuditLogs,
  useVerifyChain,
  AuditLogsQueryParams,
} from '../../features/audit/useAuditLogs';
import { AuditLogRead } from '../../api/audit';
import { exportAuditLogs } from '../../api/audit';

/**
 * AuditLogPage displays paginated audit logs with filtering, chain verification, and CSV export.
 * Accessible only to ITSecurityAuditor and SystemAdmin roles.
 *
 * @returns The audit log search page.
 */
export default function AuditLogPage() {
  const { t } = useTranslation();
  const [params, setParams] = useState<AuditLogsQueryParams>({ page: 1, size: 50 });
  const [filterForm, setFilterForm] = useState<Omit<AuditLogsQueryParams, 'page' | 'size'>>({});
  const [verifyModalOpen, setVerifyModalOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const { data, isLoading, isError, error } = useAuditLogs(params);
  const verifyMutation = useVerifyChain();

  const handleFilterSubmit = () => {
    setParams({ ...filterForm, page: 1, size: 50 });
  };

  const handleVerifyOpen = () => {
    verifyMutation.reset();
    verifyMutation.mutate({ from: filterForm.from, to: filterForm.to });
    setVerifyModalOpen(true);
  };

  const handleExportCSV = async () => {
    setIsExporting(true);
    try {
      await exportAuditLogs(filterForm.from, filterForm.to);
    } finally {
      setIsExporting(false);
    }
  };

  const columns: ColumnDef<AuditLogRead>[] = useMemo(
    () => [
      {
        accessorKey: 'timestamp',
        header: t('audit.columns.timestamp'),
        cell: ({ getValue }) => {
          const ts = getValue<string>();
          return new Date(ts).toLocaleString('zh-TW');
        },
      },
      {
        accessorKey: 'user_id',
        header: t('audit.columns.user_id'),
        cell: ({ getValue }) => {
          const uid = getValue<string>();
          return uid.slice(0, 8) + '...';
        },
      },
      {
        accessorKey: 'action',
        header: t('audit.columns.action'),
      },
      {
        accessorKey: 'resource_type',
        header: t('audit.columns.resource_type'),
      },
      {
        accessorKey: 'resource_id',
        header: t('audit.columns.resource_id'),
        cell: ({ getValue }) => {
          const rid = getValue<string | null>();
          return rid ? rid.slice(0, 8) + '...' : '-';
        },
      },
      {
        accessorKey: 'ip_address',
        header: t('audit.columns.ip_address'),
      },
    ],
    [t],
  );

  const auditLogItems = data?.items || [];

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        {/* Filter Form */}
        <Tabs defaultValue="filters" aria-label={t('audit.tabs.label')}>
          <Tabs.List>
            <Tabs.Tab value="filters">{t('audit.tabs.filters')}</Tabs.Tab>
          </Tabs.List>
          <Tabs.Panel value="filters" pt="md">
            <Stack gap="md">
              <Group grow>
                <TextInput
                  label={t('audit.form.user_id')}
                  placeholder={t('audit.form.user_id_placeholder')}
                  value={filterForm.user_id || ''}
                  onChange={(e) => setFilterForm({ ...filterForm, user_id: e.currentTarget.value })}
                />
                <Select
                  label={t('audit.form.action')}
                  placeholder={t('audit.form.action_placeholder')}
                  data={[
                    { value: 'budget_upload.accepted', label: 'budget_upload.accepted' },
                    { value: 'budget_upload.rejected', label: 'budget_upload.rejected' },
                    { value: 'login', label: 'login' },
                    { value: 'logout', label: 'logout' },
                  ]}
                  searchable
                  clearable
                  value={filterForm.action || null}
                  onChange={(val) => setFilterForm({ ...filterForm, action: val || undefined })}
                />
              </Group>
              <Group grow>
                <TextInput
                  label={t('audit.form.resource_type')}
                  placeholder={t('audit.form.resource_type_placeholder')}
                  value={filterForm.resource_type || ''}
                  onChange={(e) =>
                    setFilterForm({ ...filterForm, resource_type: e.currentTarget.value })
                  }
                />
                <TextInput
                  label={t('audit.form.resource_id')}
                  placeholder={t('audit.form.resource_id_placeholder')}
                  value={filterForm.resource_id || ''}
                  onChange={(e) =>
                    setFilterForm({ ...filterForm, resource_id: e.currentTarget.value })
                  }
                />
              </Group>
              <Group grow>
                <TextInput
                  label={t('audit.form.from')}
                  type="datetime-local"
                  value={filterForm.from || ''}
                  onChange={(e) => setFilterForm({ ...filterForm, from: e.currentTarget.value })}
                />
                <TextInput
                  label={t('audit.form.to')}
                  type="datetime-local"
                  value={filterForm.to || ''}
                  onChange={(e) => setFilterForm({ ...filterForm, to: e.currentTarget.value })}
                />
              </Group>
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setFilterForm({})}>
                  {t('common.cancel')}
                </Button>
                <Button onClick={handleFilterSubmit} disabled={isLoading}>
                  {t('audit.buttons.search')}
                </Button>
              </Group>
            </Stack>
          </Tabs.Panel>
        </Tabs>

        {/* Error Display */}
        {isError && <ErrorDisplay error={error} />}

        {/* Data Table */}
        <DataTable<AuditLogRead>
          data={auditLogItems}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="audit.empty.no_results"
          pageSize={50}
          enablePagination={true}
          aria-label={t('audit.table.label')}
        />

        {/* Action Buttons */}
        <Group justify="flex-end">
          <Button
            variant="default"
            onClick={handleVerifyOpen}
            disabled={!filterForm.from || !filterForm.to}
          >
            {t('audit.buttons.verify')}
          </Button>
          <Button
            onClick={handleExportCSV}
            disabled={!filterForm.from || !filterForm.to || isExporting}
            loading={isExporting}
          >
            {t('audit.buttons.export')}
          </Button>
        </Group>

        {/* Verify Chain Modal */}
        <Modal
          opened={verifyModalOpen}
          onClose={() => {
            setVerifyModalOpen(false);
            verifyMutation.reset();
          }}
          title={t('audit.verify.title')}
        >
          {verifyMutation.isPending ? (
            <Text>{t('common.loading')}</Text>
          ) : verifyMutation.data ? (
            <Stack gap="md">
              <Group justify="space-between">
                <Text fw={500}>{t('audit.verify.status')}:</Text>
                <Badge color={verifyMutation.data.verified ? 'green' : 'red'}>
                  {verifyMutation.data.verified
                    ? t('audit.verify.verified')
                    : t('audit.verify.corrupted')}
                </Badge>
              </Group>
              <Group justify="space-between">
                <Text fw={500}>{t('audit.verify.chain_length')}:</Text>
                <Text>{verifyMutation.data.chain_length}</Text>
              </Group>
              <Button fullWidth onClick={() => setVerifyModalOpen(false)}>
                {t('common.confirm')}
              </Button>
            </Stack>
          ) : verifyMutation.isError ? (
            <ErrorDisplay error={verifyMutation.error} />
          ) : null}
        </Modal>
      </Stack>
    </Container>
  );
}
