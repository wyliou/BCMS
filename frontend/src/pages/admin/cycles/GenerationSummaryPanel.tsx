import { useState } from 'react';
import { Stack, Button, Group, Text, Table, Divider } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { ErrorDisplay } from '../../../components/ErrorDisplay';
import { useRegenerateTemplate } from '../../../features/cycles/useCycles';
import { OpenCycleResponse, FilingUnitInfoRead } from '../../../api/cycles';

interface GenerationSummaryPanelProps {
  /** The open cycle response including generation and dispatch summaries. */
  openResult: OpenCycleResponse;
  /** Filing units used to resolve org_unit_id to names. */
  filingUnits: FilingUnitInfoRead[];
  /** The cycle UUID for template regeneration. */
  cycleId: string;
}

/**
 * GenerationSummaryPanel displays template generation and dispatch results
 * after opening a cycle. Shows per-unit errors with retry buttons.
 *
 * @param props - The open result, filing units, and cycle ID.
 * @returns A summary panel with optional retry actions.
 */
export function GenerationSummaryPanel({
  openResult,
  filingUnits,
  cycleId,
}: GenerationSummaryPanelProps) {
  const { t } = useTranslation();
  const regenMutation = useRegenerateTemplate();
  const [retryErrors, setRetryErrors] = useState<Record<string, string>>({});

  const unitMap = Object.fromEntries(filingUnits.map((u) => [u.org_unit_id, u.name]));
  const { generation_summary, dispatch_summary } = openResult;

  const handleRetry = (orgUnitId: string) => {
    regenMutation.mutate(
      { cycleId, orgUnitId },
      {
        onSuccess: (result) => {
          if (result.status === 'error' && result.error) {
            setRetryErrors((prev) => ({ ...prev, [orgUnitId]: result.error! }));
          } else {
            setRetryErrors((prev) => {
              const next = { ...prev };
              delete next[orgUnitId];
              return next;
            });
          }
        },
        onError: (err) => {
          setRetryErrors((prev) => ({ ...prev, [orgUnitId]: err.message }));
        },
      },
    );
  };

  return (
    <Stack gap="xs">
      <Divider />
      <Text fw={600}>{t('cycle.generation_summary')}</Text>
      <Group gap="md">
        <Text size="sm">
          {t('cycle.generation_total')}: {generation_summary.total}
        </Text>
        <Text size="sm" c="green">
          {t('cycle.generation_generated')}: {generation_summary.generated}
        </Text>
        <Text size="sm" c="red">
          {t('cycle.generation_errors')}: {generation_summary.errors}
        </Text>
      </Group>

      {generation_summary.error_details.length > 0 && (
        <Table striped>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t('cycle.filing_units_table.name')}</Table.Th>
              <Table.Th>{t('cycle.filing_units_table.warnings')}</Table.Th>
              <Table.Th></Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {generation_summary.error_details.map((d) => (
              <Table.Tr key={d.org_unit_id}>
                <Table.Td>{unitMap[d.org_unit_id] ?? d.org_unit_id}</Table.Td>
                <Table.Td>
                  <Text size="sm" c="red">
                    {retryErrors[d.org_unit_id] ?? d.error ?? d.status}
                  </Text>
                </Table.Td>
                <Table.Td>
                  <Button
                    size="xs"
                    variant="outline"
                    loading={regenMutation.isPending}
                    onClick={() => handleRetry(d.org_unit_id)}
                  >
                    {t('cycle.retry_template')}
                  </Button>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      )}

      {regenMutation.isError && <ErrorDisplay error={regenMutation.error} />}

      <Text fw={600}>{t('cycle.dispatch_summary')}</Text>
      <Group gap="md">
        <Text size="sm">
          {t('cycle.dispatch_sent')}: {dispatch_summary.sent}
        </Text>
        <Text size="sm" c={dispatch_summary.errors > 0 ? 'red' : 'dimmed'}>
          {t('cycle.dispatch_errors')}: {dispatch_summary.errors}
        </Text>
      </Group>
    </Stack>
  );
}
