import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Center, Title, Text, Button, Stack } from '@mantine/core';

/**
 * ForbiddenPage displays a 403 access denied message.
 * Shown when RouteGuard redirects due to insufficient roles.
 *
 * @returns The 403 forbidden page UI.
 */
export default function ForbiddenPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Center h="100vh">
      <Stack align="center" gap="md">
        <Title order={1}>{t('errors.forbidden_title')}</Title>
        <Text c="dimmed">{t('errors.forbidden_message')}</Text>
        <Button onClick={() => navigate('/')}>{t('errors.back_home')}</Button>
      </Stack>
    </Center>
  );
}
