---
name: 'step-01-init'
description: 'Initialize architecture workflow - find PRD, detect continuation, extract constraints, detect brownfield, strip N/A sections'
nextStepFile: '{skill_base}/steps/step-02-foundation.md'
outputFile: '{planning_artifacts}/architecture.md'
templateFile: '{skill_base}/architecture-template.md'
---

# Step 1: Init & Discovery

**Progress:** Step 1 of 5 → Next: Technology & Foundation

**Goal:** Locate PRD, detect continuation state, extract constraints from all PRD sections, detect brownfield context, initialize the architecture document structure, and strip irrelevant sections based on project type.

---

## Instructions

### 1. Check for Existing Architecture (Inline Continuation)

Search for existing architecture: `{planning_artifacts}/architecture.md`, `{output_folder}/architecture.md`

**If found with `status: in-progress`:**

1. Read frontmatter `current_step` value
2. Read `prd_source` from frontmatter, verify PRD still exists at that path
   - **If PRD not found:** Ask user for new path
3. Present resume summary:

```
Resuming architecture workflow:
- Document: {path}
- PRD: {prd_source}
- Progress: Step {current_step} of 5
- Product Category: {product_category}
- Completed: {list filled sections}

Continue from Step {current_step}?
```

**Menu:**
- **[C] Continue** - Resume from detected step
- **[R] Restart** - Begin fresh (will overwrite)
- **[X] Exit** - Stop without changes

**Resume mapping:**

| Step Value | Resume Action |
|------------|---------------|
| 1 | Restart step 1 |
| 2 | Load `step-02-foundation.md` |
| 3 | Load `step-03-modules.md` |
| 4 | Load `step-04-testing.md` |
| 5 | Load `step-05-finalize.md` |

**If not found or `status: complete`:** Proceed to fresh setup.

---

### 2. Discover PRD

Search for PRD in: `{planning_artifacts}/**`, `{output_folder}/**`, `docs/**`
Pattern: `*prd*.md` or `prd.md`

**If not found:** "Architecture requires a PRD. Please provide the path or run `/prd-create` first."

**If found:** Read completely, confirm with user:
> "Found PRD: [path]. Creating architecture for [project name]. Continue?"

---

### 3. Extract Constraints from All PRD Sections

Read and extract from ALL PRD sections (1-7). Store as working set — do NOT fill the architecture document yet.

| PRD Section | Extract |
|-------------|---------|
| Section 1 (Overview) | Project name, product category, project type (Greenfield/Brownfield), user types |
| Section 2 (Journeys) | Flow overview (read-only, for understanding) |
| Section 3 (FRs) | FR count, capability areas (from section headers), FR dependencies |
| Section 4 (NFRs) | Performance, security, scale requirements |
| Section 5 (Data Entities) | Entity count, entity names, key attributes |
| Section 6 (Tech Constraints) | Decided (locked) vs Open (need selection) |
| Section 7 (Implementation Reference) | Config schemas, output formats, error catalogs, algorithms (if present) |

---

### 4. Brownfield Detection

**If PRD Section 1 indicates Brownfield:**

1. Search for Project Charter: `docs/project-charter*.md`
2. If found, read Section 7 (Brownfield Context) for:
   - Existing systems and their disposition
   - Legacy data migration requirements
   - Technical constraints from legacy systems

3. Search for related documents:
   - Integration spec: `docs/integration-spec*.md`
   - Data migration plan: `docs/data-migration*.md`
   - Security architecture: `docs/security-architecture*.md`

4. Inform user of brownfield context:
> "This is a **brownfield project** integrating with existing systems:
> - {list existing systems and dispositions}
> - {note any legacy constraints}
>
> I'll include a Legacy Integration section in the architecture."

---

### 5. Initialize Architecture Document

1. Copy `{templateFile}` to `{outputFile}`
2. Fill **frontmatter ONLY** (no content sections yet):
   ```yaml
   ---
   status: in-progress
   current_step: 1
   prd_source: [path]
   prd_checksum: [first 8 chars of sha256 hash of PRD content]
   product_category: [from PRD Section 1]
   completed_at:
   ---
   ```
3. Fill header:
   - `{{project_name}}` from PRD Section 1
   - `{{date}}` = today
   - `{{prd_path}}` = path to PRD

---

### 6. Strip Irrelevant Sections

Based on `product_category` and project type, remove sections that don't apply. This keeps the document lean and prevents "N/A" boilerplate.

**Section stripping rules:**

| Condition | Action |
|-----------|--------|
| Greenfield project | Remove Section 10 (Legacy Integration) entirely |
| CLI Tool, Library, Plugin without persistent storage | Remove Section 6 (Database Schema) entirely |
| No external services or env vars needed | Replace Section 7 with "Configuration Files" table: `Config File / Path / Purpose` |
| Project has persistent storage | Keep Section 6, remove SQL example comments (fill in Step 5) |
| Brownfield project | Keep Section 10, remove placeholder values (fill in Step 5) |

**Always keep:** Sections 1-5 (Stack, Structure, Patterns, Modules, Contracts), Section 8 (Testing), Section 9 (Implementation Order).

---

### 7. Checkpoint

Present to user:
- PRD summary: project name, product category, FR count, entity count
- Technology constraints extracted (Decided vs Open)
- Brownfield context (if applicable)
- Sections stripped (list which sections were removed and why)

> "PRD analyzed. Ready to select technology stack and define project foundation."

**No menu** — proceed directly to step 2. This step is purely discovery/setup with no decisions to discuss.

**On proceed:** Update frontmatter `current_step: 2`, load `{nextStepFile}`
