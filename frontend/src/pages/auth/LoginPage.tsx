import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Button, Center, Card, Title, Text, Stack, Alert } from '@mantine/core';
import { useAuthStore } from '../../stores/auth-store';

/**
 * SSO Login landing page. Displays the platform name and a button that
 * redirects to the SSO login endpoint via full-page navigation.
 *
 * If the user is already authenticated, redirects to /dashboard.
 * If the URL contains ?error=AUTH_003, displays an unauthorized message.
 *
 * @returns The login page UI.
 */
export default function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { isAuthenticated } = useAuthStore();

  const errorCode = searchParams.get('error');

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  /**
   * Handles SSO login button click by navigating to the backend SSO endpoint.
   */
  function handleLogin() {
    window.location.href = '/api/v1/auth/sso/login?return_to=' + encodeURIComponent('/dashboard');
  }

  return (
    <Center h="100vh">
      <Card shadow="md" padding="xl" radius="md" withBorder w={400}>
        <Stack align="center" gap="md">
          <Title order={2}>{t('auth.login_title')}</Title>
          <Text c="dimmed">{t('auth.login_prompt')}</Text>

          {errorCode === 'AUTH_003' && (
            <Alert color="red" w="100%">
              {t('auth.unauthorized')}
            </Alert>
          )}

          {errorCode === 'AUTH_001' && (
            <Alert color="red" w="100%">
              {t('auth.sso_unavailable')}
            </Alert>
          )}

          <Button fullWidth onClick={handleLogin}>
            {t('auth.login_button')}
          </Button>
        </Stack>
      </Card>
    </Center>
  );
}
