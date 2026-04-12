import { ColumnDef } from '@tanstack/react-table';
import { ConsolidatedReportRow } from '../../api/reports';
import { formatAmount } from '../../lib/format-currency';
import { TFunction } from 'i18next';

/**
 * Formats a monetary value for display, returning a dash for null values.
 *
 * @param value - The string monetary value or null.
 * @returns The formatted string.
 */
function displayAmount(value: string | null): string {
  if (value === null) return '\u2014';
  return formatAmount(value) ?? '\u2014';
}

/**
 * Builds the column definitions for the consolidated report table.
 * Uses three column groups: operational budget, personnel budget, shared cost.
 *
 * @param t - The i18n translation function.
 * @returns Array of column definitions for TanStack Table.
 */
export function buildReportColumns(t: TFunction): ColumnDef<ConsolidatedReportRow>[] {
  return [
    // Org unit columns
    {
      accessorKey: 'org_unit_id',
      header: t('report.columns.org_unit_id'),
      enableSorting: false,
    },
    {
      accessorKey: 'org_unit_name',
      header: t('report.columns.org_unit_name'),
      enableSorting: false,
    },
    // Account columns
    {
      accessorKey: 'account_code',
      header: t('report.columns.account_code'),
      enableSorting: false,
    },
    {
      accessorKey: 'account_name',
      header: t('report.columns.account_name'),
      enableSorting: false,
    },
    // Column group 1: operational budget
    {
      id: 'operational_budget_group',
      header: t('report.column_groups.operational_budget'),
      columns: [
        {
          accessorKey: 'actual',
          header: t('report.columns.actual'),
          cell: (info) => displayAmount(info.getValue() as string | null),
          enableSorting: true,
        },
        {
          accessorKey: 'operational_budget',
          header: t('report.columns.operational_budget'),
          cell: (info) => {
            const val = info.getValue() as string | null;
            const row = info.row.original;
            if (val === null && row.budget_status === 'not_uploaded') {
              return t('report.status.not_uploaded');
            }
            return displayAmount(val);
          },
          enableSorting: true,
        },
        {
          accessorKey: 'delta_amount',
          header: t('report.columns.delta_amount'),
          cell: (info) => displayAmount(info.getValue() as string | null),
          enableSorting: true,
        },
        {
          accessorKey: 'delta_pct',
          header: t('report.columns.delta_pct'),
          // Reason: Backend sends "N/A" for zero-actual rows; render as-is
          cell: (info) => info.getValue() as string,
          enableSorting: false,
        },
      ],
    },
    // Column group 2: personnel budget
    {
      id: 'personnel_budget_group',
      header: t('report.column_groups.personnel_budget'),
      columns: [
        {
          accessorKey: 'personnel_budget',
          header: t('report.columns.personnel_budget'),
          // Reason: FCR-012 — null below 1000-level displays as "—"
          cell: (info) => displayAmount(info.getValue() as string | null),
          enableSorting: true,
        },
      ],
    },
    // Column group 3: shared cost
    {
      id: 'shared_cost_group',
      header: t('report.column_groups.shared_cost'),
      columns: [
        {
          accessorKey: 'shared_cost',
          header: t('report.columns.shared_cost'),
          cell: (info) => displayAmount(info.getValue() as string | null),
          enableSorting: true,
        },
      ],
    },
  ];
}
