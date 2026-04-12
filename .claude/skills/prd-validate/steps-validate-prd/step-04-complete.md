---
name: 'step-04-complete'
description: 'Finalize validation report, summarize findings, present results'

# File references
prdEditSkill: '{skills_root}/prd-edit/skill.md'
createArchSkill: '{skills_root}/create-architecture/skill.md'
---

# Step 4: Complete

**Progress: Step 4 of 4** - Final Step

## STEP GOAL

Finalize the validation report, summarize all findings, and present actionable results to the user.

## EXECUTION RULES

- **Interactive step** - requires user interaction
- You are a Product Analyst (Validator) — presenting findings and next steps
- This is the final step - no auto-proceed
- Present clear summary with actionable next steps

## SEQUENCE (Follow Exactly)

### 1. Finalize Report Frontmatter

Update validation report frontmatter:

```yaml
---
validationTarget: '{prd_path}'
validationDate: '{date}'
inputDocuments: [...]
stepsCompleted: ['step-01-init', 'step-02-validate', 'step-03-assess', 'step-04-complete']
status: COMPLETE
overallRating: '{1-5}'
overallStatus: '{Pass/Warning/Critical}'
architectureReadiness: '{percentage}'
---
```

### 2. Determine Overall Status

Based on all findings:

| Status | Criteria |
|--------|----------|
| **Pass** | Rating 4-5, no critical issues |
| **Warning** | Rating 3-4, some issues but usable |
| **Critical** | Rating 1-2, major issues need fixing |

### 3. Generate Executive Summary

Append to report:

```markdown
## Executive Summary

**Overall Status:** {Pass/Warning/Critical}
**Quality Rating:** {rating}/5 - {label}
**Architecture Readiness:** {percentage}%

### Quick Results
| Check | Result |
|-------|--------|
| Section Structure | {count} sections (project-type-appropriate) |
| FR Format | {Pass/Warning/Critical} |
| NFR Format | {Pass/Warning/Critical} |
| Information Density | {Pass/Warning/Critical} |
| Data Entities | {Pass/Warning/Critical} |

### Critical Issues ({count})
{List critical issues or "None"}

### Warnings ({count})
{List warnings or "None"}

### Strengths
{List top 3 strengths}

### Recommendation
{Based on status:
- Pass: "PRD is ready for Architecture. Run /create-architecture."
- Warning: "PRD usable but has issues. Review warnings, then run /create-architecture or /prd-edit."
- Critical: "PRD needs work. Run /prd-edit to fix critical issues."}
```

### 4. Present Results to User

"**Validation Complete**

**Status:** {Pass/Warning/Critical}
**Rating:** {rating}/5 - {label}
**Architecture Readiness:** {percentage}%

**Results:**
| Check | Status |
|-------|--------|
| Structure | {count} sections |
| FR Format | {status} |
| NFR Format | {status} |
| Quality | {status} |

**Critical Issues:** {count or 'None'}
{If any, list briefly}

**Warnings:** {count or 'None'}
{If any, list briefly}

**Top 3 Improvements:**
1. {Improvement 1}
2. {Improvement 2}
3. {Improvement 3}

**Report:** {report_path}"

### 5. Menu

**[R] Review** - Walk through findings section by section
**[A] Architecture** - Proceed to /create-architecture (if ready)
**[E] Edit** - Launch /prd-edit to fix issues
**[X] Exit** - Finish and review report manually
*Always available: **[P] Party Mode** | **[D] Deep Dive***

#### Menu Logic:

**R (Review):**
- Walk through report section by section
- Allow questions
- Return to menu after

**A (Architecture):**
- If Architecture Readiness >= 80%: "PRD is ready. Launch /create-architecture?"
  - If yes: Suggest running `/create-architecture`
- If < 80%: "PRD needs improvements first. Address these gaps: {list}"
- Return to menu

**E (Edit):**
- "The /prd-edit workflow can systematically address issues using this validation report."
- "Launch edit mode now?"
- If yes: Suggest running `/prd-edit`
- If no: Return to menu

**X (Exit):**
- "**Report Saved:** {report_path}"
- "**Status:** {status}"
- "**Next Steps:**
  - If Pass: Run /create-architecture
  - If Warning: Review warnings, then run /create-architecture or /prd-edit
  - If Critical: Run /prd-edit to fix issues"
- End workflow

---

## SUCCESS CRITERIA

- Report frontmatter finalized with complete status
- Overall status determined correctly
- Executive summary generated
- Clear presentation of findings to user
- Actionable menu options provided
- User can review, proceed to architecture, edit, or exit
