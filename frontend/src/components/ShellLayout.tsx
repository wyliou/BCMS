import { AppShell, NavLink, Group, Text, Button, Burger, useMantineTheme } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { NavLink as RouterNavLink, Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores/auth-store';

/**
 * Navigation item configuration for the shell sidebar.
 */
interface NavItem {
  /** i18n key for the label text. */
  label: string;
  /** Route path to navigate to. */
  to: string;
  /** Roles that can see this nav item. */
  roles: readonly string[];
}

/**
 * Role-to-nav-item mapping per PRD section 8.2.
 */
const NAV_ITEMS: readonly NavItem[] = [
  {
    label: 'nav.dashboard',
    to: '/dashboard',
    roles: ['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'],
  },
  {
    label: 'nav.reports',
    to: '/reports',
    roles: ['FinanceAdmin', 'UplineReviewer', 'CompanyReviewer', 'SystemAdmin'],
  },
  {
    label: 'nav.upload',
    to: '/upload',
    roles: ['FilingUnitManager'],
  },
  {
    label: 'nav.personnel_import',
    to: '/personnel-import',
    roles: ['HRAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.shared_cost_import',
    to: '/shared-cost-import',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.cycle_admin',
    to: '/admin/cycles',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.account_master',
    to: '/admin/accounts',
    roles: ['FinanceAdmin', 'SystemAdmin'],
  },
  {
    label: 'nav.org_tree',
    to: '/admin/org-units',
    roles: ['SystemAdmin'],
  },
  {
    label: 'nav.user_admin',
    to: '/admin/users',
    roles: ['SystemAdmin'],
  },
  {
    label: 'nav.audit_log',
    to: '/audit',
    roles: ['ITSecurityAuditor', 'SystemAdmin'],
  },
] as const;

/**
 * ShellLayout provides the application shell with a role-differentiated sidebar,
 * header with user info and logout button, and an Outlet for page content.
 *
 * @returns The shell layout wrapping nested route content.
 */
export function ShellLayout() {
  const { t } = useTranslation();
  const theme = useMantineTheme();
  const [opened, { toggle }] = useDisclosure();
  const { user, logout, hasAnyRole } = useAuthStore();

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 250, breakpoint: 'sm', collapsed: { mobile: !opened } }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" />
            <Text fw={700}>{t('auth.login_title')}</Text>
          </Group>
          <Group>
            <Text size="sm">{user?.display_name ?? ''}</Text>
            <Button variant="subtle" size="xs" onClick={() => logout()}>
              {t('common.logout')}
            </Button>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="md">
        {NAV_ITEMS.filter((item) => hasAnyRole(...item.roles)).map((item) => (
          <NavLink key={item.to} label={t(item.label)} component={RouterNavLink} to={item.to} />
        ))}
      </AppShell.Navbar>

      <AppShell.Main bg={theme.other.surfaceBase as string}>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
