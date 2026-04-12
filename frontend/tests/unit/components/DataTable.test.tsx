import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MantineProvider } from '@mantine/core';
import { I18nextProvider } from 'react-i18next';
import { ColumnDef } from '@tanstack/react-table';
import i18n from '../../../src/i18n';
import { DataTable } from '../../../src/components/DataTable';

interface TestRow {
  id: number;
  name: string;
}

const columns: ColumnDef<TestRow, unknown>[] = [
  { accessorKey: 'id', header: 'ID' },
  { accessorKey: 'name', header: 'Name' },
];

/**
 * Test wrapper providing Mantine and i18n context.
 */
function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <MantineProvider>
      <I18nextProvider i18n={i18n}>{children}</I18nextProvider>
    </MantineProvider>
  );
}

describe('DataTable', () => {
  it('renders skeletons when isLoading is true', () => {
    const { container } = render(
      <Wrapper>
        <DataTable data={[]} columns={columns} isLoading />
      </Wrapper>,
    );
    expect(container.querySelector('table')).not.toBeInTheDocument();
    expect(container.querySelectorAll('.mantine-Skeleton-root').length).toBeGreaterThanOrEqual(1);
  });

  it('renders empty message when data is empty and not loading', () => {
    render(
      <Wrapper>
        <DataTable data={[]} columns={columns} />
      </Wrapper>,
    );
    expect(screen.getByText(i18n.t('common.empty'))).toBeInTheDocument();
  });

  it('renders correct number of data rows', () => {
    const data: TestRow[] = [
      { id: 1, name: 'Alice' },
      { id: 2, name: 'Bob' },
      { id: 3, name: 'Charlie' },
    ];

    render(
      <Wrapper>
        <DataTable data={data} columns={columns} enablePagination={false} />
      </Wrapper>,
    );

    const rows = screen.getAllByRole('row');
    // 1 header row + 3 data rows
    expect(rows).toHaveLength(4);
  });

  it('sorts rows when clicking a sortable column header', async () => {
    const user = userEvent.setup();
    const data: TestRow[] = [
      { id: 3, name: 'Charlie' },
      { id: 1, name: 'Alice' },
      { id: 2, name: 'Bob' },
    ];

    render(
      <Wrapper>
        <DataTable data={data} columns={columns} enablePagination={false} />
      </Wrapper>,
    );

    // Click on the Name header to sort
    const nameHeader = screen.getByText('Name');
    await user.click(nameHeader);

    // After ascending sort, first data cell in second column should be Alice
    const cells = screen.getAllByRole('cell');
    expect(cells[1].textContent).toBe('Alice');
  });

  it('paginates when data exceeds pageSize', () => {
    const data: TestRow[] = Array.from({ length: 25 }, (_, i) => ({
      id: i + 1,
      name: `User ${i + 1}`,
    }));

    render(
      <Wrapper>
        <DataTable data={data} columns={columns} pageSize={20} />
      </Wrapper>,
    );

    // Should show 20 data rows + 1 header on first page
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(21);

    // Pagination controls should be present
    expect(screen.getByLabelText('Table pagination')).toBeInTheDocument();
  });
});
