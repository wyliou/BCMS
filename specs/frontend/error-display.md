# Spec: ErrorDisplay Component (moderate)

Module: `frontend/src/components/ErrorDisplay.tsx` | Tests: `frontend/tests/unit/components/ErrorDisplay.test.tsx`

## FRs
- **FR-011, FR-024, FR-027, FR-008:** Batch validation errors (UPLOAD_007, PERS_004, SHARED_004, ACCOUNT_002) include row-level `details[]` arrays. These must be displayed as a collapsible table with columns: Row, Column/Field, Error Code, Reason.
- **FR-022:** 403 errors must NOT be displayed as inline alerts — they trigger a redirect (handled by axios interceptor or `RouteGuard`). `ErrorDisplay` handles 400-level validation errors and 5xx errors.

## Exports
- `ErrorDisplay` — React component: renders the backend error envelope (`{ error: { code, message, details? }, request_id? }`) using a Mantine `Alert`. Shows row-level errors as a collapsible `Table` when `details` is present.

## Imports
- `@mantine/core`: `Alert`, `Text`, `Code`, `Collapse`, `Table`, `Button`, `Stack`
- `react`: `useState`
- `react-i18next`: `useTranslation`
- `axios`: `AxiosError`

## Props Interface
```typescript
interface ApiErrorDetails {
  row?: number;
  column?: string;
  code: string;
  reason: string;
}

interface ApiErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: ApiErrorDetails[];
  };
  request_id?: string;
}

interface ErrorDisplayProps {
  error: AxiosError<ApiErrorEnvelope> | Error | null | undefined;
}
```

## Rendering Logic

### Case 1: `error` is null or undefined
Renders nothing (`return null`).

### Case 2: Network error (not an AxiosError, or `error.response` is absent)
Renders a Mantine `Alert` with:
- Color: `red`
- Title: i18n key `errors.network_error` ("連線失敗")
- Body: generic connectivity message.

### Case 3: AxiosError with `error.response.data` matching `ApiErrorEnvelope`
Renders a Mantine `Alert` with:
- Color: `red`
- Title: `error.response.data.error.code` displayed in a `Code` element.
- Body: `error.response.data.error.message`.
- `request_id` shown as small grey text if present.
- If `details` array is non-empty: renders a "顯示錯誤詳情" toggle button. When expanded, shows a `Table` with columns:
  - 列 (Row)
  - 欄位 (Column)
  - 錯誤代碼 (Code)
  - 說明 (Reason)

### Case 4: AxiosError with no parseable body
Renders a generic error alert with the HTTP status code.

## Collapsible Details Table

Use Mantine `Collapse` component for the expand/collapse animation. Maximum of 100 rows rendered; if `details.length > 100`, show "... 及其他 N 列錯誤" at the bottom of the table.

The expand/collapse toggle button must be accessible:
- `aria-expanded` attribute reflects open/closed state.
- Button label changes between "顯示錯誤詳情" and "隱藏錯誤詳情".

## Side-Effects
None — pure presentational component.

## Gotchas
- `ErrorDisplay` must handle the case where `error.response?.data` is not the expected envelope shape (e.g., an HTML 502 response from nginx). Use `instanceof` and optional chaining defensively.
- Never pass a 403 `AxiosError` to this component; 403s redirect via `RouteGuard` / axios interceptor.
- Do NOT wrap `ErrorDisplay` in a try/catch — if the component itself throws, the `ErrorBoundary` catches it.
- The component must be reusable across upload forms, import pages, and cycle admin without any page-specific logic.
- `aria-describedby`: Form inputs that trigger mutations should link their error region to this component's container `id` when in error state (FCR-007).

## Tests
1. **Null error:** Returns null (renders nothing) when `error` is `null`.
2. **Network error:** Renders the "連線失敗" message when `error` is a non-Axios `Error` with no response.
3. **Validation error without details:** Renders the error `code` and `message` from the envelope without a details table.
4. **Batch validation error:** When `details` is a non-empty array, renders the "顯示錯誤詳情" toggle; clicking it expands the table showing row-level errors.
5. **request_id display:** When `request_id` is present in the envelope, it is rendered in the component.

## Consistency Constraints
FCR-005: API errors caught by mutation `onError` callbacks are passed to `<ErrorDisplay error={err} />`. The component is NOT duplicated or reimplemented locally.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
