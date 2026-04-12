import { useState } from 'react';
import { useForm, zodResolver } from '@mantine/form';
import {
  Stack,
  Title,
  Button,
  Group,
  Paper,
  Text,
  Skeleton,
  Modal,
  TextInput,
  NumberInput,
} from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { AxiosError } from 'axios';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import { RouteGuard } from '../../../components/RouteGuard';
import { useCycleList, useCreateCycle } from '../../../features/cycles/useCycles';
import { OpenCycleResponse, FilingUnitInfoRead } from '../../../api/cycles';
import { CycleCard } from './CycleCard';
import { GenerationSummaryPanel } from './GenerationSummaryPanel';

// --- Form schema ---
const createCycleSchema = z.object({
  fiscal_year: z.number({ required_error: 'cycle.error.year_required' }).int().min(2000).max(2100),
  deadline: z.string().min(1, 'cycle.error.deadline_required'),
  reporting_currency: z.string().min(1, 'cycle.error.currency_required'),
});

type CreateCycleFormValues = z.infer<typeof createCycleSchema>;

/**
 * CycleAdminPage manages budget cycles: create, open, close, reopen, and set reminders.
 * Route guard enforces FinanceAdmin or SystemAdmin role.
 *
 * @returns The cycle administration page.
 */
export default function CycleAdminPage() {
  const { t } = useTranslation();
  const [createOpened, setCreateOpened] = useState(false);
  const [createError, setCreateError] = useState<AxiosError | null>(null);
  const [openResults, setOpenResults] = useState<
    Record<string, { result: OpenCycleResponse; units: FilingUnitInfoRead[] }>
  >({});

  const { data: cycles, isLoading, isError, error } = useCycleList();
  const createMutation = useCreateCycle();

  const form = useForm<CreateCycleFormValues>({
    validate: zodResolver(createCycleSchema),
    initialValues: {
      fiscal_year: new Date().getFullYear(),
      deadline: '',
      reporting_currency: 'TWD',
    },
  });

  const handleCreate = (values: CreateCycleFormValues) => {
    setCreateError(null);
    createMutation.mutate(values, {
      onSuccess: () => {
        setCreateOpened(false);
        form.reset();
      },
      onError: (err) => setCreateError(err),
    });
  };

  return (
    <RouteGuard roles={['FinanceAdmin', 'SystemAdmin']}>
      <Stack gap="md" p="md">
        <Group justify="space-between">
          <Title order={2}>{t('cycle.page_title')}</Title>
          <Button onClick={() => setCreateOpened(true)}>{t('cycle.create_cycle')}</Button>
        </Group>

        {/* Create cycle modal */}
        <Modal
          opened={createOpened}
          onClose={() => setCreateOpened(false)}
          title={t('cycle.create_cycle')}
        >
          <form onSubmit={form.onSubmit(handleCreate)}>
            <Stack>
              {createError && <ErrorDisplay error={createError} />}
              <NumberInput
                label={t('cycle.fiscal_year')}
                required
                min={2000}
                max={2100}
                aria-describedby={form.errors.fiscal_year ? 'fiscal-year-error' : undefined}
                {...form.getInputProps('fiscal_year')}
              />
              <TextInput
                label={t('cycle.deadline')}
                placeholder="YYYY-MM-DD"
                required
                aria-describedby={form.errors.deadline ? 'deadline-error' : undefined}
                {...form.getInputProps('deadline')}
              />
              <TextInput
                label={t('cycle.reporting_currency')}
                required
                aria-describedby={form.errors.reporting_currency ? 'currency-error' : undefined}
                {...form.getInputProps('reporting_currency')}
              />
              <Group justify="flex-end">
                <Button variant="outline" onClick={() => setCreateOpened(false)}>
                  {t('common.cancel')}
                </Button>
                <Button type="submit" loading={createMutation.isPending}>
                  {t('common.confirm')}
                </Button>
              </Group>
            </Stack>
          </form>
        </Modal>

        {/* Loading state */}
        {isLoading && (
          <Stack>
            <Skeleton height={80} />
            <Skeleton height={80} />
          </Stack>
        )}

        {/* Error state */}
        {isError && <ErrorDisplay error={error as AxiosError} />}

        {/* Empty state */}
        {!isLoading && !isError && cycles?.length === 0 && (
          <Paper p="xl" withBorder>
            <Stack align="center" gap="md">
              <Text c="dimmed">{t('cycle.no_cycles')}</Text>
              <Button onClick={() => setCreateOpened(true)}>{t('cycle.create_cycle')}</Button>
            </Stack>
          </Paper>
        )}

        {/* Populated state */}
        {cycles &&
          cycles.length > 0 &&
          cycles.map((cycle) => (
            <Stack key={cycle.id} gap="xs">
              <CycleCard
                cycle={cycle}
                onOpenResult={(cycleId, result, units) =>
                  setOpenResults((prev) => ({ ...prev, [cycleId]: { result, units } }))
                }
              />
              {openResults[cycle.id] && (
                <Paper p="md" withBorder>
                  <GenerationSummaryPanel
                    openResult={openResults[cycle.id].result}
                    filingUnits={openResults[cycle.id].units}
                    cycleId={cycle.id}
                  />
                </Paper>
              )}
            </Stack>
          ))}
      </Stack>
    </RouteGuard>
  );
}
