import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Center, Title, Text, Button, Stack } from '@mantine/core';

/**
 * NotFoundPage displays a 404 page not found message.
 * Rendered by the React Router catch-all route.
 *
 * @returns The 404 not found page UI.
 */
export default function NotFoundPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Center h="100vh">
      <Stack align="center" gap="md">
        <Title order={1}>{t('errors.not_found_title')}</Title>
        <Text c="dimmed">{t('errors.not_found_message')}</Text>
        <Button onClick={() => navigate('/')}>{t('errors.back_home')}</Button>
      </Stack>
    </Center>
  );
}
