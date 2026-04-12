---
name: 'step-05-finalize'
description: 'Generate DB schema, env vars, brownfield section, build-from-prd readiness validation'
outputFile: '{planning_artifacts}/architecture.md'
---

# Step 5: Schema & Finalize

**Progress:** Step 5 of 5 → Final

**Goal:** Generate database schema (if applicable), environment variables/configuration, brownfield integration section (if applicable), and validate build-from-prd readiness.

---

## Instructions

### 1. Generate Database Schema (If Section 6 Exists)

**Skip if Section 6 was stripped in Step 1** (CLI tools, libraries without storage).

**For projects with storage:** Transform PRD Data Entities (Section 5) into SQL DDL.

**For each Data Entity:**

1. Create table with columns matching entity attributes
2. Apply type mapping from FR Input constraints (e.g., `email (string, RFC 5322)` → `VARCHAR(255) CHECK (...)`)
3. Add indexes for query patterns implied by FRs
4. Define foreign key relationships between entities

**Format:**

```sql
-- =====================
-- [Entity Name]
-- =====================
CREATE TABLE [table_name] (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  [columns from entity attributes],
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
-- Entity: [PRD Entity Name] | FRs: FR-001, FR-002, ...

CREATE INDEX idx_[table]_[column] ON [table]([column]);
```

**Include:**
- UUID primary keys (unless PRD specifies otherwise)
- Foreign keys with explicit references
- Unique constraints where entity requires
- Indexes for common queries
- Timestamps (created_at, updated_at)

Fill Section 6 in `{outputFile}`.

---

### 2. Define Environment & Configuration (If Section 7 Exists)

**If Section 7 is "Environment Variables":**

| Variable | Required | Description |
|----------|----------|-------------|
| DATABASE_URL | Yes | Database connection string |
| [AUTH_VAR] | Yes/No | Based on auth choice |
| [FRAMEWORK_VARS] | Varies | Framework-specific |
| [INTEGRATION_VARS] | Varies | Third-party integrations |

**If Section 7 was replaced with "Configuration Files" table (Step 1):**

| Config File | Path | Purpose |
|-------------|------|---------|
| {file} | {path} | {what it configures} |

Fill Section 7 in `{outputFile}`.

---

### 3. Brownfield Integration (If Section 10 Exists)

**Skip if Section 10 was stripped in Step 1** (Greenfield projects).

If brownfield context was gathered in step 1:

1. Fill Existing Systems table from PRD + charter context
2. Document Integration Adapters for each legacy system
3. Document Legacy Constraints with impact and mitigation
4. Document Coexistence Strategy

Fill Section 10 in `{outputFile}`.

---

### 4. Build-from-prd Readiness Validation

This is the critical quality gate. Verify the architecture document contains every field build-from-prd needs to generate its build plan.

**Project-type-aware checklist (skip checks marked N/A for your project type):**

| Requirement | Source Section | Applies To | Check |
|-------------|---------------|------------|-------|
| language identified | S1 Build Commands | All | Extractable from stack + commands |
| package_manager identified | S1 Build Commands | All | Explicit in Install command |
| test_command defined | S1 Build Commands | All | Explicit and complete |
| src_dir marked | S2 comment | All | `<!-- src_dir: ... -->` present |
| test_dir marked | S2 comment | All | `<!-- test_dir: ... -->` present |
| module paths defined | S4 Path column | All | Every module has a path |
| module test paths defined | S4 Test Path column | All | Every module has a test path (or explicit "—") |
| module exports listed | S4 Exports column | All | Every module has exports |
| module dependencies listed | S4 Depends On column | All | Every module has deps (or "—" for leaf) |
| naming conventions complete | S3 table | All | All rows filled (project-type-appropriate set) |
| error taxonomy complete | S3 taxonomy | All | Covers all error codes from contracts |
| every FR has contract | S5 | All | Cross-ref PRD Section 3 |
| response format defined | S3 | All | Exit codes / HTTP responses / return types |
| logging pattern defined | S3 | All | Sub-section present and populated |
| error propagation defined | S3 | All | Convention documented with patterns |
| side-effect ownership defined | S3 | All | Sub-section present and populated |
| test tiers defined | S8 | All | At least 2 tiers with scope and frequency |
| high-risk areas identified | S8 | All | At least 1 module flagged with test cases |
| implementation order defined | S9 | All | Batch sequence with parallelization notes |
| every entity has schema | S6 | Web, API, Full Stack, Data Pipeline, ML | Cross-ref PRD Section 5 |
| environment variables complete | S7 | Projects with external services | All required vars listed |
| brownfield integration complete | S10 | Brownfield projects only | Existing systems, adapters, constraints |

**Report format:**
```
Readiness Validation: {passed}/{applicable} checks PASS ({skipped} skipped — not applicable to {product_category})
```

**Mandatory: Fix all failures before finalizing.**

---

### 5. Final Coverage Validation

Cross-reference completeness across all sections:

| Check | Status |
|-------|--------|
| Every FR-* has contract | ✓/✗ |
| All FR Error cases have error codes in taxonomy | ✓/✗ |
| Module graph is acyclic | ✓/✗ |
| All module paths exist in directory structure | ✓/✗ |
| All module test paths exist in directory structure | ✓/✗ |
| Implementation batch sequence covers all modules | ✓/✗ |
| Every Data Entity has table (if S6 exists) | ✓/✗ or SKIP |
| Environment variables complete (if S7 is env vars) | ✓/✗ or SKIP |

**If gaps found:** Fix before finalizing.

---

### 6. Finalize Document

Update `{outputFile}` frontmatter:
```yaml
---
status: complete
current_step: 5
prd_source: [path]
prd_checksum: [first 8 chars of sha256 hash of PRD content]
product_category: [category]
completed_at: [date]
---
```

---

### 7. Present Completion

**Summary:**
```
Architecture complete: {outputFile}

- Technology Stack: {language} + {key libs} + {testing}
- Build Commands: {count} defined
- Modules: {count}
- Contracts: {count} ({type}: REST/CLI/Library)
- Test Strategy: {tier count} tiers, {high-risk count} high-risk areas
- Implementation Order: {batch count} batches ({parallel count} parallelizable)
- Database Tables: {count} (or "N/A — stripped")
- Environment Variables: {count} (or "N/A — file-based config")
- Readiness: {passed}/{applicable} PASS ({skipped} skipped)

PRD + Architecture = complete implementation context.
```

**Suggest next step:** "Run `/build-from-prd` to begin implementation."

**No menu** — workflow complete.
