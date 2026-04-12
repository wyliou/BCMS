---
name: 'step-03-edit'
description: 'Apply approved changes to PRD'

# File references
nextStepFile: '{skill_base}/steps-edit-prd/step-04-complete.md'
---

# Step 3: Edit

**Progress: Step 3 of 4** - Next: Complete

## STEP GOAL

Apply all approved changes from step 2 to the PRD, including content updates, format conversions, and structure changes.

## EXECUTION RULES

- **Auto-proceed step** - executes approved plan
- You are a Product Analyst (Editor) — applying approved changes
- Only implement approved changes - no additions
- Follow PRD Guidelines for all edits

## SEQUENCE (Follow Exactly)

### 1. Retrieve Approved Plan

From step 2, retrieve:
- Approved changes (section-by-section)
- Format conversions (FR, NFR, IDs)
- Priority order
- Conversion mode (if legacy)

"**Starting Edits**
Plan: {count} changes across {section count} sections
Executing..."

### 2. Execute Changes by Priority

**For each change (in priority order):**

**a) Load Section**
- Read current PRD section
- Note existing content

**b) Apply Change**
- Additions: Create new content following PRD Guidelines
- Updates: Modify existing content per plan
- Removals: Delete specified content
- Restructure: Reformat to standard structure

**c) Save and Verify**
- Apply change to PRD
- Verify change applied correctly

**d) Report Progress**
"**Updated:** {section_name}"

### 3. FR Format Conversion (If in Plan)

Convert each FR to Input/Rules/Output/Error format:

**Before:**
```
**FR-001**: User can register
- Given: visitor on registration page
- When: submit valid email and password
- Then: account created
```

**After:**
```
**FR-001**: User registers with email and password
- **Input:** email (valid format), password (8+ chars, 1 uppercase, 1 number)
- **Rules:** Email must be unique; hash password before storage
- **Output:** Account created, confirmation email sent within 30 seconds
- **Error:** Duplicate email → "Email already registered"
```

**Conversion steps:**
1. Keep existing ID format (do not change IDs during format conversion)
2. Extract inputs from Given/When → Input field with constraints
3. Extract business logic → Rules field
4. Extract success case from Then → Output field
5. Identify error cases → Error field
6. Add Depends field if references other FRs

"**Converted:** {count} FRs to Input/Rules/Output/Error format"

### 4. NFR Format Conversion (If in Plan)

Convert each NFR to single-line format:

**Before:**
```
**NFR-001**: Performance
- The system should respond quickly
- Page load under 3 seconds
```

**After:**
```
**NFR-PERF-001**: Page load time under 3 seconds for 95th percentile under normal load
```

**Conversion steps:**
1. Use NFR-[CAT]-### format (PERF, SEC, SCALE, REL, ACC, USE, MAINT, COMPAT)
2. Identify metric (response time, uptime, etc.)
3. Extract or add specific target
4. Add condition (under normal load, during peak, etc.)
5. Combine into single line

"**Converted:** {count} NFRs to single-line format"

### 5. Restructure (If Conversion Mode)

**If "Restructure" or "Both":**

Reorganize PRD to structured format (sections based on project type):

```markdown
## 1. Overview
### Vision
### Classification
### Actors
### Success Metrics
### MVP Scope

## 2. Journeys/Workflows

## 3. Functional Requirements

## 4. Non-Functional Requirements

## 5. Data Entities

## 6. Technology Constraints
### Decided (non-negotiable)
### Open (agent can decide)

## 7. Implementation Reference (if applicable)
```

**Migration:**
- Move Executive Summary content → Overview/Vision
- Move Success Criteria → Success Metrics (table with primary designation)
- `### Users` → `### Actors`
- `### Key Success Metric` → `### Success Metrics`
- `## 2. User Journeys` → `## 2. Journeys/Workflows`
- Move Product Scope → MVP Scope
- Create Data Entities table from FR analysis

"**Restructured to standard format.**"

### 6. Generate Missing Sections (If in Plan)

**If Data Entities missing:**
Analyze FRs to identify entities:
- Extract nouns from FR Inputs and Outputs
- Create table with Entity, Key Attributes, Related FRs

**If Technology Constraints missing:**
Create section with:
- Decided: (from PRD context or "No constraints specified")
- Open: (list areas for agent decision)

### 7. Update PRD Frontmatter

```yaml
---
lastEdited: '{current_date}'
editHistory:
  - date: '{current_date}'
    changes: '{summary}'
---
```

### 8. Final Verification

**Load complete updated PRD and verify:**
- All approved changes applied
- Section structure is sound for project type (if restructured)
- FR format is Input/Rules/Output/Error
- NFR format is single-line (if present)
- Data Entities table present (if applicable)
- No unintended modifications

**If issues found:** Fix immediately

### 9. Proceed to Completion

"**Edits Complete**
- Sections updated: {count}
- FRs converted: {count}
- NFRs converted: {count}
- IDs updated: {count}

Finalizing..."

→ Load and execute `{nextStepFile}`

---

## SUCCESS CRITERIA

- All approved changes from step 2 applied
- Changes executed in priority order
- FR format converted to Input/Rules/Output/Error (if in plan)
- NFR format converted to single-line (if in plan)
- IDs standardized if inconsistent (if in plan)
- Restructuring completed (if conversion mode)
- Missing sections generated
- Frontmatter updated with edit history
- Final verification confirms changes
- Auto-proceeds to completion step
