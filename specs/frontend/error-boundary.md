# Spec: ErrorBoundary Component (simple)

Module: `frontend/src/components/ErrorBoundary.tsx` | Tests: `frontend/tests/unit/components/ErrorBoundary.test.tsx`

## Exports
- `ErrorBoundary` — React class component: catches unhandled React render errors below it in the tree. Displays a fallback UI when an error is caught.

## Imports
- `react`: `Component`, `ErrorInfo`, `ReactNode`
- `react-i18next`: `withTranslation` or `TFunction` (for i18n in class component)
- `@mantine/core`: `Alert`, `Text`, `Button`

## Props Interface
```typescript
interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;  // Optional custom fallback; defaults to generic error UI
}
interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}
```

## Behavior
- Must be a React class component (hooks-based error boundaries are not supported in React 18.3).
- `componentDidCatch(error, info)`: logs error info for diagnostics. No `console.log` — use structured error reporting only (per subagent constraint #9). In production, this would forward to an error tracking service; for now it is a no-op beyond state update.
- `getDerivedStateFromError(error)`: returns `{ hasError: true, error }`.
- Fallback UI: Mantine `Alert` with color `red`, title from i18n key `errors.boundary_title`, message from `errors.boundary_message`. Includes a "重新整理" button calling `window.location.reload()`.
- If `fallback` prop is provided, renders that instead of the default fallback UI.

## Side-Effects
None beyond catching render errors. No HTTP calls.

## Gotchas
- Error boundaries do NOT catch errors in event handlers, async code, or server-side rendering. They only catch render-phase errors.
- Must be placed high in the tree (in `App.tsx`) to catch errors from any page.
- Class component is required; do not refactor to a function component.
- `console.error` is acceptable here as the browser devtools need to display the error stack (this is the one allowed `console.*` call).

## Tests
1. Renders children normally when no error is thrown.
2. When a child throws during render, displays the fallback Alert UI instead of crashing the app.
3. "重新整理" button is present in the error fallback UI.
4. Custom `fallback` prop is rendered instead of default UI when provided.

## Constraints
FCR-004: All user-visible strings in this component are rendered via `t('i18n.key')`. No inline Chinese characters in JSX.
FCR-007: Every `<TextInput>`, `<Select>`, `<FileInput>` in this component has an `aria-describedby` pointing to its error message element when in error state. Focus order follows visual order.
