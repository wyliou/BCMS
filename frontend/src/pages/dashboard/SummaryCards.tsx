import { SimpleGrid, Card, Text, Group, Skeleton } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { DashboardSummary } from '../../api/dashboard';

/**
 * Props for the SummaryCards component.
 */
interface SummaryCardsProps {
  /** The dashboard summary data, or undefined during loading. */
  summary: DashboardSummary | undefined;
  /** Whether data is loading. */
  isLoading: boolean;
  /** Callback when a card is clicked to filter by status. */
  onStatusFilter: (status: string | undefined) => void;
}

/** Summary card configuration items. */
const CARD_ITEMS: {
  key: keyof DashboardSummary;
  labelKey: string;
  filterValue: string | undefined;
}[] = [
  { key: 'total', labelKey: 'dashboard.summary.total', filterValue: undefined },
  { key: 'uploaded', labelKey: 'dashboard.summary.uploaded', filterValue: 'uploaded' },
  {
    key: 'not_downloaded',
    labelKey: 'dashboard.summary.not_downloaded',
    filterValue: 'not_downloaded',
  },
  {
    key: 'resubmit_requested',
    labelKey: 'dashboard.summary.resubmit_requested',
    filterValue: 'resubmit_requested',
  },
];

/**
 * SummaryCards renders four stat cards showing filing unit counts.
 * Clicking a card filters the status grid by that status.
 *
 * @param props - The component props.
 * @returns The summary cards grid.
 */
export function SummaryCards({ summary, isLoading, onStatusFilter }: SummaryCardsProps) {
  const { t } = useTranslation();

  if (isLoading) {
    return (
      <SimpleGrid cols={{ base: 2, sm: 4 }}>
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i} withBorder>
            <Skeleton height={20} width="60%" mb="xs" />
            <Skeleton height={32} width="40%" />
          </Card>
        ))}
      </SimpleGrid>
    );
  }

  return (
    <SimpleGrid cols={{ base: 2, sm: 4 }}>
      {CARD_ITEMS.map((item) => (
        <Card
          key={item.key}
          withBorder
          style={{ cursor: 'pointer' }}
          onClick={() => onStatusFilter(item.filterValue)}
          role="button"
          aria-label={t(item.labelKey)}
        >
          <Text size="sm" c="dimmed">
            {t(item.labelKey)}
          </Text>
          <Group mt="xs">
            <Text size="xl" fw={700}>
              {summary?.[item.key] ?? 0}
            </Text>
          </Group>
        </Card>
      ))}
    </SimpleGrid>
  );
}
