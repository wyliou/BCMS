---
name: 'step-04-complete'
description: 'Present edit summary, offer validation or additional edits'

# File references
validateSkill: '{skills_root}/prd-validate/skill.md'
planStep: '{skill_base}/steps-edit-prd/step-02-plan.md'
createArchSkill: '{skills_root}/create-architecture/skill.md'
---

# Step 4: Complete

**Progress: Step 4 of 4** - Final Step

## STEP GOAL

Present summary of completed edits and offer next steps including validation integration.

## EXECUTION RULES

- **Interactive step** - requires user selection
- You are a Product Analyst (Editor) — summarizing changes and preparing handoff
- This is the final step
- Offers seamless validation handoff

## SEQUENCE (Follow Exactly)

### 1. Compile Edit Summary

From step 3, gather:

**Changes Made:**
- Sections added: {list}
- Sections updated: {list}
- Content removed: {list}
- Structure changes: {description}

**Format Conversions:**
- FRs converted to Input/Rules/Output/Error: {count}
- NFRs converted to single-line: {count}
- IDs standardized: {count}

**PRD Status:**
- Format: {Structured / Partial}
- FR Format: {Input/Rules/Output/Error}
- NFR Format: {Single-line}
- Location: {prd_path}

### 2. Present Completion Summary

"**Edit Complete**

**PRD:** {prd_path}
**Changes:** {count} sections modified
**Format:** {Structured / Partial}

**Summary:**
{Brief description of major changes}

**Format Status:**
- FRs: {count} in Input/Rules/Output/Error format
- NFRs: {count} in single-line format
- Data Entities: {Present/Added/Missing}

**What's next?**"

### 3. Menu

**[V] Validate** - Run /prd-validate
**[A] Architecture** - Proceed to /create-architecture
**[E] Edit More** - Continue editing
**[S] Summary** - Show detailed change report
**[X] Exit** - Finish
*Always available: **[P] Party Mode** | **[D] Deep Dive***

#### Menu Logic:

**V (Validate):**
"**Starting validation...**"
→ Suggest running `/prd-validate`

**A (Architecture):**
"**Architecture Readiness Check:**"
- Required sections for project type: {Yes/No}
- FR Input/Rules/Output/Error: {Yes/No}
- Data Entities (if applicable): {Yes/No}
- Technology Constraints: {Yes/No}

If all Yes: "PRD is ready for Architecture. Run /create-architecture?"
If any No: "Address these gaps first: {list}"

**E (Edit More):**
"**Additional changes?**"
Capture new edit goals
→ Load and execute `{planStep}`

**S (Summary):**
Display detailed report:
```
**Edit Report**

**PRD:** {path}
**Date:** {date}

**Structure:**
| Section | Status |
|---------|--------|
| 1. Overview | {Present/Updated/Added} |
| 2. Journeys/Workflows | {Present/Updated/Added/N/A} |
| 3. Functional Requirements | {Present/Updated/Added} |
| 4. Non-Functional Requirements | {Present/Updated/Added/N/A} |
| 5. Data Entities | {Present/Updated/Added/N/A} |
| 6. Technology Constraints | {Present/Updated/Added/N/A} |
| 7. Implementation Reference | {Present/Updated/Added/N/A} |

**Format Conversions:**
- FRs: {count} converted to Input/Rules/Output/Error
- NFRs: {count} converted to single-line
- IDs: {count} standardized

**Key Improvements:**
{List major improvements}

**Architecture Readiness:** {Ready/Needs Work}
```
Then return to menu

**X (Exit):**
"**Complete**
PRD: {path}
Format: {Structured / Partial}
Status: Edited

**Next Steps:**
- Run /prd-validate to verify improvements
- Run /create-architecture when ready for implementation"

Exit workflow

---

## SUCCESS CRITERIA

- Complete edit summary compiled
- All changes clearly documented
- Format conversions reported
- Validation option available and working
- Architecture readiness assessed
- User can validate, proceed to architecture, edit more, or exit
- Clean handoff to next workflow
