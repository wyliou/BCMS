import { useState } from 'react';
import { Accordion, Group, Text, Button, TextInput, Stack, Skeleton, Modal } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ErrorDisplay } from '../../components/ErrorDisplay';
import { FailedNotificationItem } from '../../api/notifications';
import {
  useFailedNotifications,
  useResendNotification,
} from '../../features/consolidated-report/useDashboard';

/**
 * Props for the FailedNotificationsPanel component.
 */
interface FailedNotificationsPanelProps {
  /** Whether the panel should be rendered (FinanceAdmin only). */
  enabled: boolean;
}

/**
 * FailedNotificationsPanel renders a collapsible Accordion section
 * listing failed notifications with a resend button per item.
 * Only visible to FinanceAdmin.
 *
 * @param props - The component props.
 * @returns The failed notifications panel, or null if not enabled.
 */
export function FailedNotificationsPanel({ enabled }: FailedNotificationsPanelProps) {
  const { t } = useTranslation();
  const { data, isLoading, isError, error } = useFailedNotifications(enabled);
  const resendMutation = useResendNotification();

  const [resendTarget, setResendTarget] = useState<FailedNotificationItem | null>(null);
  const [resendEmail, setResendEmail] = useState('');

  if (!enabled) return null;

  const handleResendOpen = (item: FailedNotificationItem) => {
    setResendTarget(item);
    setResendEmail('');
  };

  const handleResendConfirm = async () => {
    if (!resendTarget || !resendEmail) return;
    await resendMutation.mutateAsync({
      notificationId: resendTarget.id,
      recipientEmail: resendEmail,
    });
    setResendTarget(null);
  };

  if (isLoading) {
    return (
      <Stack gap="xs">
        <Skeleton height={40} />
        <Skeleton height={40} />
      </Stack>
    );
  }

  if (isError) {
    return <ErrorDisplay error={error} />;
  }

  const items = data?.items ?? [];

  return (
    <>
      <Accordion>
        <Accordion.Item value="failed-notifications">
          <Accordion.Control>
            <Text fw={600}>
              {t('dashboard.failed_notifications.title')} ({items.length})
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            {items.length === 0 ? (
              <Text c="dimmed">{t('dashboard.failed_notifications.empty')}</Text>
            ) : (
              <Stack gap="xs">
                {items.map((item) => (
                  <Group key={item.id} justify="space-between" wrap="nowrap">
                    <Stack gap={2}>
                      <Text size="sm">
                        {item.type} - {item.recipient_id}
                      </Text>
                      {item.bounce_reason && (
                        <Text size="xs" c="dimmed">
                          {item.bounce_reason}
                        </Text>
                      )}
                      <Text size="xs" c="dimmed">
                        {new Date(item.created_at).toLocaleString('zh-TW')}
                      </Text>
                    </Stack>
                    <Button size="xs" variant="subtle" onClick={() => handleResendOpen(item)}>
                      {t('dashboard.failed_notifications.resend')}
                    </Button>
                  </Group>
                ))}
              </Stack>
            )}
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>

      <Modal
        opened={!!resendTarget}
        onClose={() => setResendTarget(null)}
        title={t('dashboard.failed_notifications.resend_title')}
      >
        <Stack gap="md">
          <TextInput
            label={t('dashboard.failed_notifications.email_label')}
            value={resendEmail}
            onChange={(e) => setResendEmail(e.currentTarget.value)}
            aria-describedby={resendMutation.isError ? 'resend-error' : undefined}
          />
          {resendMutation.isError && (
            <div id="resend-error">
              <ErrorDisplay error={resendMutation.error} />
            </div>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setResendTarget(null)}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={handleResendConfirm}
              loading={resendMutation.isPending}
              disabled={!resendEmail}
            >
              {t('common.confirm')}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}
