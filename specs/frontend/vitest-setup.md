# Spec: Vitest Setup (simple)

Module: `frontend/vitest.config.ts` + `frontend/tests/setup.ts` | Tests: n/a (setup for all other tests)

## Exports
None — configuration files only.

## Imports (in `tests/setup.ts`)
- `@testing-library/jest-dom`: for DOM matchers (`toBeInTheDocument`, `toHaveTextContent`, etc.)
- `@testing-library/react`: `cleanup` (called after each test)
- `vitest`: `afterEach`, `beforeAll`, `vi`
- `msw/node`: `setupServer` — MSW node server for API mocking

## vitest.config.ts Requirements
```typescript
// Key settings:
{
  test: {
    environment: 'jsdom',
    setupFiles: ['./tests/setup.ts'],
    globals: true,           // vi, describe, it, expect without imports
    coverage: {
      provider: 'v8',
      include: ['src/**'],
      exclude: ['src/i18n/zh-TW.json'],
    },
  },
}
```
- Must use `jsdom` environment (not `node`) for React component rendering.
- `globals: true` so tests match the Vitest global API style.
- Resolve path aliases (`@/` → `src/`) to match `tsconfig.json`.

## tests/setup.ts Requirements
- Import and extend `expect` with `@testing-library/jest-dom` matchers.
- Call `afterEach(cleanup)` so React trees are unmounted after each test.
- Set up and start the MSW `server` with an empty default handler list; export `server` for per-test handler overrides.
- Mock `window.location.href` setter with `vi.stubGlobal` or `Object.defineProperty` for tests that assert navigation.
- Suppress `console.error` output from React's error boundary testing by mocking in test files that need it (do not suppress globally — it hides real errors).

## Gotchas
- `@testing-library/user-event` version 14+ is needed for `userEvent.setup()` pattern (event simulation is async).
- The MSW server must call `server.listen({ onUnhandledRequest: 'error' })` in `beforeAll` — unhandled API calls in tests should fail loudly, not silently.
- Do NOT add `jsdom` as a top-level Vite plugin; it's a Vitest test environment only.
- Vite config and Vitest config can share a file (`vite.config.ts` with `defineConfig` + `test` key) — but keep the Vitest-specific options under the `test` key.

## Tests (self-validating)
1. A trivial test `expect(1 + 1).toBe(2)` passes — confirms Vitest globals work.
2. `@testing-library/jest-dom` matchers are available (`expect(el).toBeInTheDocument()`).
3. MSW server intercepts a test HTTP call and returns a mock response without hitting the network.
4. After each test, `cleanup()` ensures no DOM leaks between tests.

## Constraints
None of the FCR entries apply directly to test setup infrastructure.
