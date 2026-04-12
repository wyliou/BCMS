import { useMemo } from 'react';
import { Button, TextInput, Select, Group, Stack } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '../../components/DataTable';
import { StatusBadge } from '../../components/StatusBadge';
import { DashboardItem } from '../../api/dashboard';

/** Dashboard status mapped to StatusBadge-compatible values. */
const DASHBOARD_STATUS_TO_BADGE: Record<string, 'not_uploaded' | 'uploaded' | 'resubmit'> = {
  not_downloaded: 'not_uploaded',
  downloaded: 'not_uploaded',
  uploaded: 'uploaded',
  resubmit_requested: 'resubmit',
};

/**
 * Props for the StatusGrid component.
 */
interface StatusGridProps {
  /** The dashboard items (filing units). */
  items: DashboardItem[];
  /** Whether data is loading. */
  isLoading: boolean;
  /** Current status filter value. */
  statusFilter: string | undefined;
  /** Callback to change the status filter. */
  onStatusFilterChange: (value: string | undefined) => void;
  /** Current org unit search text. */
  orgUnitSearch: string;
  /** Callback to change the org unit search. */
  onOrgUnitSearchChange: (value: string) => void;
  /** Whether to show the resubmit button (FinanceAdmin/UplineReviewer). */
  canResubmit: boolean;
  /** Callback when resubmit is clicked for a row. */
  onResubmit: (item: DashboardItem) => void;
}

/**
 * StatusGrid renders a filterable DataTable showing filing units and their status.
 *
 * @param props - The component props.
 * @returns The status grid with filters and table.
 */
export function StatusGrid({
  items,
  isLoading,
  statusFilter,
  onStatusFilterChange,
  orgUnitSearch,
  onOrgUnitSearchChange,
  canResubmit,
  onResubmit,
}: StatusGridProps) {
  const { t } = useTranslation();

  const statusOptions = [
    { value: '', label: t('dashboard.filter.all') },
    { value: 'not_downloaded', label: t('dashboard.status.not_downloaded') },
    { value: 'downloaded', label: t('dashboard.status.downloaded') },
    { value: 'uploaded', label: t('dashboard.status.uploaded') },
    { value: 'resubmit_requested', label: t('dashboard.status.resubmit_requested') },
  ];

  // Reason: Client-side org unit name filtering on already-fetched items
  const filteredItems = useMemo(() => {
    if (!orgUnitSearch) return items;
    const search = orgUnitSearch.toLowerCase();
    return items.filter(
      (item) =>
        item.org_unit_name.toLowerCase().includes(search) ||
        item.org_unit_id.toLowerCase().includes(search),
    );
  }, [items, orgUnitSearch]);

  const columns: ColumnDef<DashboardItem, unknown>[] = useMemo(
    () => [
      {
        accessorKey: 'org_unit_id',
        header: t('dashboard.columns.org_unit_id'),
      },
      {
        accessorKey: 'org_unit_name',
        header: t('dashboard.columns.org_unit_name'),
      },
      {
        accessorKey: 'status',
        header: t('dashboard.columns.status'),
        cell: ({ getValue }) => {
          const status = getValue<string>();
          const badgeStatus = DASHBOARD_STATUS_TO_BADGE[status] ?? 'not_uploaded';
          return <StatusBadge status={badgeStatus} />;
        },
      },
      {
        accessorKey: 'last_uploaded_at',
        header: t('dashboard.columns.last_uploaded_at'),
        cell: ({ getValue }) => {
          const val = getValue<string | null>();
          return val ? new Date(val).toLocaleString('zh-TW') : '\u2014';
        },
      },
      {
        accessorKey: 'version',
        header: t('dashboard.columns.version'),
        cell: ({ getValue }) => {
          const val = getValue<number | null>();
          return val !== null ? val : '\u2014';
        },
      },
      ...(canResubmit
        ? [
            {
              id: 'resubmit_action',
              header: t('dashboard.columns.actions'),
              cell: ({ row }: { row: { original: DashboardItem } }) => (
                <Button size="xs" variant="subtle" onClick={() => onResubmit(row.original)}>
                  {t('dashboard.actions.resubmit')}
                </Button>
              ),
            },
          ]
        : []),
    ],
    [t, canResubmit, onResubmit],
  );

  return (
    <Stack gap="md">
      <Group>
        <Select
          data={statusOptions}
          value={statusFilter ?? ''}
          onChange={(val) => onStatusFilterChange(val || undefined)}
          aria-label={t('dashboard.filter.status_label')}
          w={200}
        />
        <TextInput
          placeholder={t('dashboard.filter.org_unit_placeholder')}
          value={orgUnitSearch}
          onChange={(e) => onOrgUnitSearchChange(e.currentTarget.value)}
          aria-label={t('dashboard.filter.org_unit_label')}
          w={250}
        />
      </Group>
      <DataTable<DashboardItem>
        data={filteredItems}
        columns={columns}
        isLoading={isLoading}
        emptyMessage="dashboard.empty"
        aria-label={t('dashboard.table.label')}
      />
    </Stack>
  );
}
