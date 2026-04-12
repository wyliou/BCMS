---
name: 'step-06-complete'
description: 'Readiness gate and handoff'

# File references
validationChecks: '{skills_root}/_prd-data/validation-checks.md'
---

# Step 6: Complete

**Progress: Step 6 of 6** - Workflow Complete

## STEP GOAL

Perform readiness gate (structural completeness + cross-reference integrity) and prepare for handoff.

## EXECUTION RULES

- This is the final step
- Readiness gate issues MUST be fixed before handoff
- Deep quality validation (density, measurability, leakage) is /prd-validate's domain — do not duplicate here

## SEQUENCE (Follow Exactly)

### 1. Readiness Gate

Structural completeness and cross-reference integrity checks only. This is NOT deep quality validation — that's /prd-validate's role.

#### A. Document Structure

Refer to `{validationChecks}` Section Requirements table to determine which sections are **Required**, **Recommended**, or **Optional** for this product type. Verify each required section is populated. Recommended sections should be populated but are not blockers.

#### B. Placeholder Cleanup

Scan the entire document for `{{...}}` patterns. These are TEMPLATE placeholders from prd-template.md and must ALL be removed or filled by step 6. No `{{...}}` pattern is acceptable in the final document — if a section is optional and not populated, remove the entire section rather than leaving placeholders.

#### C. Cross-Reference Integrity

| Check | Validation |
|-------|------------|
| Dependency validity | All `Depends:` references exist, no circular deps |
| Entity traceability | All entity Related FRs exist in Section 3 (skip if Section 5 not applicable) |

**Mandatory: Do not allow handoff with structural issues.**

If any check fails:
1. List specific issues found
2. Fix each issue (update the relevant section)
3. Re-run the check
4. Repeat until all pass

### 2. Update Frontmatter

Update the PRD frontmatter:
```yaml
---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-03-journeys', 'step-04-requirements', 'step-05-specifications', 'step-06-complete']
outputPath: '{outputPath}'
---
```

### 3. Present Completion

"**PRD Complete**

**Document:** {outputPath}

**Summary:**
- {FR count} Functional Requirements across {area count} capability areas
- {NFR count} Non-Functional Requirements {or "N/A"}
- {entity count} Data Entities {or "N/A"}
- Readiness Gate: PASS

**Next Steps:**
1. Review the PRD with stakeholders
2. Run /prd-validate for deep quality validation (density, measurability, traceability)
3. Run /create-architecture to generate the Architecture document"

### 4. Menu

**[A] Architecture** - Run /create-architecture
**[V] Validate** - Run /prd-validate
**[S] Show PRD** - Display the complete document
**[X] Exit** - Finish
