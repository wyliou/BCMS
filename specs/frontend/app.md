# Spec: App.tsx Entry Point (simple)

Module: `frontend/src/App.tsx` | Tests: `frontend/tests/unit/App.test.tsx`

## Exports
- `App` — default export React component: wires all providers and renders the router outlet.

## Imports
- `@mantine/core`: `MantineProvider`
- `react-i18next`: `I18nextProvider`
- `../src/i18n/index`: `i18n`
- `../src/styles/theme`: `theme`
- `../src/providers/QueryProvider`: `QueryProvider`
- `../src/routes/index`: `AppRouter` (default export from routes)
- `react-router-dom`: `BrowserRouter`

## Provider Stack (outermost to innermost)
```tsx
<MantineProvider theme={theme}>
  <I18nextProvider i18n={i18n}>
    <QueryProvider>
      <BrowserRouter>
        <AppRouter />
      </BrowserRouter>
    </QueryProvider>
  </I18nextProvider>
</MantineProvider>
```

`ErrorBoundary` wraps the entire stack as the outermost element so render errors anywhere are caught:
```tsx
<ErrorBoundary>
  <MantineProvider theme={theme}>
    ...
  </MantineProvider>
</ErrorBoundary>
```

## Side-Effects
- Importing `i18n` from `src/i18n/index.ts` triggers i18next initialization as a side effect.

## Gotchas
- `BrowserRouter` must wrap `AppRouter` so all React Router hooks work inside route components.
- `MantineProvider` must be the outermost UI provider so Mantine components in `ErrorBoundary`'s fallback can access the theme context.
- Do NOT fetch auth state here. Auth initialization is handled inside `AppRouter` or a dedicated init component.
- `App.tsx` file must stay under 100 lines — it should only wire providers.

## Tests
1. Renders without crashing (smoke test with all providers).
2. `MantineProvider` receives the `theme` object with `brandPrimary` color defined.
3. `QueryProvider` is present in the tree (children can call `useQueryClient()`).
4. `BrowserRouter` is present so `useNavigate()` works in child components.
5. `ErrorBoundary` is the outermost wrapper; a child error renders the fallback UI without crashing the test.

## Constraints
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
