---
name: 'step-01b-continue'
description: 'Handle continuation of an interrupted UX workflow'

# File references
step02File: '{skill_base}/steps/step-02-discovery.md'
step03File: '{skill_base}/steps/step-03-design-system.md'
step04File: '{skill_base}/steps/step-04-complete.md'
outputFile: '{planning_artifacts}/ux-design-specification.md'
---

# Step 1b: UX Workflow Continuation

## STEP GOAL

Handle continuation of an interrupted UX workflow by detecting progress and resuming from the correct step.

## EXECUTION RULES

- **Auto-triggered** when existing workflow detected
- Focus on state detection and seamless continuation
- Preserve all existing work in the document

## SEQUENCE (Follow Exactly)

### 1. Analyze Existing Document

Read the existing document at `{outputFile}` and extract:

- `stepsCompleted` array from frontmatter
- `inputDocuments` array from frontmatter
- Existing content sections

### 2. Reload Input Documents

Load each file listed in `inputDocuments` to restore context.
Do NOT discover new documents - only reload existing ones.

### 3. Determine Next Step

**Step Routing Logic:**

| stepsCompleted | Next Step | Action |
|----------------|-----------|--------|
| `['step-01-init']` | step-02-discovery | Discovery |
| `['step-01-init', 'step-02-discovery']` | step-03-design-system | Design System |
| `['step-01-init', 'step-02-discovery', 'step-03-design-system']` | step-04-complete | Finalization |
| All 4 steps | Complete | Workflow finished |

### 4. Report Continuation Status

**Continuation Report:**
"Welcome back! Resuming UX design for {{project_name}}.

**Progress:**
- Steps completed: [list by name]
- Context files: {inputDocuments.length} loaded
- Document: `{outputFile}`

**Existing Sections:**
[Brief summary of what's in the document]

**Next Step:** [Name]

Ready to continue?"

### 5. Route to Correct Step

Based on `stepsCompleted`:

- If next is discovery: load and execute `{step02File}`
- If next is design-system: load and execute `{step03File}`
- If next is complete: load and execute `{step04File}`
- If already complete: Inform user and offer to review or start fresh

---

## SUCCESS CRITERIA

- Correctly detected workflow state
- Input documents reloaded
- Accurate summary of existing progress
- Proper routing to correct next step
- Preserved all existing content
