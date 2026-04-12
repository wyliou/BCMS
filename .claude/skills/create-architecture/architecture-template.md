---
status: in-progress
current_step: 1
prd_source:
prd_checksum:
product_category:
completed_at:
---

# Architecture: {{project_name}}

> Generated: {{date}}
> PRD: {{prd_path}}

<!--
=============================================================================
AI IMPLEMENTATION GUIDE

This document + PRD = complete implementation context.
- PRD defines WHAT (requirements with Input/Rules/Output/Error)
- Architecture defines HOW (stack, structure, patterns, specifications)

IMPLEMENTATION ORDER:
1. Install tech stack dependencies (use Build Commands)
2. Create directory structure (use src_dir/test_dir markers)
3. Implement modules following boundaries (use Path, Exports, Depends On)
4. Build contracts matching module assignments
5. Apply coding patterns consistently
6. Follow implementation batch sequence (Section 9)

RULES:
- Follow naming conventions exactly
- Use error codes from taxonomy
- Keep modules isolated per boundaries
- Follow logging pattern for all log output
- Respect side-effect ownership
- Follow error propagation convention
=============================================================================
-->

---

## 1. Technology Stack

<!-- Categories are project-type-adaptive. Step-02 selects the relevant set. -->

| Category | Choice | Version | Rationale |
|----------|--------|---------|-----------|
| | | | |

### Build Commands

| Command | Value |
|---------|-------|
| Install | |
| Test | |
| Lint | |
| Type Check | |
| Format | |
| Build | |

### Dependency Pinning Strategy

<!-- Define pinning rules: exact pin for locked deps, compatible range for runtime, minimum for dev tools. -->

---

## 2. Project Structure

<!-- src_dir: src/ -->
<!-- test_dir: tests/ -->

```
project/
├── src/
├── tests/
└── ...
```

---

## 3. Coding Patterns

### Naming Conventions

<!-- Rows are project-type-adaptive. Step-02 fills the relevant set. -->
<!-- Web App: Components, Utilities, Functions, DB Tables, API Routes, Constants, Types -->
<!-- CLI Tool: Source files, Test files, Functions, Classes/Models, Constants, Config keys, Error codes -->
<!-- Library: Source files, Test files, Functions, Classes, Constants, Public API, Types -->

| Element | Convention | Example |
|---------|------------|---------|
| | | |

### Response Format

<!-- Project-type-adaptive. Step-02 fills the relevant format. -->
<!-- Web/API: HTTP JSON responses. CLI: exit codes + stdout/stderr. Library: return types + exceptions. -->

### Error Code Taxonomy

<!-- Project-type-adaptive. Step-02 fills from PRD error catalog. -->
<!-- Web/API: HTTP status code mapping. CLI: exit codes + error code ranges. Library: exception types. -->
<!-- Always add domain-specific prefixes from PRD Section 3 capability area headers. -->

### Logging Pattern

<!-- Define log format, levels, targets, and what gets logged.
Derive from PRD Section 7 (if present) and FR logging requirements. -->

### Error Propagation Convention

<!-- Define how errors flow between modules.
Common patterns:
- Raise immediate: single fatal error, raise exception
- Collect-then-report: accumulate errors within a phase, return error list
Document which modules use which pattern and how the orchestrator handles both. -->

### Side-Effect Ownership

<!-- Define which modules own which side effects.
Each side effect (file I/O, network calls, logging, database writes) should have exactly one owner.
Non-owners must delegate to the owning module. -->

---

## 4. Module Boundaries

| Module | Path | Test Path | Responsibility | Implements | Exports | Depends On |
|--------|------|-----------|----------------|------------|---------|------------|
| | | | | FR-* | | |

### Import Graph

<!-- Directed dependency graph between modules.
Format: module-a → module-b (what it uses)
Verify: graph must be acyclic. -->

**Module Rules:**
- Each module owns its FRs completely
- Cross-module calls go through exported interfaces
- Side effects respect ownership table
- Orchestrator modules coordinate pipeline sequence, contain no business logic

---

## 5. Contracts

<!-- Contract format is project-type-adaptive. See step-03 for all formats. -->
<!-- Each contract entry includes Module: field mapping it to Section 4 -->
<!-- Common formats: REST endpoints (web/API), CLI commands, Library API, Data Flow, Resource Defs, Service Contracts, Screen Contracts -->

---

<!-- CONDITIONAL: Include Section 6 only if project has persistent storage (Web App, API Service, Full Stack, Data Pipeline, ML, Microservices). Strip for CLI Tool, Library, Plugin without storage. -->

## 6. Database Schema

<!--
Generated from PRD Data Entities.
Includes: tables, constraints, indexes, relationships.

Format:
```sql
CREATE TABLE table_name (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ...
);
-- Entity: [name] | FRs: FR-*
```
-->

---

<!-- CONDITIONAL: Include Section 7 only if project uses environment variables or external services. For projects with file-based-only config, replace with Configuration Files table. -->

## 7. Environment & Configuration

<!-- For projects with env vars: -->
<!-- | Variable | Required | Description | -->
<!-- For projects with file-based config only: -->
<!-- | Config File | Path | Purpose | -->

---

## 8. Testing Strategy

### Test Tiers

<!-- Define test structure derived from module complexity and NFRs.
Typical tiers: Unit (pure logic), Component (single module + fixtures), Integration (end-to-end pipeline).
Adapt tier count and scope to project size. -->

| Tier | Type | Scope | Speed | When |
|------|------|-------|-------|------|
| | | | | |

### Fixture Strategy

<!-- Define how test data is structured:
- Unit: minimal in-memory or mock data
- Component: small purpose-built fixture files
- Integration: full test corpus or seeded database
- Golden files: expected outputs for regression validation (if applicable) -->

### High-Risk Test Areas

<!-- Identify modules with highest test priority based on:
- Silent failure potential (wrong data, not errors)
- Complex algorithms (precision, heuristics, state machines)
- Multiple edge cases documented in PRD Section 7 -->

| Module | Risk | Minimum Test Cases |
|--------|------|-------------------|
| | | |

---

## 9. Implementation Order

### Batch Sequence

<!-- Derived from Section 4 module dependency graph via topological sort.
Group modules with no inter-dependencies into parallel batches.
Identify critical path and bottleneck modules. -->

| Batch | Modules | Depends On | Parallelizable |
|-------|---------|------------|----------------|
| | | | |

---

<!-- CONDITIONAL: Include Section 10 only for Brownfield projects. Strip entirely for Greenfield. -->

## 10. Legacy Integration (Brownfield Only)

### Existing Systems

| System | Integration Type | Protocol | Notes |
|--------|-----------------|----------|-------|
| | | | |

### Integration Adapters

<!-- For each legacy system:
- Direction: Inbound / Outbound / Bidirectional
- Protocol: REST / SOAP / JDBC / File / MQ
- Data Format: JSON / XML / CSV / Binary
- Auth: How to authenticate
- Error Handling: How to handle failures -->

### Legacy Constraints

| Constraint | Impact | Mitigation |
|------------|--------|------------|
| | | |

### Coexistence Strategy

**Strategy:** {{Parallel Run / Strangler Fig / Big Bang / Phased Cutover}}
**Sync Mechanism:** {{How data stays in sync during transition}}
**Cutover Criteria:** {{When to fully switch to new system}}
