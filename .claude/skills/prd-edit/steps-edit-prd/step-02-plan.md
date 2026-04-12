---
name: 'step-02-plan'
description: 'Deep review PRD, analyze validation findings, build change plan'

# File references
nextStepFile: '{skill_base}/steps-edit-prd/step-03-edit.md'
validationChecks: '{skills_root}/_prd-data/validation-checks.md'
---

# Step 2: Plan

**Progress: Step 2 of 4** - Next: Edit

## STEP GOAL

Deep review the PRD, analyze validation findings (if available), and build a detailed change plan for user approval.

## EXECUTION RULES

- **Interactive step** - requires user approval of plan
- You are a Product Analyst (Editor) — analyzing PRD and building change plan
- Focus on analysis and planning - no edits yet
- Plan must be approved before proceeding

## SEQUENCE (Follow Exactly)

### 1. Gather Context

From step 1, retrieve:
- Edit goals
- PRD format (Structured/Partial/Legacy)
- FR format (Input/Rules/Output/Error or basic)
- Conversion mode (if legacy): Restructure/Targeted/Both
- Validation report (if loaded)

### 2. Analyze Validation Report (If Available)

**Extract findings by severity:**
- Critical (must fix)
- Warning (should fix)
- Informational (nice to fix)

**Map to sections:**
| Section | Issues | Priority |
|---------|--------|----------|
| {section} | {issue list} | Critical/High/Med/Low |

### 3. Deep PRD Review (If No Validation Report)

Reference `{validationChecks}` and analyze based on project type:

| Check | Finding | Priority |
|-------|---------|----------|
| Section Structure | {missing/incomplete sections for project type} | {priority} |
| FR IDs | {consistency check} | {priority} |
| FR Structure | {Input/Rules/Output/Error compliance} | {priority} |
| NFR Format | {single-line compliance, if NFRs present} | {priority} |
| Data Entities | {table with Related FRs, if applicable} | {priority} |
| Information Density | {anti-patterns found} | {priority} |
| Measurability | {unmeasurable items} | {priority} |

### 4. Build Section-by-Section Change Plan

**For each affected section:**

```
**{Section Name}**
- Current: {brief description or "Missing"}
- Issues: {from analysis}
- Changes: {specific changes needed}
- Priority: {Critical/High/Med/Low}
```

**Include format conversions if needed:**

```
**FR Format Conversion**
- Current: {Given/When/Then or description only}
- Target: Input/Rules/Output/Error format
- FRs to convert: {count}
- Priority: High

**NFR Format Conversion**
- Current: {multi-line or missing metrics}
- Target: Single-line with metric/target/condition
- NFRs to convert: {count}
- Priority: High

**ID Consistency Fix** (only if IDs are inconsistent)
- FR IDs: {count} to standardize (pick dominant format)
- NFR IDs: {count} to standardize
```

### 5. Summarize Change Plan

**Changes by Type:**
- Sections to add: {count}
- Sections to update: {count}
- FR format conversions: {count}
- NFR format conversions: {count}
- ID format updates: {count}
- Content removals: {count}
- Restructuring: {Yes/No}

**Priority Distribution:**
- Critical: {count}
- High: {count}
- Medium: {count}
- Low: {count}

### 6. Present Plan for Approval

"**Change Plan**

**Based on:** {validation report / PRD Guidelines review}

**Changes:**

{Section-by-section breakdown}

**Format Conversions:**
- FR format: {count} to convert to Input/Rules/Output/Error
- NFR format: {count} to convert to single-line
- ID fixes: {count} to standardize (if inconsistent)

**Summary:**
- Total changes: {count} across {section count} sections
- Priority: {critical} critical, {high} high

**Approve this plan?**"

### 7. Menu

**[C] Continue** - Approve and proceed to edit
**[R] Revise** - Modify the plan
**[D] Deep Dive** - Apply advanced elicitation on complex issues
**[P] Party Mode** - Multi-agent discussion of change plan
**[X] Exit** - Save progress and stop

#### Menu Logic:

**C (Continue):**
"**Approved.** Proceeding to edit..."
→ Load and execute `{nextStepFile}`

**R (Revise):**
- Discuss adjustments
- Rebuild plan
- Re-present for approval
- Return to menu

**D (Deep Dive):**
Invoke `/_deep-dive` skill to explore complex issues, unclear requirements, or areas needing deeper analysis. After deep dive, update plan with insights and return to menu.

**P (Party Mode):**
Invoke `/_party-mode` skill to discuss the change plan from multiple agent perspectives (PM, Architect, Developer, QA). Get diverse viewpoints on proposed changes and their implications. After discussion, refine plan if needed and return to menu.

---

## SUCCESS CRITERIA

- Validation findings fully analyzed (if available)
- Deep PRD review completed (if no validation)
- FR and NFR format compliance checked
- Section-by-section change plan built
- Format conversions identified
- Changes prioritized by severity
- User presented clear plan
- User approves plan before proceeding
