import { useState } from 'react';
import {
  Container,
  Stack,
  Select,
  Button,
  Group,
  Modal,
  TextInput,
  NumberInput,
  FileInput,
} from '@mantine/core';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslation } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import { DataTable } from '../../../components/DataTable';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import {
  useAccounts,
  useUpsertAccount,
  useImportActuals,
} from '../../../features/cycles/useAccounts';
import { useAuthStore } from '../../../stores/auth-store';
import { Account } from '../../../api/accounts';

/**
 * Zod schema for account upsert form.
 */
const UpsertAccountSchema = z.object({
  code: z.string().min(1, 'Code is required'),
  name: z.string().min(1, 'Name is required'),
  category: z.enum(['operational', 'personnel', 'shared_cost']),
  level: z.number().int().positive('Level must be positive'),
});

type UpsertAccountForm = z.infer<typeof UpsertAccountSchema>;

/**
 * AccountMasterPage displays accounts with CRUD operations and actuals import.
 * Accessible to FinanceAdmin and SystemAdmin.
 *
 * @returns The account master page.
 */
export default function AccountMasterPage() {
  const { t } = useTranslation();
  const { hasRole } = useAuthStore();
  const canEdit = hasRole('SystemAdmin');

  const [categoryFilter, setCategoryFilter] = useState<string | null>(null);
  const [upsertModalOpen, setUpsertModalOpen] = useState(false);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [cycleIdForImport, setCycleIdForImport] = useState('');

  const { data, isLoading, isError, error, refetch } = useAccounts(categoryFilter || undefined);
  const upsertMutation = useUpsertAccount();
  const importMutation = useImportActuals();

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<UpsertAccountForm>({
    resolver: zodResolver(UpsertAccountSchema),
  });

  const handleUpsert = async (formData: UpsertAccountForm) => {
    await upsertMutation.mutateAsync(formData);
    setUpsertModalOpen(false);
    reset();
    refetch();
  };

  const handleImport = async () => {
    if (!selectedFile || !cycleIdForImport) {
      return;
    }
    await importMutation.mutateAsync({ cycleId: cycleIdForImport, file: selectedFile });
    setImportModalOpen(false);
    setSelectedFile(null);
    setCycleIdForImport('');
  };

  const columns: ColumnDef<Account>[] = [
    {
      accessorKey: 'code',
      header: t('accounts.columns.code'),
    },
    {
      accessorKey: 'name',
      header: t('accounts.columns.name'),
    },
    {
      accessorKey: 'category',
      header: t('accounts.columns.category'),
      cell: ({ getValue }) => {
        const cat = getValue<string>();
        return t(`accounts.category.${cat}`);
      },
    },
    {
      accessorKey: 'level',
      header: t('accounts.columns.level'),
    },
  ];

  const accounts = data?.items || [];

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        {/* Category Filter */}
        <Select
          label={t('accounts.filter.category')}
          placeholder={t('accounts.filter.category_placeholder')}
          data={[
            { value: 'operational', label: t('accounts.category.operational') },
            { value: 'personnel', label: t('accounts.category.personnel') },
            { value: 'shared_cost', label: t('accounts.category.shared_cost') },
          ]}
          searchable
          clearable
          value={categoryFilter}
          onChange={setCategoryFilter}
        />

        {/* Error Display */}
        {isError && <ErrorDisplay error={error} />}

        {/* Data Table */}
        <DataTable<Account>
          data={accounts}
          columns={columns}
          isLoading={isLoading}
          emptyMessage="accounts.empty.no_accounts"
          pageSize={50}
          enablePagination={true}
          aria-label={t('accounts.table.label')}
        />

        {/* Action Buttons */}
        {canEdit && (
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setImportModalOpen(true)}>
              {t('accounts.buttons.import_actuals')}
            </Button>
            <Button onClick={() => setUpsertModalOpen(true)}>
              {t('accounts.buttons.add_account')}
            </Button>
          </Group>
        )}

        {/* Upsert Modal */}
        <Modal
          opened={upsertModalOpen}
          onClose={() => setUpsertModalOpen(false)}
          title={t('accounts.modal.upsert_title')}
        >
          <form onSubmit={handleSubmit(handleUpsert)}>
            <Stack gap="md">
              <TextInput
                label={t('accounts.form.code')}
                placeholder={t('accounts.form.code_placeholder')}
                {...register('code')}
                error={errors.code?.message}
              />
              <TextInput
                label={t('accounts.form.name')}
                placeholder={t('accounts.form.name_placeholder')}
                {...register('name')}
                error={errors.name?.message}
              />
              <Controller
                name="category"
                control={control}
                render={({ field }) => (
                  <Select
                    label={t('accounts.form.category')}
                    placeholder={t('accounts.form.category_placeholder')}
                    data={[
                      { value: 'operational', label: t('accounts.category.operational') },
                      { value: 'personnel', label: t('accounts.category.personnel') },
                      { value: 'shared_cost', label: t('accounts.category.shared_cost') },
                    ]}
                    {...field}
                  />
                )}
              />
              <Controller
                name="level"
                control={control}
                render={({ field }) => (
                  <NumberInput
                    label={t('accounts.form.level')}
                    placeholder={t('accounts.form.level_placeholder')}
                    {...field}
                    value={field.value || undefined}
                    error={errors.level?.message}
                  />
                )}
              />
              <Group justify="flex-end">
                <Button variant="default" onClick={() => setUpsertModalOpen(false)}>
                  {t('common.cancel')}
                </Button>
                <Button type="submit" loading={upsertMutation.isPending}>
                  {t('common.save')}
                </Button>
              </Group>
            </Stack>
          </form>
        </Modal>

        {/* Import Modal */}
        <Modal
          opened={importModalOpen}
          onClose={() => setImportModalOpen(false)}
          title={t('accounts.modal.import_title')}
        >
          <Stack gap="md">
            <TextInput
              label={t('accounts.form.cycle_id')}
              placeholder={t('accounts.form.cycle_id_placeholder')}
              value={cycleIdForImport}
              onChange={(e) => setCycleIdForImport(e.currentTarget.value)}
            />
            <FileInput
              label={t('accounts.form.file')}
              placeholder={t('accounts.form.file_placeholder')}
              accept=".csv,.xlsx,.xls"
              value={selectedFile}
              onChange={setSelectedFile}
            />
            {importMutation.isError && <ErrorDisplay error={importMutation.error} />}
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setImportModalOpen(false)}>
                {t('common.cancel')}
              </Button>
              <Button onClick={handleImport} loading={importMutation.isPending}>
                {t('accounts.buttons.import')}
              </Button>
            </Group>
          </Stack>
        </Modal>

        {/* Upsert Error */}
        {upsertMutation.isError && <ErrorDisplay error={upsertMutation.error} />}
      </Stack>
    </Container>
  );
}
