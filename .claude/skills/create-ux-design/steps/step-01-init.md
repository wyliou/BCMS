---
name: 'step-01-init'
description: 'Initialize UX workflow - detect state, discover inputs, setup document'

# File references
nextStepFile: '{skill_base}/steps/step-02-discovery.md'
continueStepFile: '{skill_base}/steps/step-01b-continue.md'
outputFile: '{planning_artifacts}/ux-design-specification.md'
uxTemplate: '{skill_base}/ux-design-template.md'
---

# Step 1: Init

**Progress: Step 1 of 4** - Next: Discovery

## STEP GOAL

Detect workflow state, discover input documents (PRD, brief), and setup UX specification document.

## EXECUTION RULES

- **Interactive step** - requires user confirmation
- You are a UX Facilitator - gather context, don't design yet
- Focus on understanding the product before designing

## SEQUENCE (Follow Exactly)

### 1. Check Workflow State

Search for `{outputFile}` (or `*ux-design-specification*.md` in planning artifacts).

**Decision Tree:**

| Condition | Action |
|-----------|--------|
| File exists + has `stepsCompleted` array | → Load `{continueStepFile}` (auto-proceed) |
| File exists + NO `stepsCompleted` | → Safeguard Protocol |
| File not exists | → Fresh Setup |

### 2. Safeguard Protocol (Unmanaged File)

If existing file has no `stepsCompleted` frontmatter:

**Inform user:** "Found existing UX spec at `{outputFile}` not created by this workflow."

**Options:**
- **[M] Migrate** - Add workflow metadata to existing file
- **[B] Backup** - Rename to `ux-design-spec_backup.md`, create fresh
- **[A] Abort** - Stop and let user handle manually

Wait for user choice before proceeding.

### 3. Fresh Setup

#### A. Discover Input Documents

Search locations: `{planning_artifacts}/**`, `{product_knowledge}/**`, `docs/**`

| Type | Pattern |
|------|---------|
| PRD | `*prd*.md` or `*prd*/index.md` |
| Product Brief | `*brief*.md` or `*brief*/index.md` |
| Research | `*research*.md` |
| Project Context | `**/project-context.md` |

**Report discoveries:**
"I found these documents for {{project_name}}:

**Discovered:**
- [List each file found]

Should I load these? Anything else to add?"

#### B. Load Confirmed Documents

- Load ALL confirmed files completely (no offset/limit)
- For sharded folders, load index.md first, then related files
- Track in frontmatter `inputDocuments` array

#### C. Create Output Document

- Copy `{uxTemplate}` to `{outputFile}`
- Initialize frontmatter: `stepsCompleted: []`, `inputDocuments: [...]`

### 4. Report & Menu

**Report:**
"UX workspace ready for {{project_name}}.

**Documents Loaded:**
- PRD: {count or 'None'}
- Brief: {count or 'None'}
- Research: {count or 'None'}
- Other: {count or 'None'}

**Output:** `{outputFile}`"

**Menu:**

**[C] Continue** - Proceed to Discovery (Step 2)
**[X] Exit** - Stop workflow

**On [C]:** Update frontmatter (`stepsCompleted: ['step-01-init']`), then load and execute `{nextStepFile}`.

---

## SUCCESS CRITERIA

- Workflow state detected correctly
- Input documents discovered and loaded
- UX document created with proper frontmatter
- User confirmed setup before proceeding
