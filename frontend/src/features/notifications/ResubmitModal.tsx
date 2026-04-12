import { useEffect } from 'react';
import {
  Modal,
  Stack,
  Textarea,
  NumberInput,
  Button,
  Group,
  Text,
  Divider,
  Skeleton,
  Table,
} from '@mantine/core';
import { useForm, zodResolver } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useAuthStore } from '../../stores/auth-store';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { useResubmit } from './useResubmit';

// --- Form schema ---
const resubmitSchema = z.object({
  reason: z.string().min(1, 'resubmit.error.reason_required'),
  target_version: z.number().int().positive().optional(),
});

type ResubmitFormValues = z.infer<typeof resubmitSchema>;

/**
 * Props for the ResubmitModal component.
 */
export interface ResubmitModalProps {
  /** Whether the modal is open. */
  opened: boolean;
  /** Callback to close the modal. */
  onClose: () => void;
  /** The cycle UUID for this resubmit request. */
  cycleId: string;
  /** The org unit UUID for the filing unit to resubmit. */
  orgUnitId: string;
  /** Display name of the org unit shown in the modal title. */
  orgUnitName: string;
  /** The user_id of the filing unit's manager (recipient). */
  recipientUserId: string;
  /** The email address of the filing unit's manager. */
  recipientEmail: string;
  /** The latest upload version number to pre-fill target_version. */
  latestVersion: number | null;
}

/**
 * ResubmitModal provides a form for FinanceAdmins or UplineReviewers to
 * send a resubmit notification to a filing unit manager.
 * Also shows the history of previous resubmit requests for the unit.
 *
 * @param props - The modal props.
 * @returns A Mantine Modal with form and history sections.
 */
export function ResubmitModal({
  opened,
  onClose,
  cycleId,
  orgUnitId,
  orgUnitName,
  recipientUserId,
  recipientEmail,
  latestVersion,
}: ResubmitModalProps) {
  const { t } = useTranslation();

  // Reason: requester_user_id must come from auth store, never from props (security)
  const user = useAuthStore((s) => s.user);
  const requesterUserId = user?.user_id ?? '';

  const { historyQuery, createMutation } = useResubmit(cycleId, orgUnitId, opened);

  const form = useForm<ResubmitFormValues>({
    validate: zodResolver(resubmitSchema),
    initialValues: {
      reason: '',
      target_version: latestVersion ?? undefined,
    },
  });

  // Reset form when modal opens
  useEffect(() => {
    if (opened) {
      form.reset();
      form.setFieldValue('target_version', latestVersion ?? undefined);
    }
    // Reason: Only reset on open, not on every render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const handleSubmit = (values: ResubmitFormValues) => {
    createMutation.mutate(
      {
        cycle_id: cycleId,
        org_unit_id: orgUnitId,
        reason: values.reason,
        target_version: values.target_version,
        requester_user_id: requesterUserId,
        recipient_user_id: recipientUserId,
        recipient_email: recipientEmail,
      },
      {
        onSuccess: () => {
          notifications.show({ message: t('resubmit.submit_success'), color: 'green' });
          onClose();
        },
      },
    );
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={`${t('resubmit.modal_title')} — ${orgUnitName}`}
      size="lg"
    >
      <Stack gap="md">
        {/* Error from mutation */}
        {createMutation.isError && <ErrorDisplay error={createMutation.error} />}

        {/* Resubmit form */}
        <form onSubmit={form.onSubmit(handleSubmit)}>
          <Stack gap="sm">
            <Textarea
              label={t('resubmit.reason_label')}
              placeholder={t('resubmit.reason_placeholder')}
              withAsterisk
              minRows={3}
              disabled={createMutation.isPending}
              aria-describedby={form.errors.reason ? 'resubmit-reason-error' : undefined}
              {...form.getInputProps('reason')}
            />
            {form.errors.reason && (
              <Text id="resubmit-reason-error" size="xs" c="red">
                {t('resubmit.error.reason_required')}
              </Text>
            )}

            <NumberInput
              label={t('resubmit.target_version_label')}
              min={1}
              disabled={createMutation.isPending}
              aria-describedby={form.errors.target_version ? 'resubmit-version-error' : undefined}
              {...form.getInputProps('target_version')}
            />

            <Group justify="flex-end">
              <Button variant="outline" onClick={onClose} disabled={createMutation.isPending}>
                {t('resubmit.cancel')}
              </Button>
              <Button type="submit" loading={createMutation.isPending}>
                {t('resubmit.submit')}
              </Button>
            </Group>
          </Stack>
        </form>

        <Divider />

        {/* History section */}
        <Text fw={600}>{t('resubmit.history_title')}</Text>
        {historyQuery.isLoading && <Skeleton height={80} />}
        {historyQuery.isError && <ErrorDisplay error={historyQuery.error} />}
        {historyQuery.data && historyQuery.data.length === 0 && (
          <Text size="sm" c="dimmed">
            {t('resubmit.no_history')}
          </Text>
        )}
        {historyQuery.data && historyQuery.data.length > 0 && (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>{t('resubmit.table.requested_at')}</Table.Th>
                <Table.Th>{t('resubmit.table.reason')}</Table.Th>
                <Table.Th>{t('resubmit.table.target_version')}</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {historyQuery.data.map((req) => (
                <Table.Tr key={req.id}>
                  <Table.Td>{new Date(req.requested_at).toLocaleString('zh-TW')}</Table.Td>
                  <Table.Td>
                    <Text size="sm" lineClamp={2} title={req.reason}>
                      {req.reason}
                    </Text>
                  </Table.Td>
                  <Table.Td>{req.target_version ?? '-'}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        )}
      </Stack>
    </Modal>
  );
}
