# Spec: Vite/TS/React Scaffold + Config Files (simple)

Module: `frontend/` root — `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`
Tests: n/a (gate checks: `pnpm build`, `pnpm lint`, `pnpm exec tsc --noEmit`)

## Exports
None — configuration artifacts only.

## Key Configuration Requirements

**`package.json`**
- Package manager: pnpm 9.x
- Dev deps: TypeScript 5.6.x, Vite 5.4.x, React 18.3.x, ESLint 9.x, Prettier 3.x, Vitest 2.x, React Testing Library 16.x, Playwright 1.48.x
- Runtime deps: react 18.3.x, react-dom 18.3.x, react-router-dom 6.28.x, @tanstack/react-query 5.x, zustand 5.x, axios 1.7.x, react-hook-form 7.x, zod 3.23, @mantine/core 7.x, @mantine/hooks 7.x, react-i18next 15.x, i18next, @tanstack/react-table 8.x
- Scripts: `dev`, `build`, `lint`, `test`, `exec` wrappers matching build plan gate commands

**`vite.config.ts`**
- Plugin: `@vitejs/plugin-react`
- Dev proxy: `/api/v1` → `http://localhost:8000` (preserves cookies for SSO)
- Test: Vitest config pointing to `frontend/tests/setup.ts`, jsdom environment

**`tsconfig.json`**
- Target: ES2022, strict mode enabled
- `moduleResolution`: bundler
- Path alias: `@/` → `frontend/src/`
- Include: `src/**/*`, `tests/**/*`

**`index.html`**
- Root div `id="root"`, script entry `src/main.tsx`
- `lang="zh-TW"` on `<html>`

## Imports
None — root configuration files only.

## Gotchas
- Vite dev proxy must forward cookies (`changeOrigin: true`, no cookie stripping) for SSO callback to work locally.
- `lang="zh-TW"` on `<html>` is required for i18n correctness (NFR-USE-001).
- Lockfile (`pnpm-lock.yaml`) must be committed per architecture Dependency Pinning Strategy.
- `VITE_API_BASE_URL` must be documented in `.env.example`; defaults to `/api/v1` via dev proxy.

## Constraints
FCR-013: Environment variables referenced in this module use the `import.meta.env.VITE_` prefix. No `process.env` references.
