---
name: 'step-02-foundation'
description: 'Select technology stack, define build commands, project structure, and coding patterns'
nextStepFile: '{skill_base}/steps/step-03-modules.md'
outputFile: '{planning_artifacts}/architecture.md'
---

# Step 2: Technology & Foundation

**Progress:** Step 2 of 5 → Next: Modules & Contracts

**Goal:** Select the complete technology stack, define build commands, project structure, and coding patterns including error propagation convention.

---

## Instructions

### 1. Select Technology Stack

**For each "Open" decision in PRD Section 6:**

1. Read `product_category` from architecture frontmatter
2. Load `{data_files_path}/project-types.csv` and use ONLY the matching category row
3. Use web search: "[technology] latest stable version" for version confirmation
4. Select technology that aligns with PRD constraints (Section 6 Decided items are locked), NFR requirements (Section 4), and ecosystem compatibility
5. Document rationale briefly

**Category sets by project type — use ONLY the one matching your product_category:**

**Web App / Full Stack / API Service:**
| Category | Selection Inputs |
|----------|------------------|
| Framework | Product category + PRD hints |
| Database | Data complexity (Section 5) + scale (Section 4) |
| ORM | Framework ecosystem |
| Auth | Security requirements (Section 4) |
| Styling | Frontend needs (if applicable) |
| Testing | Framework ecosystem |

**CLI Tool / Library/SDK / Plugin/Extension:**
| Category | Selection Inputs |
|----------|------------------|
| Framework/Toolkit | Product category + distribution format |
| Database | Only if persistent storage needed (Section 5) |
| Testing | Framework ecosystem |
| Packaging | Distribution requirements (executable, package registry) |

**Data Pipeline:**
| Category | Selection Inputs |
|----------|------------------|
| Orchestrator | Workflow complexity + scheduling needs |
| Storage | Data volume + query patterns (Section 5) |
| Message Queue | If async processing needed |
| Data Validation | Data quality requirements |
| Testing | Framework ecosystem |

**ML Model/Service:**
| Category | Selection Inputs |
|----------|------------------|
| Serving Framework | Inference latency (Section 4) + model type |
| Training Framework | Model architecture requirements |
| Model Registry | Versioning + deployment requirements |
| Database | Feature store + metadata storage needs |
| Testing | Framework ecosystem |

**Infrastructure/IaC:**
| Category | Selection Inputs |
|----------|------------------|
| IaC Tool | Cloud provider(s) + team familiarity |
| State Backend | Collaboration + state management needs |
| Policy/Compliance | Security requirements (Section 4) |
| Testing | Infrastructure testing approach |

**Microservices:**
| Category | Selection Inputs |
|----------|------------------|
| Service Framework | Per-service, may vary by bounded context |
| Database | Per-service, based on data ownership |
| Service Communication | Sync (REST/gRPC) vs Async (message queue) |
| Service Discovery | Deployment target (K8s, cloud-native) |
| Auth | Inter-service + external auth |
| Testing | Unit + contract + integration approach |

**Desktop / Mobile:**
| Category | Selection Inputs |
|----------|------------------|
| Framework | Target platforms + code sharing strategy |
| Local Storage | Offline data needs |
| Auth | Authentication flow (OAuth, biometric) |
| Testing | Framework ecosystem + E2E |

**Prototype/MVP:**
| Category | Selection Inputs |
|----------|------------------|
| Framework | Speed of development + team familiarity |
| Database | Simplest option that meets needs |
| Testing | Minimal — core hypothesis validation |

**Decision Rule:** If PRD clearly implies one choice, select it. Only ask user if multiple equally valid options exist—then present top 2 with your recommendation.

Fill Section 1 Technology Stack table in `{outputFile}`.

---

### 2. Define Build Commands

Derive Install/Test/Lint/Type Check/Format/Build commands from the selected stack. These directly feed build-from-prd's Build Config table.

| Command | Value |
|---------|-------|
| Install | e.g., `npm install`, `uv sync`, `go mod download` |
| Test | e.g., `npm test`, `uv run pytest tests/ --tb=short`, `go test ./...` |
| Lint | e.g., `npm run lint`, `uv run ruff check src/ --fix`, `golangci-lint run` |
| Type Check | e.g., `npx tsc --noEmit`, `uv run pyright src/`, leave empty for dynamic langs |
| Format | e.g., `npx prettier --write src/`, `uv run ruff format src/`, leave empty if lint handles it |
| Build | e.g., `npm run build`, `uv run python -m build`, `go build ./cmd/app` |

Fill Section 1 Build Commands table in `{outputFile}`.

### 2b. Define Dependency Pinning Strategy

Document pinning rules for reproducible builds:
- **Locked deps (from PRD Section 6 "Decided"):** Exact pin (`==`)
- **Runtime deps:** Compatible range (`>=x.y,<x+1`) or exact pin
- **Dev/build deps:** Minimum version (`>=`)

Fill Section 1 Dependency Pinning Strategy in `{outputFile}`.

---

### 3. Define Project Structure

Generate directory tree following framework conventions.

**Structure must include:**
- Source code organization (framework-specific)
- Test file locations (mirroring source structure)
- Configuration files
- Database/schema files (if applicable)
- Static assets (if applicable)

**Derive from:**
- Framework conventions (e.g., Next.js app router, NestJS modules)
- PRD functional areas (Section 3 capability area headers → corresponding directories)
- Module count from FRs

**Language-specific entry points:**
- **Python CLI:** Include `__main__.py` (trivial: `from package.cli import main; main()`) for `python -m package` and packaging tool entry points
- **Node.js:** Include `bin/` entry point script or `package.json` `bin` field
- **Go:** Include `cmd/app/main.go`

**Add `src_dir` and `test_dir` markers as HTML comments:**
```markdown
<!-- src_dir: src/ -->
<!-- test_dir: tests/ -->
```

These markers are extracted by build-from-prd for automated tooling.

Fill Section 2 in `{outputFile}`.

---

### 4. Define Coding Patterns

#### A. Naming Conventions (project-type-adaptive)

Select the row set matching your product category:

**Web App / API Service / Full Stack / Microservices:**
| Element | Convention | Example |
|---------|------------|---------|
| Component files | Framework standard | `UserProfile.tsx` |
| Utility files | kebab-case | `user-service.ts` |
| Functions | camelCase | `getUserById` |
| DB Tables | snake_case | `user_accounts` |
| API Routes | kebab-case | `/api/user-profile` |
| Constants | UPPER_SNAKE | `MAX_RETRY_COUNT` |
| Types/Interfaces | PascalCase | `UserProfile` |

**CLI Tool / Data Pipeline:**
| Element | Convention | Example |
|---------|------------|---------|
| Source files | snake_case | `weight_alloc.py` |
| Test files | test_ prefix + snake_case | `test_weight_alloc.py` |
| Functions | snake_case | `detect_header_row()` |
| Classes/Models | PascalCase | `InvoiceItem` |
| Constants | UPPER_SNAKE | `MAX_SCAN_ROW` |
| Config keys | snake_case | `invoice_sheet` |
| Error codes | PREFIX_NNN | `ERR_020` |

**Library/SDK / Plugin/Extension:**
| Element | Convention | Example |
|---------|------------|---------|
| Source files | snake_case or kebab-case | `parser.py`, `parser.ts` |
| Test files | test_ prefix or .test suffix | `test_parser.py` |
| Functions | snake_case or camelCase | `parse_document()` |
| Classes | PascalCase | `DocumentParser` |
| Constants | UPPER_SNAKE | `DEFAULT_TIMEOUT` |
| Public API | camelCase or snake_case | `createClient()` |
| Types | PascalCase | `ParserOptions` |

**Desktop / Mobile:**
| Element | Convention | Example |
|---------|------------|---------|
| Screen files | PascalCase | `HomeScreen.tsx` |
| Component files | PascalCase | `UserAvatar.tsx` |
| Functions | camelCase | `navigateToProfile` |
| State keys | camelCase | `isLoggedIn` |
| Constants | UPPER_SNAKE | `SCREEN_TIMEOUT` |
| Routes | kebab-case | `/user-profile` |
| Types | PascalCase | `UserState` |

Adapt based on language conventions. For example, Python always uses snake_case for functions regardless of project type.

#### B. Response Format (project-type-adaptive)

**Web App / API Service:**
```
Success: { data: T, error: null }
Error: { data: null, error: { code: string, message: string } }
```

**CLI Tool:**
```
Exit codes: 0 (success), 1 (runtime error), 2 (usage/config error)
Stdout: structured output (per PRD Section 7 format specs)
Stderr: reserved for unhandled exceptions
```

**Library/SDK:**
```
Returns: typed values per function signature
Errors: typed exceptions/errors with code property
```

**Data Pipeline:**
```
Success: output dataset/table with metadata (row count, schema version)
Failure: dead-letter queue entry with error context
```

Select the matching format. Customize exit codes or response structure based on PRD Section 7 if present.

#### C. Error Code Taxonomy (project-type-adaptive)

**If PRD Section 7 defines an error catalog:** Use it directly. Map errors to processing phases or modules. Do NOT create a generic taxonomy — the PRD's is authoritative.

**If PRD has no error catalog, derive from project type:**

**Web App / API Service:**
| Prefix | Category | HTTP Status |
|--------|----------|-------------|
| AUTH_ | Authentication | 401/403 |
| VAL_ | Validation | 400 |
| RES_ | Resource | 404/409 |
| SYS_ | System | 500 |

**CLI Tool:**
| Range/Prefix | Category | Exit Code |
|-------------|----------|-----------|
| CONFIG_ | Configuration errors | 2 |
| INPUT_ | Input file/data errors | 1 |
| PROC_ | Processing errors | 1 |
| OUTPUT_ | Output generation errors | 1 |

**Library/SDK:**
| Exception Type | Category |
|---------------|----------|
| ConfigError | Invalid configuration |
| ValidationError | Invalid input |
| ProcessingError | Runtime failures |

Always add domain-specific prefixes from PRD Section 3 capability areas.

#### D. Logging Pattern

Define:
- **Format:** e.g., `[{timestamp}] {level} [{module}] {message}`
- **Levels:** ERROR (failures), WARN (degraded), INFO (state changes), DEBUG (dev only)
- **Targets:** Console, file, external service — with level filtering per target
- **What gets logged:** State transitions, external calls, errors. NOT: routine reads, internal calculations.
- **Structured fields:** If applicable, define required fields per log entry.

Derive from PRD Section 7 (if present) and FR Log fields.

#### E. Error Propagation Convention

Define how errors flow between modules. This is critical for orchestrator modules and pipeline architectures.

**Two standard patterns (select and adapt):**

| Pattern | When to Use | Mechanism |
|---------|-------------|-----------|
| **Raise immediate** | Single fatal error that stops the current phase | Raise exception (e.g., `raise ProcessingError(...)`) |
| **Collect-then-report** | Phase where all problems should be reported at once | Return result object with `.errors` list |

**Document for each pattern:**
- Which modules use it (derive from FR error behavior: single-point failure vs multi-field validation)
- How the orchestrator handles it (try/except AND/OR result inspection)
- How errors propagate to the user (error codes, messages, exit codes)

#### F. Side-Effect Ownership

Define which modules own which side effects:

| Side Effect | Owner Module | Non-owners Must |
|-------------|-------------|-----------------|
| File writes | {module} | Call {module}.write() |
| HTTP calls | {module} | Call {module}.request() |
| DB writes | {module} | Go through {module} service |
| Logging | Each module | Use shared logger config |
| Path construction | {orchestrator} | Receive paths, never construct them |

Derive from FR capability areas — modules that handle FILE, API, DATA areas typically own corresponding side effects.

Fill Section 3 in `{outputFile}`.

---

### 5. Checkpoint

Present to user:
- Technology stack table (versions + rationale)
- Build commands
- Project structure (collapsed view)
- Coding patterns summary (naming, response format, error propagation)

**Menu:**
- **[C] Continue** - Proceed to Step 3: Modules & Contracts
- **[R] Revise** - Adjust technology selections, structure, or patterns
- **[P] Party Mode** - Discuss stack decisions with architect/dev agents
- **[D] Deep Dive** - Analyze decisions with advanced elicitation methods
- **[X] Exit** - Save progress and stop

**On [P] Party Mode:**
Invoke `_party-mode` skill with:
- `topic`: "Technology stack decisions for [project name]"
- `content`: Technology stack table + PRD constraints summary
- `focus_agents`: `architect`, `dev`

After party mode completes, return to this checkpoint with insights applied.

**On [D] Deep Dive:**
Invoke `_deep-dive` skill with:
- `content`: Technology stack table + rationale
- `focus_area`: "Technology stack validation"
- `content_type`: "architecture"

Recommended method categories: `technical`, `risk`, `competitive`

After deep dive completes, return to this checkpoint with enhancements applied.

**On Continue:** Update frontmatter `current_step: 3`, load `{nextStepFile}`
