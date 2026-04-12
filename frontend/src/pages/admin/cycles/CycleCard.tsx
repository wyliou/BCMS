import { useState } from 'react';
import {
  Stack,
  Button,
  Group,
  Paper,
  Text,
  Badge,
  Skeleton,
  Modal,
  Textarea,
  Alert,
  Table,
  Divider,
  Collapse,
} from '@mantine/core';
import { useForm, zodResolver } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { AxiosError } from 'axios';
import { useAuthStore } from '../../../stores/auth-store';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import {
  useOpenCycle,
  useCloseCycle,
  useReopenCycle,
  useFilingUnits,
} from '../../../features/cycles/useCycles';
import { CycleRead, OpenCycleResponse, FilingUnitInfoRead } from '../../../api/cycles';
import { ReminderSection } from './ReminderSection';

const reopenSchema = z.object({
  reason: z.string().min(1, 'cycle.error.reopen_reason_required'),
});

type ReopenFormValues = z.infer<typeof reopenSchema>;

/**
 * Maps cycle status to i18n key.
 *
 * @param status - The cycle status.
 * @returns i18n key string.
 */
export function statusKey(status: CycleRead['status']): string {
  const map: Record<CycleRead['status'], string> = {
    Draft: 'cycle.status.draft',
    Open: 'cycle.status.open',
    Closed: 'cycle.status.closed',
  };
  return map[status];
}

/**
 * Maps cycle status to Mantine badge color.
 *
 * @param status - The cycle status.
 * @returns Mantine color string.
 */
export function statusColor(status: CycleRead['status']): string {
  const map: Record<CycleRead['status'], string> = {
    Draft: 'gray',
    Open: 'green',
    Closed: 'red',
  };
  return map[status];
}

export interface CycleCardProps {
  /** The cycle to display. */
  cycle: CycleRead;
  /** Called when a cycle is successfully opened with its result. */
  onOpenResult: (cycleId: string, result: OpenCycleResponse, units: FilingUnitInfoRead[]) => void;
}

/**
 * CycleCard renders a single cycle with status badge and action buttons.
 * Handles open, close, and reopen mutations inline.
 *
 * @param props - The cycle and callback.
 * @returns A Paper card for the cycle.
 */
export function CycleCard({ cycle, onOpenResult }: CycleCardProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [reopenOpened, setReopenOpened] = useState(false);
  const [reopenError, setReopenError] = useState<AxiosError | null>(null);
  const [openError, setOpenError] = useState<AxiosError | null>(null);

  const hasAnyRole = useAuthStore((s) => s.hasAnyRole);
  const isSystemAdmin = hasAnyRole('SystemAdmin');

  const filingUnitsQuery = useFilingUnits(expanded && cycle.status === 'Draft' ? cycle.id : null);
  const openMutation = useOpenCycle();
  const closeMutation = useCloseCycle();
  const reopenMutation = useReopenCycle();

  const reopenForm = useForm<ReopenFormValues>({
    validate: zodResolver(reopenSchema),
    initialValues: { reason: '' },
  });

  const handleOpen = () => {
    setOpenError(null);
    openMutation.mutate(cycle.id, {
      onSuccess: (result) => {
        onOpenResult(cycle.id, result, filingUnitsQuery.data ?? []);
      },
      onError: (err) => setOpenError(err),
    });
  };

  const handleClose = () => {
    closeMutation.mutate(cycle.id, {
      onSuccess: () => setConfirmClose(false),
    });
  };

  const handleReopen = (values: ReopenFormValues) => {
    setReopenError(null);
    reopenMutation.mutate(
      { cycleId: cycle.id, reason: values.reason },
      {
        onSuccess: () => setReopenOpened(false),
        onError: (err) => setReopenError(err),
      },
    );
  };

  const missingManagerUnits = (filingUnitsQuery.data ?? []).filter(
    (u) => !u.has_manager && !u.excluded,
  );
  const canOpen = missingManagerUnits.length === 0;

  return (
    <Paper p="md" withBorder>
      <Group justify="space-between" mb="xs">
        <Group gap="sm">
          <Text fw={600}>
            {cycle.fiscal_year} — {cycle.reporting_currency}
          </Text>
          <Badge color={statusColor(cycle.status)}>{t(statusKey(cycle.status))}</Badge>
        </Group>
        <Group gap="xs">
          {cycle.status === 'Draft' && (
            <Button size="xs" variant="outline" onClick={() => setExpanded((v) => !v)}>
              {expanded ? t('common.collapse') : t('cycle.filing_units_check')}
            </Button>
          )}
          {cycle.status === 'Draft' && (
            <Button
              size="xs"
              loading={openMutation.isPending}
              disabled={expanded && !canOpen}
              onClick={handleOpen}
              data-testid="open-cycle-btn"
            >
              {t('cycle.open_cycle')}
            </Button>
          )}
          {cycle.status === 'Open' && (
            <Button
              size="xs"
              color="red"
              variant="outline"
              onClick={() => setConfirmClose(true)}
              data-testid="close-cycle-btn"
            >
              {t('cycle.close_cycle')}
            </Button>
          )}
          {cycle.status === 'Closed' && isSystemAdmin && (
            <Button size="xs" variant="outline" onClick={() => setReopenOpened(true)}>
              {t('cycle.reopen_cycle')}
            </Button>
          )}
        </Group>
      </Group>

      <Text size="sm" c="dimmed">
        {t('cycle.deadline')}: {cycle.deadline}
      </Text>

      {openError && <ErrorDisplay error={openError} />}

      {/* Pre-open filing units check panel */}
      <Collapse in={expanded && cycle.status === 'Draft'}>
        <Divider my="sm" />
        {filingUnitsQuery.isLoading && <Skeleton height={80} />}
        {filingUnitsQuery.data && (
          <Stack gap="xs">
            {missingManagerUnits.length > 0 && (
              <Alert color="yellow" title={t('cycle.no_manager_warning')}>
                <Text size="sm">
                  {missingManagerUnits.map((u) => `${u.code} ${u.name}`).join(', ')}
                </Text>
              </Alert>
            )}
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t('cycle.filing_units_table.code')}</Table.Th>
                  <Table.Th>{t('cycle.filing_units_table.name')}</Table.Th>
                  <Table.Th>{t('cycle.filing_units_table.has_manager')}</Table.Th>
                  <Table.Th>{t('cycle.filing_units_table.excluded')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {filingUnitsQuery.data.map((u) => (
                  <Table.Tr key={u.org_unit_id}>
                    <Table.Td>{u.code}</Table.Td>
                    <Table.Td>{u.name}</Table.Td>
                    <Table.Td>{u.has_manager ? 'Yes' : 'No'}</Table.Td>
                    <Table.Td>{u.excluded ? 'Yes' : '-'}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Stack>
        )}
      </Collapse>

      {/* Reminder section for Open cycles */}
      {cycle.status === 'Open' && <ReminderSection cycleId={cycle.id} />}

      {/* Reopen modal */}
      <Modal
        opened={reopenOpened}
        onClose={() => setReopenOpened(false)}
        title={t('cycle.reopen_cycle')}
      >
        <form onSubmit={reopenForm.onSubmit(handleReopen)}>
          <Stack>
            {reopenError && <ErrorDisplay error={reopenError} />}
            <Textarea
              label={t('cycle.reopen_reason')}
              placeholder={t('cycle.reopen_reason_placeholder')}
              required
              aria-describedby={reopenForm.errors.reason ? 'reopen-reason-error' : undefined}
              {...reopenForm.getInputProps('reason')}
            />
            <Group justify="flex-end">
              <Button variant="outline" onClick={() => setReopenOpened(false)}>
                {t('common.cancel')}
              </Button>
              <Button type="submit" loading={reopenMutation.isPending}>
                {t('cycle.reopen_cycle')}
              </Button>
            </Group>
          </Stack>
        </form>
      </Modal>

      {/* Confirm close dialog */}
      <Modal
        opened={confirmClose}
        onClose={() => setConfirmClose(false)}
        title={t('cycle.confirm_close')}
        data-testid="close-confirm-modal"
      >
        <Stack>
          <Text>{t('cycle.confirm_close_message')}</Text>
          <Group justify="flex-end">
            <Button variant="outline" onClick={() => setConfirmClose(false)}>
              {t('common.cancel')}
            </Button>
            <Button color="red" loading={closeMutation.isPending} onClick={handleClose}>
              {t('cycle.close_cycle')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Paper>
  );
}
