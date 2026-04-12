import { useState } from 'react';
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  ColumnDef,
  SortingState,
  flexRender,
} from '@tanstack/react-table';
import { Table, Pagination, Select, Group, Text, Skeleton, Center, Stack } from '@mantine/core';
import { useTranslation } from 'react-i18next';

/**
 * Props for the DataTable component.
 */
interface DataTableProps<TData> {
  /** Row data array. */
  data: TData[];
  /** Column definitions for TanStack Table. */
  columns: ColumnDef<TData, unknown>[];
  /** Whether data is currently loading. */
  isLoading?: boolean;
  /** i18n key for the empty state message. Defaults to 'common.empty'. */
  emptyMessage?: string;
  /** Number of rows per page. Defaults to 20. */
  pageSize?: number;
  /** Whether to show pagination controls. Defaults to true. */
  enablePagination?: boolean;
  /** Whether to enable column sorting. Defaults to true. */
  enableSorting?: boolean;
  /** Accessible label for the table element. */
  'aria-label'?: string;
}

/** Page size options for the pagination dropdown. */
const PAGE_SIZE_OPTIONS = [
  { value: '10', label: '10' },
  { value: '20', label: '20' },
  { value: '50', label: '50' },
];

/**
 * DataTable is a thin wrapper around TanStack Table and Mantine Table
 * providing consistent pagination, sorting, column headers, empty states,
 * and loading skeletons across the application.
 *
 * @param props - The DataTable props.
 * @returns A table with loading, empty, and paginated data states.
 */
export function DataTable<TData>({
  data,
  columns,
  isLoading = false,
  emptyMessage = 'common.empty',
  pageSize = 20,
  enablePagination = true,
  enableSorting = true,
  'aria-label': ariaLabel,
}: DataTableProps<TData>) {
  const { t } = useTranslation();
  const [sorting, setSorting] = useState<SortingState>([]);

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: enableSorting ? getSortedRowModel() : undefined,
    getPaginationRowModel: enablePagination ? getPaginationRowModel() : undefined,
    initialState: {
      pagination: { pageSize },
    },
  });

  if (isLoading) {
    return (
      <Stack gap="xs">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} height={32} />
        ))}
      </Stack>
    );
  }

  if (data.length === 0) {
    return (
      <Center py="xl">
        <Text c="dimmed">{t(emptyMessage)}</Text>
      </Center>
    );
  }

  const totalPages = table.getPageCount();
  const currentPage = table.getState().pagination.pageIndex + 1;

  return (
    <Stack gap="md">
      <Table striped highlightOnHover aria-label={ariaLabel}>
        <Table.Thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <Table.Tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => {
                const sortDir = header.column.getIsSorted();
                const ariaSortValue =
                  sortDir === 'asc' ? 'ascending' : sortDir === 'desc' ? 'descending' : 'none';

                return (
                  <Table.Th
                    key={header.id}
                    onClick={
                      enableSorting && header.column.getCanSort()
                        ? header.column.getToggleSortingHandler()
                        : undefined
                    }
                    style={
                      enableSorting && header.column.getCanSort()
                        ? { cursor: 'pointer', userSelect: 'none' }
                        : undefined
                    }
                    aria-sort={enableSorting ? ariaSortValue : undefined}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                    {sortDir === 'asc' && ' \u2191'}
                    {sortDir === 'desc' && ' \u2193'}
                  </Table.Th>
                );
              })}
            </Table.Tr>
          ))}
        </Table.Thead>
        <Table.Tbody>
          {table.getRowModel().rows.map((row) => (
            <Table.Tr key={row.id}>
              {row.getVisibleCells().map((cell) => (
                <Table.Td key={cell.id}>
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>

      {enablePagination && totalPages > 1 && (
        <Group justify="space-between">
          <Pagination
            total={totalPages}
            value={currentPage}
            onChange={(page) => table.setPageIndex(page - 1)}
            aria-label="Table pagination"
          />
          <Select
            data={PAGE_SIZE_OPTIONS}
            value={String(table.getState().pagination.pageSize)}
            onChange={(val) => {
              if (val) table.setPageSize(Number(val));
            }}
            w={80}
            aria-label={t('common.page_size')}
          />
        </Group>
      )}
    </Stack>
  );
}
