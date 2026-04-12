import { useState } from 'react';
import { Stack, Button, TextInput, Text, Divider } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import { useSetReminders } from '../../../features/cycles/useCycles';

interface ReminderSectionProps {
  /** The cycle UUID to set reminders for. */
  cycleId: string;
}

/**
 * ReminderSection provides a form for setting the reminder schedule of an Open cycle.
 * Accepts comma-separated positive integers and validates before patching.
 *
 * @param props - The cycle ID.
 * @returns A form section for editing reminder days.
 */
export function ReminderSection({ cycleId }: ReminderSectionProps) {
  const { t } = useTranslation();
  const setRemindersMutation = useSetReminders();
  const [remindersInput, setRemindersInput] = useState('7, 3, 1');
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSave = () => {
    const parts = remindersInput.split(',').map((s) => s.trim());
    const nums = parts.map(Number);
    const valid = nums.every((n) => Number.isInteger(n) && n > 0);
    if (!valid) {
      setValidationError(t('cycle.error.reminders_invalid'));
      return;
    }
    setValidationError(null);
    setRemindersMutation.mutate({ cycleId, daysBefore: nums });
  };

  const errorId = 'reminders-error';

  return (
    <Stack gap="xs" mt="sm">
      <Divider />
      <Text fw={600}>{t('cycle.set_reminders')}</Text>
      <TextInput
        label={t('cycle.reminders_days_before')}
        description={t('cycle.reminders_hint')}
        value={remindersInput}
        onChange={(e) => setRemindersInput(e.target.value)}
        error={validationError}
        aria-describedby={validationError ? errorId : undefined}
        id="reminders-input"
      />
      {validationError && (
        <Text id={errorId} size="xs" c="red">
          {validationError}
        </Text>
      )}
      <Button
        size="xs"
        variant="outline"
        loading={setRemindersMutation.isPending}
        onClick={handleSave}
      >
        {t('cycle.save_reminders')}
      </Button>
      {setRemindersMutation.isError && <ErrorDisplay error={setRemindersMutation.error} />}
    </Stack>
  );
}
