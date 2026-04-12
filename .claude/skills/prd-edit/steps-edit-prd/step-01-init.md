---
name: 'step-01-init'
description: 'Load PRD, detect format, discover edit requirements'

# File references
nextStepFile: '{skill_base}/steps-edit-prd/step-02-plan.md'
prdPurpose: '{skills_root}/_prd-data/prd-purpose.md'
validationChecks: '{skills_root}/_prd-data/validation-checks.md'
---

# Step 1: Init

**Progress: Step 1 of 4** - Next: Plan

## STEP GOAL

Load the PRD, detect format (Structured/Legacy), discover edit requirements, and auto-detect validation reports.

## EXECUTION RULES

- **Interactive step** - requires user input
- Focus on discovery - no edits yet
- You are a Product Analyst (Editor) — an improvement specialist

## SEQUENCE (Follow Exactly)

### 1. Load Standards

Load and read:
- `{prdPurpose}` - PRD Guidelines philosophy
- `{validationChecks}` - Validation criteria (for format detection)

### 2. Load PRD

**If path provided:** Verify exists, load complete file with frontmatter
**If no path:** Prompt: "Which PRD would you like to edit? Provide the file path."

### 3. Auto-Detect Validation Report

Check PRD folder for `validation-report*.md`:

**If found:**
"**Found:** validation-report.md
[U] Use report | [S] Skip"

- **U:** Load report, note "Report loaded - will use findings to prioritize edits"
- **S:** Continue without report

**If not found:** Continue to step 4

### 4. Manual Validation Report

"**Validation report path?** (or 'none'):"

If provided: Load report

### 5. Get Edit Goals

"**What changes do you want to make?**
(e.g., 'Fix density issues', 'Add FR structure', 'Add Data Entities', 'Address validation findings'):"

Wait for response. Store edit goals.

### 6. Detect PRD Format

Extract all `##` headers and analyze:

**Section Check:**
| Section | Present? | Required For |
|---------|----------|--------------|
| 1. Overview | {Yes/No/Partial} | All projects |
| 2. Journeys/Workflows | {Yes/No/Partial} | UI-based, pipelines, infrastructure |
| 3. Functional Requirements | {Yes/No/Partial} | All projects |
| 4. Non-Functional Requirements | {Yes/No/Partial} | Production |
| 5. Data Entities | {Yes/No/Partial} | Persistent storage |
| 6. Technology Constraints | {Yes/No/Partial} | When constraints exist |
| 7. Implementation Reference | {Yes/No/Partial} | Complex systems with defined specs |

**FR Format Check:**
- Structured: Has Input/Rules/Output/Error fields
- Basic: Has Given/When/Then or simple descriptions
- Unstructured: Plain text descriptions

**FR ID Check:**
- Accept any consistent format (FR-001, FR-AUTH-001, descriptive)
- Flag only if inconsistent or missing

**Classify:**
| Classification | Criteria |
|----------------|----------|
| Structured | Required sections + FR Input/Rules/Output/Error format |
| Partial | Some structure, needs format conversion |
| Legacy | Missing required sections or no FR structure |

### 7. Route Based on Format

**IF Structured/Partial OR has validation report:**

"**Ready**
- Format: {classification}
- Sections: {count} present
- FR Format: {Structured / Basic (needs conversion)}
- Validation Report: {Loaded / None}
- Goals: {summary}

Proceeding to planning..."

→ Load and execute `{nextStepFile}`

**IF Legacy AND no validation report:**

→ Continue to Legacy Assessment (step 8)

### 8. Legacy Assessment (Legacy PRDs Only)

Analyze section gaps based on project type:

| Section | Status | Gap | Effort |
|---------|--------|-----|--------|
| 1. Overview | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 2. User Journeys | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 3. Functional Requirements | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 4. Non-Functional Requirements | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 5. Data Entities | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 6. Technology Constraints | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |
| 7. Implementation Reference | {Present/Missing/Partial} | {what's missing} | {Min/Mod/Sig} |

Calculate: Sections present: {count}

### 9. Present Legacy Options

"**Legacy PRD Assessment**

**Structure:** {count} sections present
**Missing:** {list}
**FR Format:** {structured/basic/none}
**Overall Effort:** {Quick/Moderate/Substantial}

**Options:**"

### 10. Menu (Legacy Only)

**[R] Restructure** - Full structure conversion + edits
**[T] Targeted** - Edits within current structure only
**[B] Both** - Convert structure AND apply edits
**[X] Exit**

#### Menu Logic:
- **R/T/B:** Store conversion mode, display "Proceeding to planning..." → Load `{nextStepFile}`
- **X:** Exit workflow

---

## SUCCESS CRITERIA

- PRD loaded and format detected
- FR format (Input/Rules/Output/Error vs basic) assessed
- Validation report auto-detected or manually loaded (if available)
- Edit goals captured
- Legacy PRDs assessed with section gap analysis
- User chooses approach for legacy PRDs
- Proceeds to planning with clear context
