import { useState } from 'react';
import {
  Container,
  Stack,
  Badge,
  Group,
  Tooltip,
  Modal,
  Select,
  Button,
  Text,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '../../../components/DataTable';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import { useOrgUnits, usePatchOrgUnit } from '../../../features/cycles/useOrgUnits';
import { useAuthStore } from '../../../stores/auth-store';
import { OrgUnit } from '../../../api/admin';

/**
 * OrgTreePage displays organization units in a table with ability to manage excluded cycles.
 * Accessible to SystemAdmin and FinanceAdmin; only SystemAdmin can edit.
 *
 * @returns The org tree admin page.
 */
export default function OrgTreePage() {
  const { t } = useTranslation();
  const { hasRole } = useAuthStore();
  const canEdit = hasRole('SystemAdmin');

  const { data, isLoading, isError, error } = useOrgUnits();
  const patchMutation = usePatchOrgUnit();

  const [editingUnit, setEditingUnit] = useState<OrgUnit | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedCycleIds, setSelectedCycleIds] = useState<string[]>([]);

  const handleOpenEdit = (unit: OrgUnit) => {
    setEditingUnit(unit);
    setSelectedCycleIds(unit.excluded_for_cycle_ids || []);
    setEditModalOpen(true);
  };

  const handleSaveEdit = async () => {
    if (!editingUnit) return;
    await patchMutation.mutateAsync({
      id: editingUnit.id,
      excludedForCycleIds: selectedCycleIds,
    });
    setEditModalOpen(false);
    setEditingUnit(null);
  };

  const columns: ColumnDef<OrgUnit>[] = [
    {
      accessorKey: 'code',
      header: t('org_tree.columns.code'),
    },
    {
      accessorKey: 'name',
      header: t('org_tree.columns.name'),
    },
    {
      accessorKey: 'level_code',
      header: t('org_tree.columns.level_code'),
    },
    {
      accessorKey: 'is_filing_unit',
      header: t('org_tree.columns.is_filing_unit'),
      cell: ({ getValue }) => {
        const isFiling = getValue<boolean>();
        return isFiling ? t('org_tree.yes') : t('org_tree.no');
      },
    },
    {
      accessorKey: 'has_manager',
      header: t('org_tree.columns.has_manager'),
      cell: ({ row }) => {
        const unit = row.original;
        const hasManager = unit.has_manager;
        return (
          <Group gap={4}>
            {!hasManager && (
              <Tooltip label={t('org_tree.warning.no_manager')}>
                <span>⚠️</span>
              </Tooltip>
            )}
            <span>{hasManager ? t('org_tree.yes') : t('org_tree.no')}</span>
          </Group>
        );
      },
    },
    {
      accessorKey: 'excluded_for_cycle_ids',
      header: t('org_tree.columns.excluded_cycles'),
      cell: ({ getValue }) => {
        const ids = getValue<string[] | undefined>() || [];
        return ids.length > 0 ? <Badge>{ids.length}</Badge> : '-';
      },
    },
    {
      id: 'actions',
      header: t('org_tree.columns.actions'),
      cell: ({ row }) => {
        if (!canEdit) return '-';
        return (
          <Button variant="subtle" size="xs" onClick={() => handleOpenEdit(row.original)}>
            {t('org_tree.buttons.edit')}
          </Button>
        );
      },
    },
  ];

  const orgUnits = data?.items || [];

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        {/* Info Badge */}
        {!canEdit && (
          <Badge color="blue" variant="light">
            {t('org_tree.info.read_only')}
          </Badge>
        )}

        {/* Error Display */}
        {isError && <ErrorDisplay error={error} />}

        {/* Data Table */}
        <DataTable<OrgUnit>
          data={orgUnits}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="org_tree.empty.no_units"
          pageSize={50}
          enablePagination={true}
          aria-label={t('org_tree.table.label')}
        />

        {/* Edit Modal */}
        <Modal
          opened={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          title={t('org_tree.modal.title')}
        >
          {editingUnit && (
            <Stack gap="md">
              <Group justify="space-between">
                <Text fw={500}>{t('org_tree.modal.name')}:</Text>
                <Text>{editingUnit.name}</Text>
              </Group>
              <Select
                label={t('org_tree.modal.excluded_cycles')}
                placeholder={t('org_tree.modal.excluded_cycles_placeholder')}
                data={[
                  { value: 'cycle-1', label: 'Cycle 1' },
                  { value: 'cycle-2', label: 'Cycle 2' },
                ]}
                searchable
                clearable
                value={selectedCycleIds.length > 0 ? selectedCycleIds[0] : null}
                onChange={(val) => setSelectedCycleIds(val ? [val] : [])}
              />
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setEditModalOpen(false)}>
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  loading={patchMutation.isPending}
                  disabled={patchMutation.isPending}
                >
                  {t('common.save')}
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>

        {/* Mutation Error */}
        {patchMutation.isError && <ErrorDisplay error={patchMutation.error} />}
      </Stack>
    </Container>
  );
}
