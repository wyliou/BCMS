# Spec: domain/_shared/queries (§5.4)

**Batch:** 3
**Complexity:** Simple

Module: `backend/src/app/domain/_shared/queries.py`
Tests: `backend/tests/unit/_shared/test_queries.py`
FRs: FR-008 (actuals import), FR-024 (personnel import), FR-027 (shared cost import)

---

## Exports

```python
async def org_unit_code_to_id_map(db: AsyncSession) -> dict[str, UUID]:
    """Return a mapping of org_unit.code to org_unit.id for all org units.

    Executes a single SELECT over the org_units table. Used by every importer
    that accepts a user-supplied dept_id / org_unit_code column and needs to
    translate to internal UUID for FK storage.

    Args:
        db: Async database session (injected per-request via FastAPI Depends).

    Returns:
        dict[str, UUID]: Keys are org_unit.code strings (e.g. '4023'),
                         values are org_unit.id UUIDs.
    """
```

---

## Imports

`infra.db`: `AsyncSession`
`sqlalchemy`: `select` (2.0 style)
`domain.cycles.models` (or wherever `OrgUnit` ORM model lives — Batch 4): `OrgUnit`

**Batch 3 dependency note:** `OrgUnit` ORM model ships in Batch 4 (`domain/cycles/models.py`). In Batch 3, the model class must be imported via `TYPE_CHECKING` guard or the query must reference the table by string name via `text()`. Recommended approach: use `from __future__ import annotations` and a deferred import, with Batch 4 resolving the final import. Flag for Batch 4 integration check.

---

## Tests

1. **`test_org_unit_code_to_id_map_happy_path`** — seed 3 org unit rows; assert returned dict has 3 entries mapping code → UUID correctly.
2. **`test_org_unit_code_to_id_map_empty_table`** — empty org_units table; assert empty dict returned (no error).
3. **`test_org_unit_code_to_id_map_unknown_code_not_in_map`** — seed 2 units; assert a code not seeded is absent from dict (callers check presence for PERS_001/SHARED_001/ACCOUNT_002 errors).
4. **`test_org_unit_code_to_id_map_request_scoped`** — verify two separate calls within the same request context share the same dict reference (or at minimum return equal dicts) without issuing a second DB query (test via query count assertion or mock).

---

## Constraints

None (CR-018 applies to callers, not this module).

**CR-018 — `dept_id` column is org_unit code, not UUID (FR-024, FR-027)**
*"The `dept_id` column from the CSV is treated as `org_units.code`. Translate via `org_unit_code_to_id_map(db)` from `domain/_shared/queries`. Unknown codes raise `PERS_001` / `SHARED_001` with a row-level error."*
This module PROVIDES the map. Callers are responsible for raising the appropriate error on lookup miss.

---

## Gotchas

- **Request-scoped caching:** The function should be wrapped as a FastAPI `Depends` provider at the route layer so it is called once per request, not once per row. Do NOT use a module-level global cache — that would bleed across requests and is not testable. Typical pattern:
  ```python
  async def get_org_unit_map(db: AsyncSession = Depends(get_session)) -> dict[str, UUID]:
      return await org_unit_code_to_id_map(db)
  ```
  Importers receive the map as a constructor/function argument, not by calling `org_unit_code_to_id_map` directly.
- **No filtering:** Returns ALL org units including non-filing ones. The caller (validator) checks whether a submitted `dept_id` appears in the map; filtering by `is_filing_unit` is the validator's responsibility if applicable.
- **Codes are strings:** `org_unit.code` is a string (e.g. `"4023"`, `"1000"`). Do not cast to int.
