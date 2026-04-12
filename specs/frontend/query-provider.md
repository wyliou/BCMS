# Spec: TanStack Query Provider (simple)

Module: `frontend/src/providers/QueryProvider.tsx` | Tests: `frontend/tests/unit/providers/QueryProvider.test.tsx`

## Exports
- `QueryProvider` — React component: wraps children in `QueryClientProvider` with default `QueryClient` configuration.

## Imports
- `@tanstack/react-query`: `QueryClient`, `QueryClientProvider`
- `react`: `ReactNode`

## QueryClient Default Options
```typescript
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // 30s — avoid unnecessary refetches on tab focus
      retry: 1,                // one automatic retry on network failure
      refetchOnWindowFocus: true,
    },
    mutations: {
      retry: 0,                // never retry mutations automatically
    },
  },
});
```

The `queryClient` instance is created once at module scope (singleton).

## Side-Effects
None beyond wrapping children. `QueryClient` instance is created once at module evaluation time.

## Gotchas
- `QueryClient` must be created outside the component body so it is not recreated on each render.
- Do NOT override `refetchInterval` in default options — per-query overrides handle that (FCR-006 mandates `refetchInterval: 5000` only on dashboard hook).
- `QueryProvider` is the outermost provider in `App.tsx`, wrapping auth store and router.

## Tests
1. Renders children without error when wrapped in `QueryProvider`.
2. `useQueryClient()` inside a child resolves to the shared client (not null).
3. QueryClient is the same instance across re-renders (referential equality).
4. Devtools are NOT rendered in the production build (if `ReactQueryDevtools` is added, it must be gated on `import.meta.env.DEV`).

## Constraints
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
