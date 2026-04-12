---
name: build-from-prd
description: Implement a project from PRD and architecture docs
---

# Build from PRD

Orchestrate a multi-phase build by dispatching subagents, running gates, and managing state. You manage the build pipeline — subagents read specs and write code. You do not write implementation code or make design decisions outside of explicit decision points (ambiguity resolution, retry strategy, gate failure triage).

## Operating Principles

- **Files are the bus.** Cross-agent communication goes through `build-plan.md`, `specs/*.md`, and `build-log.md`. Pass file paths to agents, never paste contents.
- **Parallelism is the default.** Independent work goes in a single message with multiple tool calls. Cap at 4 parallel Agent calls per message — more risks resource contention and makes failure triage harder.
- **Boundaries.** When a gate fails, re-delegate — do not fix the code yourself. Your job is to identify which module failed, what the error was, and dispatch a retry with that context. The only code you write directly is gate scripts, build-log updates, and small artifact edits (e.g., appending a rule to build-plan.md §4).
- **Resume rule.** On compaction or session resume, run the **Resumption Procedure** before any other action.

### Context Management

Your context is a finite resource. These rules keep it lean:

- **Never read the PRD in main context.** Subagents read it. You know the project through `build-plan.md` only.
- **Never read agent results on success.** Gate results (test pass/fail, lint output) are your signal. Only read agent output when a gate fails and you need to diagnose.
- **Read `build-plan.md` in sections, not whole.** After Phase 1 verification, read only §8 (batch plan) for dispatch and §5 (CC) for gate sweeps. Never re-read §1-4 unless troubleshooting a scaffold issue.
- **Delegate all implementation.** Do not write module code in main.
- **Summarize, don't accumulate.** After each batch, log a one-line result to `build-log.md`. Do not carry per-module details in your working memory — the log has them.
- **Use `run_in_background`** for full test suite runs during Phase 3 milestone gates and Phase 4. Continue with other work while they run.

## Tools

- `Agent` — `general-purpose` for all implementation; `Explore` for codebase questions. Use `isolation: "worktree"` for batch implementations. Model selection: `opus` for the plan architect and all batch implementers (first-attempt success rate matters more than per-token cost — a failed batch blocks the pipeline); `sonnet` for spec writers and scaffold (well-constrained work with clear inputs). Never use `haiku` for implementation.
- `TaskCreate` / `TaskUpdate` / `TaskList` — task graph for the build.
- `Skill` — invoke `/simplify` directly in main context.
- `AskUserQuestion` — whenever you would otherwise guess.
- `Bash` with `run_in_background: true` for long test runs you want to overlap with other work.
- `Read`, `Edit`, `Grep`, `Glob` — artifact maintenance and gate sweeps.

## Artifacts

| File | Purpose | Written by |
|------|---------|-----------|
| `build-plan.md` | Build config, FR map, conventions, constraints, shared utilities, batch plan with exports | Plan agent (Step 1) |
| `specs/{module}.md` | Per-module spec (complex only) | Spec agents (Step 2) |
| `build-log.md` | Structured state log — YAML front matter + append-only prose | Orchestrator |

---

## Phase 1: Plan

Two sequential steps: produce the build plan, then (conditionally) produce specs for complex modules.

### Step 1 — Build Plan

One `general-purpose` agent (opus) reads the PRD and writes `build-plan.md`.

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  description: "PRD → build plan",
  prompt: <plan brief>
})
```

**Plan brief:**
````
You are the architect for this build. Read the PRD, architecture docs, package manifest, source dir, and config files. Produce a single planning document. Do not implement code.

Read: {prd_path} (stop and report if missing), {arch_path} (optional), the package manifest, and the source directory.

Write `{project_root}/build-plan.md` with these sections:

## 1. Build Config
Table: language, package_manager, test_command, lint_command, type_check_command, format_command, build_command, run_command, src_dir, test_dir, stub_detection_pattern.

## 2. Gates
Table: which gates are enabled (lint, type_check, format, tests, integration_tests, build, stub_scan). Disable when the corresponding command is empty.

## 3. Project Summary
Paths, stack, existing-code assessment. If source exists: map current modules and public interfaces.

## 4. Conventions
Stack, error handling strategy, logging pattern, test requirements (3-5 per function: happy/edge/error), platform notes.
**Subagent Constraints** subsection: no stubs, no type redefinition, no new deps without approval, no cross-module mocking, fixture scoping rules, file size limit (500 lines).

## 5. Cross-Cutting Constraints
Rules that cross module boundaries and could be violated by independently-built subagents. Only include constraints where **two or more modules must agree on a shared rule** and getting it wrong would cause a subtle bug. Do NOT include single-module best practices.

Each entry: **ID** (CC-NNN), **Concern** (one sentence), **Affected modules**, **Check** (grep/inspection step for gate sweep).

Scan the PRD for these categories:
- ownership_uniqueness (error codes, log messages emitted by exactly one module)
- sequencing_dependency (steps that must run in a specific order across modules)
- representation_variant (fields appearing in multiple forms across modules)
- shared_convention (numeric formats, units, precision rules shared by multiple modules)

## 6. Shared Utilities
Functions/constants used by 2+ modules: signature, placement, consumers. Keep brief (<5 lines each).

## 7. FR → Subsystem Map
`{fr_id}: subsystem — one-line acceptance criterion`.

## 8. Batch Plan
Modules grouped by dependency order. Each module entry:
- path, test_path, FRs
- **exports** (function/component signatures with types)
- **imports** (from which modules)
- **complexity**: simple (<5 functions, pure) / moderate (I/O, 5-10 functions) / complex (orchestration, >10 functions)

Batch rules:
- Target ≤ ceil(total_modules / 5) batches.
- Two non-dependent modules can share a batch.
- Single-module batches → merge into nearest compatible batch.
- Dependency order; alphabetical within a batch.

## 9. Ambiguities
Unclear or contradictory requirements. Note a safe default for each.

PRD is source of truth. Distill prose; preserve parameters verbatim. Be exhaustive on the exports table.
````

### Verify Plan

1. `Read` `build-plan.md`. Re-launch if missing/empty.
2. Check: exports table has concrete signatures, FR map complete, batch count reasonable.
3. Check: cross-cutting constraints focus on multi-module risks, not single-module best practices. Prune if >15 entries.
4. **Resolve ambiguities** with one batched `AskUserQuestion` call.
5. **Create task graph** via `TaskCreate`: Specs (if needed) → Scaffold → Batch 0..N → Simplify → Validate → Commit.
6. Initialize `build-log.md`:

```yaml
---
project: {name}
prd: {path}
started: {date}
subsystem: {backend|frontend|...}
last_phase: plan
last_batch: -1
total_batches: {N}
---
## Log
- {date} Plan complete. {N} batches, {M} CC entries.
```

### Step 2 — Specs (complex modules only)

**Write specs only for complex modules** (orchestration, >10 functions, multi-step pipelines). Simple and moderate modules use the exports table and FR list in `build-plan.md` §8 directly — their batch implementers read the PRD for detail.

**Skip this step entirely if no complex modules exist.** Update `build-log.md` and advance to Phase 2.

If complex modules exist, launch parallel agents (sonnet), grouped by batch:

```
Agent({
  subagent_type: "general-purpose",
  model: "sonnet",
  description: "Specs for complex modules",
  prompt: <spec brief>
})
```

**Spec brief:**
````
Write spec files for these complex modules: {module_list}

Read `{project_root}/build-plan.md` (exports table = your contract, §5 = cross-cutting constraints).
Read the PRD at {prd_path} for FR details.

For each module, write `specs/{module_name}.md`:
1. Module path and test path.
2. **FRs** — distill prose; preserve ALL concrete parameters verbatim.
3. **Exports** — match build-plan.md exactly.
4. **Imports** — module path + symbols. Required call order with rationale.
5. **Gotchas**, **Verbatim outputs** (user-visible strings copied from PRD).
6. **Cross-cutting constraints** — for each CC entry in build-plan.md §5 that lists this module, copy the ID + Check line.
7. **Tests** — 3-5 per function. Each enumerated variant gets its own test case.

Cross-validate: every Import resolves to an Export in build-plan.md; every applicable CC entry is referenced.
````

### Verify Specs

1. Spot-check specs — PRD parameters preserved, call ordering documented.
2. `Grep` `specs/` for each CC entry ID; verify affected modules have it.
3. Update `build-log.md`: `last_phase: specs`. Append log line.

---

## Phase 2: Scaffold

- **Greenfield:** create directories, manifest with deps, install, cross-cutting infrastructure (error types, constants, models), test config + fixtures.
- **Existing codebase:** extend minimally — only new files for new modules.
- **Dev tooling:** install lint/type-check/format tools from Build Config now.
- **Shared utilities:** implement everything in build-plan.md §6.
- **Delegation:** for >10 modules, delegate scaffold to a `general-purpose` Agent (`sonnet`).
- **Gate:** test collection dry-run + sample import resolves + lint + type-check pass.

Update `build-log.md`: `last_phase: scaffold`. Append log line.

---

## Phase 3: Batches

For each batch in dependency order:

### 1. Dispatch

Mark task in_progress. Launch modules in parallel inside worktrees (max 4 agents per message). If a batch has >4 modules, split into sequential waves of ≤4.

```
Agent({
  subagent_type: "general-purpose",
  model: "opus",
  isolation: "worktree",
  description: "Implement {module_name}",
  prompt: <batch brief>
})
```

**Batch brief:**
````
Implement and test: {subsystem_name}
Module: {module_path} | Tests: {test_path}

{IF complex}: Read `{project_root}/specs/{module_spec}.md` for your complete spec.
{IF simple/moderate}: Your contract is in `{project_root}/build-plan.md` §8, batch {N}, module {name}. Exports, imports, and FRs are defined there. Read the PRD at {prd_path}, searching for these specific FRs: {fr_ids}. Do NOT read the entire PRD.

Read `{project_root}/build-plan.md` §4 for conventions and §5 for cross-cutting constraints that affect you.
Read source files you import — understand them, do NOT reimplement.

The project currently has {passing_test_count} passing tests from prior batches. Your changes must not break them.

Rules:
- EXPORTS must match the plan/spec. IMPORTS from earlier batches are implemented — call them, do NOT mock.
- Modify only {module_path} and {test_path}.
- If a required import is missing or has wrong signature, STOP and report.
- Before finishing, run: {lint_command}, {type_check_command}, {test_command} {test_path}.
````

For simple modules, group 2-3 into one Agent call to reduce overhead.

### 2. Post-batch gate

- **Stub detection:** `Grep` for `{stub_detection_pattern}` in changed files.
- **Format + lint + type check:** parallel `Bash` calls.
- **Tests:** batch tests, then smoke test (`-x` / `--bail`).
- **Milestone gates** (midpoint and final batch): full test suite (use `run_in_background`) + CC sweep.

### 3. Merge or recover

**On pass:** merge worktree, update task, append one-line result to build-log.
**On failure:** apply retry budget:

| Attempt | Strategy |
|---------|----------|
| 1 | Standard brief |
| 2 | Add failure context — what failed, the error output, and what to fix |
| 3 | Include full failing test/lint output verbatim in the prompt |
| After 3 | `AskUserQuestion` to escalate |

**Partial advancement:** merge passing modules, re-delegate failing ones.

Update `build-log.md`: `last_batch: {N}`. Per-module pass/fail status.

---

## Phase 4: Simplify + Validate

1. Run `/simplify` in main context. Then run full test suite to verify no regressions.
2. **If test data exists:** run the app against test data, categorize results, fix code bugs (max 3 rounds).
3. **Final gate:** full test suite + CC sweep + file-size check (500-line limit).
4. **Summary to user:** test count, validation results, remaining issues.
5. **Artifact cleanup:** `AskUserQuestion` — keep or delete build-plan.md / specs/ / build-log.md.

Update `build-log.md`: `last_phase: complete`.

---

## Build Log Format

`build-log.md` has YAML front matter for machine-readable state, plus append-only prose:

```yaml
---
project: BCMS
prd: docs/PRD.md
started: 2026-04-12
subsystem: backend
last_phase: batch  # plan | specs | scaffold | batch | simplify | complete
last_batch: 3
total_batches: 7
module_status:
  core_errors: pass
  core_logging: pass
  infra_db: pass
  domain_audit: pass
  domain_cycles: fail-1  # fail-{attempt}
---
## Log
- 2026-04-12 Plan complete. 7 batches, 12 CC entries.
- 2026-04-12 Specs complete. 4 complex module specs written.
- 2026-04-12 Scaffold complete. Deps installed, gates green.
- 2026-04-12 Batch 0 complete. 5/5 modules pass. 42 tests.
- 2026-04-12 Batch 1 complete. 3/3 pass. 78 tests total.
...
```

The YAML front matter is the recovery anchor. Prose is for human context. One line per event.

---

## Recovery

### Resumption Procedure

On context compaction or session resume:

1. Read `build-log.md` YAML front matter → `last_phase`, `last_batch`, `module_status`.
2. `TaskList` to reconcile.
3. Resume from `last_phase` / `last_batch`. Re-delegate only modules with `fail-*` status.
4. Do NOT re-read the PRD or re-run Step 1 — artifacts on disk are source of truth.

### Recovery Table

| Problem | Action |
|---------|--------|
| Subagent fails tests or leaves stubs | Apply retry budget |
| Cross-module signature mismatch | Fix implementer to match spec/plan |
| Implementation diverges from PRD | Verify spec against PRD, fix spec, re-delegate |
| Tests pass individually, fail together | Check shared mutable state, singleton teardown |
| Duplicate code across subagents | `/simplify` in Phase 4 |
| Ambiguous requirement | `AskUserQuestion` — never guess |
| Context too large | Delegate to fewer, larger subagents |

---

## Multi-Subsystem Builds

When a project has multiple subsystems (e.g., backend + frontend):

1. Complete the first subsystem fully (through Phase 4).
2. Start a new build cycle for the next subsystem:
   - Step 1 produces a **new** `build-plan.md` (overwrite or use `{subsystem}-build-plan.md`).
   - Specs go in `specs/{subsystem}/`.
   - `build-log.md` gets a new YAML section: update `subsystem`, reset `last_phase` and `last_batch`.
3. The new plan architect reads the completed subsystem's code (not its plan artifacts) to understand available APIs.
4. Cross-subsystem constraints go in the new plan's §5 (e.g., "frontend must use these exact API paths").
