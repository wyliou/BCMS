---
name: 'step-04-testing'
description: 'Define testing strategy, fixture plan, high-risk areas, and implementation batch sequence'
nextStepFile: '{skill_base}/steps/step-05-finalize.md'
outputFile: '{planning_artifacts}/architecture.md'
---

# Step 4: Testing & Build Order

**Progress:** Step 4 of 5 → Next: Schema & Finalize

**Goal:** Define the testing strategy (tiers, fixtures, high-risk areas) and derive the implementation batch sequence from the module dependency graph.

---

## Instructions

### 1. Define Test Tiers

Derive test structure from module complexity, NFRs, and project type.

**Standard 3-tier model (adapt count and scope to project size):**

| Tier | Type | Scope | Speed | When |
|------|------|-------|-------|------|
| 1 | **Unit** | Pure logic: algorithms, calculations, transformations, parsing, validation rules | Fast (<10s) | Every commit |
| 2 | **Component** | Single module with real or realistic data: file I/O, database queries, API calls (mocked external deps) | Medium (<30s) | Every commit |
| 3 | **Integration** | Full pipeline end-to-end: multi-module flows, real data corpus, golden file comparison | Slow (1-5 min) | Before release |

**Adaptation by project type:**

| Project Type | Tier 1 Focus | Tier 2 Focus | Tier 3 Focus |
|--------------|-------------|-------------|-------------|
| Web App / API | Business logic, validators | Route handlers, middleware | API E2E, auth flows |
| CLI Tool | Algorithms, parsing, transformations | Single command with fixture files | Full batch with test corpus |
| Library/SDK | Public API contracts, edge cases | Integration with real dependencies | Consumer contract tests |
| Data Pipeline | Transform logic, schema validation | Stage-level with sample data | Full pipeline with test datasets |
| Desktop/Mobile | State management, business logic | Screen rendering, navigation | E2E user journeys |

**If PRD defines a test corpus (Section 7):** Tier 3 must include full corpus validation.

**If PRD defines NFR for correctness (e.g., Zero False Positives):** Add golden output file comparison to Tier 3.

Fill Section 8 Test Tiers table in `{outputFile}`.

---

### 2. Define Fixture Strategy

For each test tier, define how test data is structured:

| Tier | Fixture Approach |
|------|-----------------|
| Unit | Minimal in-memory objects, factory functions in `conftest.py` or test helpers. Never use heavy external files. |
| Component | Small purpose-built fixture files targeting specific module behaviors. Store in `tests/fixtures/` or create programmatically. |
| Integration | Full test data (corpus, seeded database, recorded API responses). Store in `tests/fixtures/` or `tests/data/`. |

**Golden files (if applicable):**
- Store expected outputs in `tests/fixtures/expected/` (or equivalent)
- Integration tests compare generated output against golden files field-by-field
- Golden files are append-only (new patterns added, existing never removed)

**conftest.py shared fixtures (derive from project needs):**
- Configuration fixture (loaded from test config files)
- Data factory functions (create minimal test objects)
- Temporary output directory (for write tests)
- Database fixtures (if applicable): test database, seed data, cleanup

Fill Section 8 Fixture Strategy in `{outputFile}`.

---

### 3. Identify High-Risk Test Areas

Scan the module table (Section 4) and PRD for modules that need extra test coverage.

**High-risk indicators:**
- **Silent failure potential:** Module produces wrong data instead of errors (e.g., merge cell propagation, data extraction with heuristics)
- **Complex algorithms:** Precision-sensitive math, multi-step cascades, heuristic scoring (e.g., header detection, weight allocation)
- **Multiple edge cases:** PRD Section 7 lists specific edge cases or examples
- **Shared dependency:** Module used by many others — bug propagates widely (e.g., data models, merge tracking)
- **Large FR count:** Module owns 4+ FRs — higher complexity, more things to get wrong

For each high-risk module, list:
- The risk type (silent failure, precision, edge cases, etc.)
- Minimum test cases needed (specific scenarios, not just count)

Fill Section 8 High-Risk Test Areas table in `{outputFile}`.

---

### 4. Derive Implementation Batch Sequence

From the module dependency graph (Section 4 Import Graph), derive the topological build order:

**Algorithm:**
1. Identify leaf modules (no dependencies) → Batch 0
2. For each subsequent batch: include modules whose ALL dependencies are in previous batches
3. Continue until all modules are assigned
4. Mark which batches can run in parallel (modules within a batch are independent)

**Format:**

| Batch | Modules | Depends On | Parallelizable |
|-------|---------|------------|----------------|
| 0 | {leaf modules} | — | Yes |
| 1 | {modules depending only on Batch 0} | Batch 0 | Yes |
| ... | ... | ... | ... |
| N | {orchestrator} | All previous | No |
| N+1 | {entry point} | Batch N | No |

**Identify:**
- **Critical path:** The longest chain of sequential dependencies
- **Bottleneck modules:** Modules with the most complex logic or most FRs (likely need the most implementation time)
- **Early validation spikes:** Any build/size/integration checks that should run early (e.g., exe size validation, database connection test, API auth flow)

Fill Section 9 in `{outputFile}`.

---

### 5. Checkpoint

Present to user:
- Test tier summary (tier count, estimated test counts, run frequency)
- Fixture strategy (types of fixtures per tier)
- High-risk modules list (count with brief risk description)
- Implementation batch sequence (batch count, parallelization opportunities)
- Bottleneck identification

**Menu:**
- **[C] Continue** - Proceed to Step 5: Schema & Finalize
- **[R] Revise** - Adjust testing strategy or build order
- **[P] Party Mode** - Discuss with architect/dev/test agents
- **[D] Deep Dive** - Analyze risk areas with advanced methods
- **[X] Exit** - Save progress and stop

**On [P] Party Mode:**
Invoke `_party-mode` skill with:
- `topic`: "Testing strategy and implementation order for [project name]"
- `content`: Test tiers + high-risk areas + batch sequence
- `focus_agents`: `architect`, `dev`, `tea`

**On Continue:** Update frontmatter `current_step: 5`, load `{nextStepFile}`
