import { useState } from 'react';
import { Container, Stack, Modal, Group, Button, MultiSelect, Text, Badge } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '../../../components/DataTable';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import { useUsers, usePatchUser, useDeactivateUser } from '../../../features/cycles/useUsers';
import { User } from '../../../api/admin';

/**
 * UserAdminPage displays users with role management and deactivation.
 * Accessible only to SystemAdmin role.
 *
 * @returns The user administration page.
 */
export default function UserAdminPage() {
  const { t } = useTranslation();

  const [pagination] = useState({ page: 1, size: 50 });
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);

  const { data, isLoading, isError, error } = useUsers(pagination);
  const patchMutation = usePatchUser();
  const deactivateMutation = useDeactivateUser();

  const handleOpenEditRoles = (user: User) => {
    setEditingUser(user);
    setSelectedRoles(user.roles);
    setEditModalOpen(true);
  };

  const handleSaveRoles = async () => {
    if (!editingUser) return;
    await patchMutation.mutateAsync({
      userId: editingUser.id,
      updates: { roles: selectedRoles },
    });
    setEditModalOpen(false);
    setEditingUser(null);
  };

  const handleOpenDeactivate = (user: User) => {
    setEditingUser(user);
    setDeactivateModalOpen(true);
  };

  const handleDeactivate = async () => {
    if (!editingUser) return;
    await deactivateMutation.mutateAsync(editingUser.id);
    setDeactivateModalOpen(false);
    setEditingUser(null);
  };

  const columns: ColumnDef<User>[] = [
    {
      accessorKey: 'name',
      header: t('users.columns.name'),
    },
    {
      accessorKey: 'email',
      header: t('users.columns.email'),
    },
    {
      accessorKey: 'roles',
      header: t('users.columns.roles'),
      cell: ({ getValue }) => {
        const roles = getValue<string[]>();
        return (
          <Group gap="xs">
            {roles.map((role) => (
              <Badge key={role} size="sm">
                {role}
              </Badge>
            ))}
          </Group>
        );
      },
    },
    {
      accessorKey: 'is_active',
      header: t('users.columns.is_active'),
      cell: ({ getValue }) => {
        const isActive = getValue<boolean>();
        return (
          <Badge color={isActive ? 'green' : 'red'}>
            {isActive ? t('users.status.active') : t('users.status.inactive')}
          </Badge>
        );
      },
    },
    {
      id: 'actions',
      header: t('users.columns.actions'),
      cell: ({ row }) => {
        const user = row.original;
        return (
          <Group gap={4}>
            <Button
              variant="subtle"
              size="xs"
              onClick={() => handleOpenEditRoles(user)}
              disabled={!user.is_active}
            >
              {t('users.buttons.edit_roles')}
            </Button>
            <Button
              variant="subtle"
              size="xs"
              color="red"
              onClick={() => handleOpenDeactivate(user)}
              disabled={!user.is_active}
            >
              {t('users.buttons.deactivate')}
            </Button>
          </Group>
        );
      },
    },
  ];

  const users = data?.items || [];

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        {/* Error Display */}
        {isError && <ErrorDisplay error={error} />}

        {/* Data Table */}
        <DataTable<User>
          data={users}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="users.empty.no_users"
          pageSize={50}
          enablePagination={true}
          aria-label={t('users.table.label')}
        />

        {/* Edit Roles Modal */}
        <Modal
          opened={editModalOpen}
          onClose={() => setEditModalOpen(false)}
          title={t('users.modal.edit_roles_title')}
        >
          {editingUser && (
            <Stack gap="md">
              <Group justify="space-between">
                <Text fw={500}>{t('users.modal.user_name')}:</Text>
                <Text>{editingUser.name}</Text>
              </Group>
              <MultiSelect
                label={t('users.modal.roles')}
                placeholder={t('users.modal.roles_placeholder')}
                data={[
                  { value: 'FilingUnitManager', label: 'FilingUnitManager' },
                  { value: 'HRAdmin', label: 'HRAdmin' },
                  { value: 'FinanceAdmin', label: 'FinanceAdmin' },
                  { value: 'UplineReviewer', label: 'UplineReviewer' },
                  { value: 'CompanyReviewer', label: 'CompanyReviewer' },
                  { value: 'ITSecurityAuditor', label: 'ITSecurityAuditor' },
                  { value: 'SystemAdmin', label: 'SystemAdmin' },
                ]}
                searchable
                value={selectedRoles}
                onChange={setSelectedRoles}
              />
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setEditModalOpen(false)}>
                  {t('common.cancel')}
                </Button>
                <Button
                  onClick={handleSaveRoles}
                  loading={patchMutation.isPending}
                  disabled={patchMutation.isPending}
                >
                  {t('common.save')}
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>

        {/* Deactivate Confirmation Modal */}
        <Modal
          opened={deactivateModalOpen}
          onClose={() => setDeactivateModalOpen(false)}
          title={t('users.modal.deactivate_title')}
        >
          {editingUser && (
            <Stack gap="md">
              <Text>{t('users.modal.deactivate_confirm', { name: editingUser.name })}</Text>
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setDeactivateModalOpen(false)}>
                  {t('common.cancel')}
                </Button>
                <Button
                  color="red"
                  onClick={handleDeactivate}
                  loading={deactivateMutation.isPending}
                  disabled={deactivateMutation.isPending}
                >
                  {t('users.buttons.deactivate')}
                </Button>
              </Group>
            </Stack>
          )}
        </Modal>

        {/* Mutation Errors */}
        {patchMutation.isError && <ErrorDisplay error={patchMutation.error} />}
        {deactivateMutation.isError && <ErrorDisplay error={deactivateMutation.error} />}
      </Stack>
    </Container>
  );
}
