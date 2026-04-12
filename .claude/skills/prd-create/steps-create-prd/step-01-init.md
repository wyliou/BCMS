---
name: 'step-01-init'
description: 'Initialize PRD workflow - detect state, discover inputs, determine output path, setup document, handle continuation'

# File references
nextStepFile: '{skill_base}/steps-create-prd/step-02-discovery.md'
defaultOutputFile: '{project_root}/docs/PRD.md'
prdTemplate: '{skills_root}/_prd-data/prd-template.md'
prdPurpose: '{skills_root}/_prd-data/prd-purpose.md'

# Resume step mapping
step02File: '{skill_base}/steps-create-prd/step-02-discovery.md'
step03File: '{skill_base}/steps-create-prd/step-03-journeys.md'
step04File: '{skill_base}/steps-create-prd/step-04-requirements.md'
step05File: '{skill_base}/steps-create-prd/step-05-specifications.md'
step06File: '{skill_base}/steps-create-prd/step-06-complete.md'
---

# Step 1: Init

**Progress: Step 1 of 6** - Next: Discovery

## STEP GOAL

Detect workflow state, determine output path, discover input documents, setup PRD document, and handle continuation of interrupted workflows.

## EXECUTION RULES

- Focus on setup - no content creation yet
- Continuation is handled inline (no separate step file)

## SEQUENCE (Follow Exactly)

### 1. Determine Output Path

#### A. Search for Existing PRDs

Search for existing PRD files: `docs/*prd*.md`, `docs/*PRD*.md`

**If existing PRDs found:**

"Found existing PRDs:
1. `{path_1}` — {first line or title}
2. `{path_2}` — {first line or title}
...

Which would you like to work with?
- [1-N] Select an existing PRD
- [New] Create a new PRD"

Wait for user choice. If an existing PRD is selected, set `outputPath` to that file and proceed to step 2.

#### B. Set Output Path (New PRD only)

If user chose [New] or no existing PRDs were found:

"Where should the PRD be saved? Default: `{defaultOutputFile}`"

If user provides a path, use it. Otherwise use `{defaultOutputFile}`. Store as `outputPath`.

### 2. Check Workflow State

Check if the file at `outputPath` exists and read it completely if found.

**Decision Tree:**

| Condition | Action |
|-----------|--------|
| File exists + `stepsCompleted` includes `step-06-complete` | → Already Complete (Section 3) |
| File exists + `stepsCompleted` present but missing `step-06-complete` | → Continuation Branch (Section 4) |
| File exists + NO `stepsCompleted` (unmanaged) | → Safeguard Protocol (Section 5) |
| File not exists | → Fresh Setup (Section 6) |

### 3. Already Complete

"This PRD's workflow is already complete.

**[V] Validate** - Run /prd-validate
**[A] Architecture** - Run /create-architecture
**[E] Edit** - Run /prd-edit
**[N] New** - Create a new PRD at a different path
**[X] Exit**"

Wait for user choice.

### 4. Continuation Branch

If existing file has `stepsCompleted` array but workflow is incomplete:

#### A. Validate Frontmatter

| Field | Requirement |
|-------|-------------|
| `stepsCompleted` | Array, not empty (at least `step-01-init`) |

**If validation fails:** Offer to backup the file and start fresh.

#### B. Restore Context

1. Re-discover input documents using the same search patterns as Fresh Setup (section 6A).
2. **Report to user:** "Found these input documents from the previous session: {list}. Any changes — new documents to add or old ones to exclude?"
3. Wait for user confirmation before loading.
4. Load `{prdPurpose}` for quality standards context (normally loaded in step-02, but skipped on continuation).

#### C. Determine Resume Point

**6-step workflow mapping:**

| Last Completed | Resume At | File |
|----------------|-----------|------|
| `step-01-init` | Step 2: Discovery | `{step02File}` |
| `step-02-discovery` | Step 3: Journeys & Mapping | `{step03File}` |
| `step-03-journeys` | Step 4: Requirements | `{step04File}` |
| `step-04-requirements` | Step 5: Specifications | `{step05File}` |
| `step-05-specifications` | Step 6: Complete | `{step06File}` |

#### D. Report & Menu

Report progress (steps completed, next step, documents loaded) and present options:

**[C] Continue** - Load and execute the next step file based on resume point
**[R] Restart** - Reset `stepsCompleted: ['step-01-init']`, load `{step02File}`
**[X] Exit** - Stop workflow

### 5. Safeguard Protocol (Unmanaged File)

If existing file has no `stepsCompleted` frontmatter:

"Found existing file at `{outputPath}` not created by this workflow. Overwrite it, or choose a different path?"

Wait for user choice before proceeding.

### 6. Fresh Setup

#### A. Discover Input Documents

Search for product knowledge documents in common locations:

**Search paths (check each, skip if not found):**
- `docs/`
- `product_knowledge/` (if exists)
- Project root `.md` files

| Type | Pattern |
|------|---------|
| Product Brief | `*brief*.md` or `*brief*/index.md` |
| Research | `*research*.md` or `*research*/index.md` |
| Project Docs | Other `.md` files in search locations |

**If no documents found or user confirms none are relevant:**
"Proceeding without input documents. We'll gather all context through our conversation."
Continue to section 6C.

**Project Type:** Ask the user: "Is this a Greenfield (new) or Brownfield (existing systems) project?"

If the project repo contains source code, suggest Brownfield but let the user decide.

**Report discoveries to user and ask for confirmation before loading.**

#### B. Load Files

Load all confirmed input documents and `{prdTemplate}`. Skip any files that don't exist.

#### C. Create Document

- Copy `{prdTemplate}` to `{outputPath}`
- Initialize frontmatter with:
  - `stepsCompleted: []`
  - `outputPath: '{outputPath}'`

Subsequent steps read `outputPath` from frontmatter rather than using a hardcoded value.

#### D. Report & Menu

**Report:**
- Document created at `{outputPath}`
- Input documents loaded (with counts by type)
- Project type (Brownfield/Greenfield)

**Menu:**

**[C] Continue** - Proceed to Discovery (Step 2)
**[X] Exit** - Stop workflow

**On [C]:** Update frontmatter (`stepsCompleted: ['step-01-init']`), then load and execute `{nextStepFile}`.
