# Spec: Org Tree Admin Page (`/admin/org-units`)

**Sub-batch:** 8a (simple)

---

```
Module:    frontend/src/pages/admin/OrgTreePage.tsx
Test path: frontend/tests/unit/pages/admin/OrgTreePage.test.tsx
API module:  frontend/src/api/admin.ts
Hook:      frontend/src/features/cycles/useOrgUnits.ts
FRs:       FR-002
Exports:   OrgTreePage, useOrgUnits
Imports:
  api/admin.ts: listOrgUnits, patchOrgUnit
  components/DataTable.tsx: DataTable
  components/ErrorDisplay.tsx: ErrorDisplay
  i18n: useTranslation
API:
  GET /admin/org-units — list all org units with metadata
  PATCH /admin/org-units/{id} — update excluded_for_cycle_ids
Tests:
  1. Renders org-unit list with correct columns (code, name, level_code, is_filing_unit, excluded status) on success.
  2. Shows loading skeleton while listOrgUnits is in-flight.
  3. Shows ErrorDisplay on RBAC_001 (403) fetch error.
  4. Shows empty state message when org-unit list is empty.
  5. Toggling exclusion on a row calls patchOrgUnit with updated excluded_for_cycle_ids and shows optimistic update.
Constraints: FCR-001, FCR-002, FCR-004, FCR-005, FCR-009, FCR-010, FCR-013
Gotchas:
  - Route guard: roles=["SystemAdmin", "FinanceAdmin"]. Sidebar appears for both.
  - PATCH is only available to SystemAdmin; FinanceAdmin sees read-only view.
  - `excluded_for_cycle_ids` is a string[] of cycle UUIDs; the PATCH body sends the full updated array (replace semantics).
  - Org units with level_code 0000 are never filing units; the UI should make this clear (badge or tooltip).
  - FR-002: units missing a manager (has_manager: false) must be visually flagged — display a warning icon in the row.
  - FR-002: units with warnings[] must show warning details in a tooltip or expandable row.
```
