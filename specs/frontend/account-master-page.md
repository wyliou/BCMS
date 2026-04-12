# Spec: Account Master Page (`/admin/accounts`)

**Sub-batch:** 8a (simple)

---

```
Module:    frontend/src/pages/admin/AccountMasterPage.tsx
Test path: frontend/tests/unit/pages/admin/AccountMasterPage.test.tsx
API module:  frontend/src/api/accounts.ts
Hook:      frontend/src/features/cycles/useAccounts.ts
FRs:       FR-007, FR-008
Exports:   AccountMasterPage, useAccounts
Imports:
  api/accounts.ts: listAccounts, upsertAccount, importActuals
  components/DataTable.tsx: DataTable
  components/ErrorDisplay.tsx: ErrorDisplay
  i18n: useTranslation
API:
  GET /accounts?category= — list account codes (filter by operational|personnel|shared_cost)
  POST /accounts — upsert by natural key `code` (create or update; body: { code, name, category, level })
  POST /cycles/{cycle_id}/actuals — multipart CSV/XLSX actuals import; response: ImportSummary
Tests:
  1. Renders account list table with columns (code, name, category, level) on success.
  2. Submitting the upsert form with valid data calls POST /accounts and shows success notification.
  3. Shows row-level ErrorDisplay (ACCOUNT_002) after actuals import failure with details[] table.
  4. Category filter dropdown refetches list with correct query param.
  5. Loading skeleton shown while listAccounts is pending.
Constraints: FCR-001, FCR-002, FCR-004, FCR-005, FCR-007, FCR-009, FCR-010, FCR-013
Gotchas:
  - Route guard: roles=["SystemAdmin", "FinanceAdmin"]. Upsert form only shown to SystemAdmin; FinanceAdmin reads list only.
  - POST /accounts is upsert by natural key `code` — no PATCH endpoint. Submitting an existing code updates it.
  - Actuals import requires a cycle_id; page must either read from route params or provide a cycle selector.
  - ACCOUNT_002 batch validation error uses ErrorDisplay with collapsible row-level table (collect-then-report pattern).
  - `category` values are enum: "operational" | "personnel" | "shared_cost" — shown as English per NFR-USE-001.
  - `level` is an integer (org level code e.g. 4000, 2000, 1000...).
  - FR-007: human-category and shared_cost-category accounts are distinguished by `category` field; the list filter allows browsing by category.
```
