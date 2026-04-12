# BCMS Frontend Build Context

Cross-cutting conventions, patterns, and constraints that apply to every frontend batch and every module. Tech Lead delegation prompts reference this document.

## Stack

| Layer | Choice | Version | Source |
|---|---|---|---|
| Language | TypeScript | 5.6.x | architecture section 1 |
| Framework | React | 18.3.x | architecture section 1 |
| Build tool | Vite | 5.4.x | architecture section 1 |
| Routing | React Router | 6.28.x | architecture section 1 |
| Server state | TanStack Query | 5.x | architecture section 1 |
| Client state | Zustand | 5.x | architecture section 1 |
| Forms | react-hook-form + zod | 7.x / 3.23 | architecture section 1 |
| HTTP client | axios | 1.7.x | architecture section 1 |
| Component library | Mantine | 7.x | architecture section 1 (locked) |
| i18n | react-i18next | 15.x | architecture section 1 |
| Tables | TanStack Table | 8.x | architecture section 1 |
| Testing | Vitest + React Testing Library | 2.x / 16.x | architecture section 1 |
| Lint | ESLint | 9.x | architecture section 1 |
| Format | Prettier | 3.x | architecture section 1 |
| Package manager | pnpm | 9.x | architecture section 1 |

## Source Layout

- All frontend code lives under `frontend/src/`.
- All frontend tests under `frontend/tests/unit/`.
- Pages (route-level components) live in `src/pages/<feature>/` — one directory per route group.
- Feature-scoped hooks and components live in `src/features/<feature>/` — domain logic isolated per feature.
- Shared presentational components live in `src/components/` — no business logic, only UI rendering.
- API client modules live in `src/api/` — one file per backend resource group, typed with zod.
- Zustand stores live in `src/stores/` — one file per concern (auth, UI).
- i18n translations live in `src/i18n/`.
- Utility functions live in `src/lib/`.
- Design tokens and theme live in `src/styles/`.
- Route configuration lives in `src/routes/`.

## Naming Conventions (from architecture section 3)

| Element | Convention | Example |
|---|---|---|
| Component files | PascalCase `.tsx` | `ConsolidatedReport.tsx` |
| Hook files | camelCase, `use` prefix `.ts` | `useBudgetUploads.ts` |
| Utility files | kebab-case `.ts` | `format-currency.ts` |
| Functions | camelCase | `getUploadStatus()` |
| Components | PascalCase | `<ConsolidatedReport />` |
| Constants | UPPER_SNAKE | `STATUS_COLORS` |
| Types/Interfaces | PascalCase, `Dto` suffix for API shapes | `BudgetUploadDto` |
| Routes | kebab-case | `/personnel-import` |
| i18n keys | dot.notation snake_case | `upload.error.row_invalid` |
| Test files | `*.test.ts` or `*.test.tsx` | `useBudgetUploads.test.ts` |

## Component Structure

- **Pages** (`src/pages/`): Route-level components. One per screen from architecture section 5.13. Responsible for: fetching data via hooks, composing feature components, handling route params.
- **Features** (`src/features/`): Feature-scoped logic. Contains custom hooks (TanStack Query wrappers), feature-specific sub-components, and feature-local types. NEVER export barrels from features — import directly from the specific file.
- **Components** (`src/components/`): Shared presentational components used by 2+ pages. No data fetching. Accept props only. Examples: `StatusBadge`, `ErrorDisplay`, `DataTable`, `RouteGuard`, `ShellLayout`.

## State Management

- **Server state:** TanStack Query for all backend data. Use `useQuery` for reads, `useMutation` for writes. Configure appropriate `staleTime` and `refetchInterval` per endpoint.
- **Client state:** Zustand for auth state (`stores/auth-store.ts`) and any UI-only state (sidebar collapse, active filters). Keep Zustand stores minimal — most state should live in TanStack Query cache.
- **Form state:** react-hook-form for all forms with zod schema validation. Define zod schemas adjacent to the form component.

## Form Handling

- Use `react-hook-form` with `zodResolver` for every form (cycle create, account upsert, file upload, resubmit reason).
- Zod schemas live next to the component that owns the form.
- File upload forms use `FormData` with the axios instance.
- On validation error from the backend (400 with `error.details[]`), display row-level errors using `ErrorDisplay`.

## API Layer

- Typed axios client in `src/api/client.ts`. Singleton instance with:
  - `baseURL` from `VITE_API_BASE_URL`
  - `withCredentials: true` (cookie auth)
  - Request interceptor: reads `bc_csrf` cookie, sets `X-CSRF-Token` header on POST/PATCH/DELETE
  - Response interceptor: 401 -> silent refresh -> retry; refresh fail -> redirect to SSO login
- One file per resource group in `src/api/`.
- Each function returns a typed response validated with zod `parse()` or `safeParse()`.
- Never use raw `fetch()` or create additional axios instances.

## Testing

- **Framework:** Vitest + React Testing Library.
- **Test count:** 3-5 tests per component/hook covering:
  1. Renders correctly (happy path)
  2. User interaction triggers expected behavior
  3. Error state rendering
  4. Loading state rendering
  5. Empty state rendering
- **Test structure:** Mirror `src/` structure under `tests/unit/`.
- **Auth in tests:** Use a test auth provider that wraps the component in a Zustand provider with preset auth state. NEVER mock the auth store directly in feature page tests.
- **API mocking:** Use `msw` (Mock Service Worker) for API calls in tests. Define handlers in `tests/mocks/handlers.ts`.
- **No snapshots:** Prefer assertion-based tests over snapshot tests.

## i18n

- All user-visible strings in `src/i18n/zh-TW.json`.
- Never hardcode Chinese (or any language) text in components. Use `t('key')` from `useTranslation()`.
- English is used for: role enum values, API field names, error codes, technical labels.
- i18n key format: `<page>.<section>.<key>` (e.g., `dashboard.summary.total_units`).

## Accessibility (WCAG AA)

- Color contrast at least 4.5:1 for all text.
- Visible focus indicators on all interactive elements (Mantine provides this by default).
- `aria-describedby` on form inputs linked to their error messages.
- All form errors announced to screen readers.
- Keyboard navigation: all primary workflows completable without mouse.
- Upload dropzones and file inputs accessible via keyboard.

## Error Handling

- All API errors use the shared error envelope: `{ error: { code, message, details? }, request_id? }`.
- `ErrorDisplay` component renders the envelope.
- Batch validation errors (UPLOAD_007, PERS_004, SHARED_004, ACCOUNT_002) show row-level details as a table.
- Network errors and timeouts show a generic "連線失敗" message.
- 403 errors redirect to the Forbidden page (never retry).
- 401 errors are handled by the axios interceptor (silent refresh or redirect to login).

## Subagent Constraints (Frontend)

Read this section verbatim into every delegation prompt.

1. **No `any` types.** Use proper TypeScript types for all variables, parameters, and return values. `unknown` is acceptable when parsing external data before validation.
2. **No direct `fetch()`.** Use the shared axios client from `src/api/client.ts`. This ensures cookie auth, CSRF headers, and 401 refresh are applied uniformly.
3. **No inline styles.** Use Mantine's `style` prop with theme tokens, `className` with CSS modules, or Mantine component props. Never use `style={{ color: '#16A34A' }}` — reference design tokens.
4. **No hardcoded API URLs.** Use `VITE_API_BASE_URL` via the axios client. Never write `fetch('http://localhost:8000/api/v1/...')`.
5. **No mocking of the auth store in feature page tests.** Use the test auth provider wrapper that injects a preset auth state into the Zustand store. This tests the real auth integration path.
6. **All pages must handle loading, error, and empty states.** Every page that fetches data must show: a loading skeleton/spinner while fetching, an error display on failure, and an appropriate empty state message when data is empty.
7. **File size limit: 500 lines per file.** If a component approaches 400 lines, split into sub-components. Extract hooks, utility functions, or sub-views.
8. **No barrel exports from `features/`.** Import directly from the specific file (e.g., `import { useDashboard } from '../features/consolidated-report/useDashboard'`). Barrel exports from `components/` are acceptable.
9. **No `console.log()`.** Remove all console statements before committing. Use structured error boundaries for error reporting.
10. **No `localStorage`/`sessionStorage` for auth.** Auth state is cookie-based. The Zustand auth store holds derived state from `/auth/me`, not tokens.
11. **PEP 604-style union types in TypeScript:** Use `string | null` not `Optional<string>`. Use `Array<T>` or `T[]` consistently (prefer `T[]`).
12. **Google-style JSDoc** on every exported function and component. Include `@param` and `@returns` sections.
13. **Environment variables:** Must be prefixed with `VITE_` to be exposed to the client bundle. Currently defined: `VITE_API_BASE_URL`.
14. **No new dependencies** beyond those listed in the frontend stack (architecture section 1). If genuinely needed, raise as a blocker.