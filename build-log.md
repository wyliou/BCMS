# BCMS Build Log

Append-only log of build-from-prd phase transitions, batch results, and recovery events. Authoritative recovery anchor — survives context compaction.

---

## 2026-04-12 — Phase 1 / Stage A complete
- Architect (Plan subagent) read PRD v4.3 + architecture.md and produced 3 artifacts.
- Plan subagent ran in read-only mode → returned artifacts as text → Tech Lead persisted them to disk.
- `build-plan.md`: 7 backend batches (Batch 0–6) over 11 backend modules + deferred frontend (Batches 7–8). Batch 0 foundation, Batch 1 audit, Batch 2 security+notifications (parallel pair), Batch 3 accounts, Batch 4 cycles, Batch 5 upload quartet (templates/budget/personnel/shared_costs, parallel), Batch 6 consolidation + orchestrators + API tail.
- `build-context.md`: Python 3.12 + FastAPI + SQLAlchemy async + Pydantic + pytest + ruff + pyright + uv; 17 subagent constraints.
- `consistency-registry.md`: 38 CR entries covering ownership_uniqueness, sequencing_dependency, detection_with_fallback, representation_variant, shared_convention, identifier_casing, input_robustness.
- 12 ambiguities flagged for Tech Lead resolution — toolchain mismatch (uv/ruff/pyright vs user-global pip/black/mypy) is top priority.

## 2026-04-12 — Ambiguity resolution (user decisions)
- Toolchain: **uv + ruff + pyright** (architecture.md wins over user-global black/mypy). `pyproject.toml` dev deps: ruff 0.7.x, pyright 1.1.x, uv 0.5.x.
- FR-002 exclude: **PATCH /admin/org-units/{id}** sets `excluded_for_cycle_ids JSONB` on org_units. Cycle-open re-checks. Audit logged.
- FR-017 sync shape: **201 + {file_url, expires_at}** for ≤BC_ASYNC_EXPORT_THRESHOLD units; **202 + {job_id}** for async. Documented in OpenAPI.
- FR-005 reminders: **default-on [7, 3, 1]** days_before on cycle open; PATCH endpoint to change; empty list disables.
- All four decisions match build-plan.md §7 defaults — no plan edits required. Stage B writers will treat these as locked.
- Remaining ambiguities (items 4, 5, 9–12 in build-plan §7) have safe defaults already baked into the plan and will be surfaced only if they block a batch.

## 2026-04-12 — Phase 1 / Stage B complete
- 3 spec-writer subagents (sonnet) ran in parallel, one per batch group.
- 30 spec files written under `specs/` covering all 17 Batch 0-1 modules + 5 Batch 2-3 modules + 8 Batch 4-6 modules.
- Cross-validation:
  - Every CR-001..CR-038 is referenced in ≥1 affected spec (sweep passed).
  - Every FR-001..FR-029 is covered by ≥1 spec (sweep passed).
  - Import dependency graph: every module's imports resolve to an earlier batch or Batch 0 shared utilities.
  - Orchestrator call order honors CR-004, CR-005, CR-006, CR-007, CR-008.
- Open risk: `domain_accounts` imports `cycles.assert_open` but `cycles` ships in a later batch. Spec flags this with a recommended deferred-import pattern (TYPE_CHECKING or runtime lazy-import). Resolution deferred to Batch 3 subagent.

## 2026-04-12 — Phase 2 / Scaffold complete
- Sonnet agent scaffolded greenfield monorepo under `backend/`.
- uv 0.8.15, Python 3.12.11. 68 pinned deps installed. uv.lock generated.
- Gates: ruff PASS, pyright PASS, pytest --collect-only PASS (1 smoke test).
- Deferred to Batch 0: alembic 0001_baseline.py, infra/db/base.py, core/security/* implementations, infra/tabular.py. All are in the Batch 0 scope anyway.
- Test scaffold: unit/integration/api/fixtures subtrees created with empty __init__.py.

