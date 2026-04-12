# Spec: DataTable Wrapper Component (moderate)

Module: `frontend/src/components/DataTable.tsx` | Tests: `frontend/tests/unit/components/DataTable.test.tsx`

## FRs
- **FR-014:** Dashboard status grid must support filtering, sorting, and pagination.
- **FR-023:** Audit log search results table supports multi-column display with pagination.
- **FR-012, FR-025, FR-028:** Version history lists (upload, personnel, shared cost) need consistent tabular display with empty states.

## Exports
- `DataTable` — React component: thin wrapper around Mantine `Table` and TanStack Table for consistent pagination, sorting, column headers, empty states, and loading skeletons across the application.

## Imports
- `@tanstack/react-table`: `useReactTable`, `getCoreRowModel`, `getSortedRowModel`, `getPaginationRowModel`, `ColumnDef`, `SortingState`, `flexRender`
- `@mantine/core`: `Table`, `Pagination`, `Select`, `Group`, `Text`, `Skeleton`, `Center`, `Stack`
- `react`: `useState`
- `react-i18next`: `useTranslation`

## Props Interface
```typescript
interface DataTableProps<TData> {
  data: TData[];
  columns: ColumnDef<TData, unknown>[];
  isLoading?: boolean;
  emptyMessage?: string;      // i18n key, defaults to 'common.empty'
  pageSize?: number;          // default 20
  enablePagination?: boolean; // default true
  enableSorting?: boolean;    // default true
  'aria-label'?: string;      // required for accessibility (FCR-007)
}
```

## Rendering Behavior

### Loading State
When `isLoading` is `true`, renders a `<Skeleton>` placeholder with 5 rows of the approximate column width. Does not render the table structure until data is available.

### Empty State
When `data.length === 0` and `isLoading === false`, renders a `<Center>` containing the `emptyMessage` translated string. No table structure rendered.

### Normal State
Renders a Mantine `<Table>` with:
- `striped`, `highlightOnHover` props for readability.
- Column headers rendered from `ColumnDef` with sort indicators when `enableSorting` is `true`.
- Sort is toggled by clicking headers; `SortingState` is managed internally via `useState`.
- Pagination rendered below the table when `enablePagination` is `true`:
  - Mantine `Pagination` component for page navigation.
  - A `Select` for page size (options: 10, 20, 50).

### Accessibility
- `<Table>` element receives the `aria-label` prop.
- Column sort buttons have `aria-sort` attribute (`"ascending"` | `"descending"` | `"none"`).
- Pagination controls have descriptive `aria-label` attributes.

## Side-Effects
Internal `useState` for `sorting` and `pagination` state. No external side effects — purely presentational with local UI state.

## Gotchas
- `ColumnDef` uses `accessorKey` or `accessorFn` as defined by the caller page. `DataTable` does not know about specific data shapes.
- This component does NOT handle server-side sorting or pagination. All data is passed pre-fetched. Pages that need server-side pagination must implement their own query params and pass filtered slices.
- Exception: `AuditLogPage` has server-side pagination (FR-023 uses `page`/`size` query params). For that page, `enablePagination` should be `false` and the page manages its own pagination UI outside this component.
- Do NOT add business logic or data-fetching inside `DataTable`. It is purely presentational.
- File size: If the component approaches 200 lines, extract `DataTableHeader`, `DataTableBody`, and `DataTablePagination` into sub-components in the same file or adjacent files.

## Tests
1. **Loading state:** When `isLoading` is `true`, renders skeletons and no `<table>` element.
2. **Empty state:** When `data` is empty and not loading, renders the `emptyMessage`.
3. **Renders rows:** With 3 data rows and matching columns, renders 3 `<tr>` elements in the `<tbody>`.
4. **Sorting:** Clicking a sortable column header updates the sort icon and reorders the displayed rows.
5. **Pagination:** When `data` has 25 rows and `pageSize` is 20, the first page shows 20 rows and the pagination control shows 2 pages.

## Consistency Constraints
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
FCR-010: This page checks `isLoading`, `isError`, and `data?.length === 0` from its query hook and renders appropriate UI for each state.
