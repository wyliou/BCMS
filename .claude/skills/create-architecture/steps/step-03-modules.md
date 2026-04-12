---
name: 'step-03-modules'
description: 'Define module boundaries, inter-module interfaces, project-type-adaptive contracts, and cross-validate'
nextStepFile: '{skill_base}/steps/step-04-testing.md'
outputFile: '{planning_artifacts}/architecture.md'
---

# Step 3: Modules & Contracts

**Progress:** Step 3 of 5 → Next: Testing & Build Order

**Goal:** Define module boundaries with paths/exports/dependencies, inter-module interfaces, project-type-adaptive contracts, and cross-validate consistency.

---

## Instructions

### 1. Extract Capability Areas

From PRD Section 3:
- `### Capability Area` section headers → each becomes a potential module
- FRs grouped under each header → define module responsibilities
- FR dependencies → inform module dependency graph
- Journeys/Workflows → inform flow between modules

### 2. Define Module Boundaries

Create the enhanced module table with all columns build-from-prd needs:

| Module | Path | Test Path | Responsibility | Implements | Exports | Depends On |
|--------|------|-----------|----------------|------------|---------|------------|
| {area} | `src/{path}/` | `tests/{path}/` | {what it does} | FR-001, FR-002, ... | {exported functions/classes} | {other modules} |

**Deriving each column:**
- **Path:** From directory structure defined in Step 2. Follow framework conventions.
- **Test Path:** Mirror source path under test directory.
- **Responsibility:** One-line summary of what the module does.
- **Implements:** List all FR IDs this module handles (from the matching capability area section).
- **Exports:** List the public functions/classes/types this module exposes. Derive from FR outputs — what other modules need to call.
- **Depends On:** List other modules this one imports from. Derive from FR dependency chains and data flow between areas.

**FR-to-module responsibility validation:** For each module, verify that every listed FR's Input/Rules logically belong to this module's responsibility. If an FR depends on another FR in the same capability area, they should be in the same module. If an FR's logic is split across two modules, document which part belongs where.

**Orchestrator module guidance:** If the project has a pipeline/batch/request flow, one module should be the thin orchestrator:
- It coordinates the sequence of module calls
- It contains NO business logic (no regex, no math, no parsing)
- It owns error collection, status aggregation, and pipeline short-circuit decisions
- It owns path construction and file I/O delegation
- Document these responsibilities explicitly in the orchestrator's Responsibility column

**Module size warning:** Flag any module with 5+ FRs as potentially exceeding file size limits. Add a split note: identify a clean boundary for splitting if the module exceeds the project's line limit during implementation. Ensure the split wouldn't change public exports (exports should already be separated).

### 3. Define Inter-Module Interfaces

For each dependency edge in the module table, document the interface:

```markdown
### {Consumer Module} → {Provider Module}
- **Provider function:** {function name from exports}
- **Data flow:** {what data passes between them}
- **Error propagation:** {how errors from provider surface in consumer — raise or collect pattern from Section 3}
```

**For orchestrator modules:** Additionally document any orchestration logic (decision sequences, fallback chains, conditional calls) that the orchestrator owns. Example: "batch.py resolves inv_no: check ColumnMapping → if absent, call fallback → pass result to extraction."

This ensures subagents in build-from-prd know exactly how to wire modules together.

### 4. Generate Contracts (Project-Type-Adaptive)

Read `product_category` from architecture frontmatter to determine contract format.

#### Web App / API Service: REST Endpoints

Group by resource. Use RESTful design (plural nouns, standard HTTP methods, nested resources).

```markdown
### METHOD /api/[route]
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Request:** `{ field: type, ... }`
- **Response 200:** `{ data: { ... } }`
- **Response 4xx:** `{ error: { code: "...", message: "..." } }`
```

**Notes:**
- Derive route from FR subject (e.g., "Create Order" → POST /api/orders)
- Use error codes from Section 3 taxonomy
- Include path params where appropriate (`/api/orders/:id`)

#### CLI Tool: Command Specifications

```markdown
### command-name
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Args:** `<required-arg> [optional-arg]`
- **Flags:** `--flag description (default: value)`
- **Stdin:** {accepted input format, or "N/A"}
- **Stdout:** {output format description}
- **Stderr:** {error/diagnostic output}
- **Exit Codes:** `0: success, 1: {error type}, 2: usage error`
```

#### Library/SDK / Plugin/Extension: Public API Surface

```markdown
### functionName(params): ReturnType
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Parameters:** `param1: Type - description`, `param2: Type - description`
- **Returns:** `Type - description`
- **Throws:** `ErrorType - when condition`
```

#### Data Pipeline: Data Flow Contracts

```markdown
### {Stage Name}
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Input:** {source system/format/schema}
- **Transform:** {processing logic summary}
- **Output:** {destination system/format/schema}
- **Error:** {retry strategy, dead-letter handling}
- **Schedule:** {trigger: cron/event/dependency}
```

#### Infrastructure/IaC: Resource Definitions

```markdown
### {Resource Group Name}
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Provider:** {cloud provider / platform}
- **Resources:** {list of resources provisioned}
- **Inputs:** {configurable parameters}
- **Outputs:** {exported values for dependent resources}
- **Dependencies:** {other resource groups this requires}
```

#### Microservices: Service Contracts

Use REST Endpoint format (above) for external-facing APIs. For inter-service communication, add:

```markdown
### {Service} → {Service} ({sync|async})
- **FR:** FR-###
- **Protocol:** {REST/gRPC/message queue}
- **Request/Event:** `{ field: type, ... }`
- **Response/Result:** `{ field: type, ... }`
- **Error/DLQ:** {error handling strategy}
- **SLA:** {latency/throughput expectations from NFRs}
```

#### Desktop / Mobile: Screen Contracts

```markdown
### {Screen/View Name}
- **FR:** FR-###
- **Module:** {owning module from Section 4}
- **Route/Navigation:** {how user reaches this screen}
- **State:** {data this screen reads/writes}
- **Actions:** {user interactions → resulting behavior}
- **Error:** {error states and handling}
```

#### Prototype/MVP

Use the simplest applicable format above (typically REST Endpoints or CLI Commands). Minimize contract detail — focus on core hypothesis validation flows only.

**Every contract entry MUST include `Module:` mapping it to Section 4.**

### 5. Complete Error Taxonomy

After contract generation, revisit Section 3 error taxonomy:

1. Review all error responses from contracts
2. Add domain-specific error codes for every error case
3. Cross-reference PRD Section 7.3 (Error Code Catalog) if present
4. Ensure every error code used in contracts exists in the taxonomy

Update Section 3 error taxonomy in `{outputFile}`.

### 6. Update Document

Fill Sections 4 (Module Boundaries) and 5 (Contracts) in `{outputFile}`.

Include the Import Graph in Section 4:
```markdown
### Import Graph
module-a → module-b (uses: functionX, functionY)
module-b → module-c (uses: functionZ)
```

Verify graph is acyclic. If cycles found, restructure modules (extract shared code into a common module).

### 7. Cross-Validation

Before checkpoint, run ALL validation checks. **Fix any failures before presenting.**

| Check | Requirement |
|-------|-------------|
| FR Coverage | Every FR has at least one contract |
| Contract Mapping | Every contract maps to exactly one module |
| Module Graph | Acyclic — no circular dependencies |
| **Path Consistency** | Every module Path in Section 4 appears in the Section 2 directory tree |
| **Test Path Consistency** | Every module Test Path in Section 4 appears in the Section 2 directory tree |
| Export Completeness | Every module has at least one export |
| Dependency Validity | Every "Depends On" entry references an existing module |
| **FR Responsibility** | Every FR assigned to a module logically belongs there (inputs/rules match module scope) |
| **Orchestrator Purity** | If an orchestrator module exists, verify it has no business logic in its responsibility |

**If gaps found:** Fix before presenting checkpoint. Common fixes:
- Missing test files in tree → add to Section 2
- FR in wrong module → reassign and update contracts
- Missing export → add to module table
- Cycle in graph → extract shared code into leaf module

### 8. Checkpoint

Present to user:
- Module boundaries table
- Import graph
- Contract summary (count by type)
- Coverage: FRs without contracts (should be 0)
- Cross-validation results (all checks should pass)

**Menu:**
- **[C] Continue** - Proceed to Step 4: Testing & Build Order
- **[R] Revise** - Adjust modules, interfaces, or contracts
- **[P] Party Mode** - Discuss module decisions with architect/dev agents
- **[D] Deep Dive** - Analyze module boundaries with advanced methods
- **[X] Exit** - Save progress and stop

**On [P] Party Mode:**
Invoke `_party-mode` skill with:
- `topic`: "Module boundaries and contracts for [project name]"
- `content`: Module table + import graph + contract summary
- `focus_agents`: `architect`, `dev`

**On Continue:** Update frontmatter `current_step: 4`, load `{nextStepFile}`
