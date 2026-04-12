---
name: 'step-03-assess'
description: 'Holistic assessment: document flow, dual-audience, architecture readiness, overall rating'

# File references
nextStepFile: '{skill_base}/steps-validate-prd/step-04-complete.md'
---

# Step 3: Assess

**Progress: Step 3 of 4** - Next: Complete

## STEP GOAL

Assess the PRD holistically: document flow, dual-audience effectiveness, architecture readiness, and assign overall quality rating.

## EXECUTION RULES

- **Auto-proceed step** - no user input required
- You are a Product Analyst (Validator) — synthesizing holistic quality assessment
- Evaluate the WHOLE document, not individual components
- This is the synthesis step - answers "Is this a good PRD?"

## SEQUENCE (Follow Exactly)

### 1. Document Flow Assessment

Read entire PRD and evaluate:

**Section Flow (adapted to project type):**
- Does Overview set up clear context?
- Does Section 2 (Journeys/Commands/Scenarios) lead naturally to FRs?
- Do FRs map to Data Entities (if applicable)?
**Narrative Coherence:**
- Cohesive story from vision to requirements?
- Consistent terminology throughout?

**Readability:**
- Clear structure and organization?
- Scannable for key information?

Rate: Excellent / Good / Adequate / Needs Work / Poor

### 2. Dual-Audience Effectiveness

**Human Readability:**
- Can stakeholders understand vision and scope?
- Is Overview clear for executives?
- Are User Journeys understandable for PMs?

Rate: Strong / Adequate / Weak

**LLM/Architecture Readiness:**
- FRs in consistent Input/Rules/Output/Error format?
- Data Entities convertible to schema?
- Technology Constraints clear for stack selection?

Rate: Strong / Adequate / Weak

### 3. Architecture Readiness Score

| PRD Element | Architecture Use | Status |
|-------------|------------------|--------|
| FR Input | → Contract request/parameter specs | {Yes/Partial/No} |
| FR Rules | → Implementation logic | {Yes/Partial/No} |
| FR Output | → Contract response/return specs | {Yes/Partial/No} |
| FR Error | → Error taxonomy | {Yes/Partial/No} |
| Data Entities | → Database schema (if applicable) | {Yes/Partial/No/N/A} |
| Technology Constraints | → Stack selection | {Yes/Partial/No} |
| FR Dependencies | → Build sequence | {Yes/Partial/No} |

Calculate readiness: (Yes=1, Partial=0.5, No=0, N/A=excluded) / applicable count * 100

### 4. Overall Quality Rating

Based on all assessments (this step + step 2), assign rating:

| Rating | Label | Criteria |
|--------|-------|----------|
| 5/5 | Excellent | Ready for Architecture, exemplary format |
| 4/5 | Good | Strong with minor improvements needed |
| 3/5 | Adequate | Acceptable but needs refinement |
| 2/5 | Needs Work | Significant gaps or format issues |
| 1/5 | Poor | Major flaws, substantial revision required |

### 5. Top 3 Improvements

Identify the 3 most impactful improvements:

1. **{Improvement 1}** - Why and how
2. **{Improvement 2}** - Why and how
3. **{Improvement 3}** - Why and how

### 6. Append to Report

```markdown
## Holistic Assessment

### Document Flow
**Structure:** {rating}
**Narrative:** {rating}
**Readability:** {rating}

### Dual-Audience Effectiveness
**Human Readability:** {Strong/Adequate/Weak}
**LLM/Architecture Ready:** {Strong/Adequate/Weak}

### Architecture Readiness

| Element | Status |
|---------|--------|
| FR Input → Contract specs | {status} |
| FR Rules → Implementation | {status} |
| FR Output → Contract response | {status} |
| FR Error → Error taxonomy | {status} |
| Data Entities → Schema | {status or N/A} |
| Tech Constraints → Stack | {status} |
| Dependencies → Sequence | {status} |

**Readiness Score:** {percentage}%

### Overall Quality Rating
**{rating}/5 - {label}**

{One-sentence summary}

### Top 3 Improvements
1. **{Improvement 1}**
   {Why and how}

2. **{Improvement 2}**
   {Why and how}

3. **{Improvement 3}**
   {Why and how}
```

Update frontmatter: add `'step-03-assess'` to `stepsCompleted`

### 7. Display Progress and Proceed

"**Assessment Complete**
- Document Flow: {rating}
- Architecture Readiness: {percentage}%
- Overall Rating: {rating}/5 - {label}

Finalizing report..."

**Auto-proceed:** Load and execute `{nextStepFile}`

---

## SUCCESS CRITERIA

- Document flow and coherence assessed
- Dual-audience effectiveness evaluated
- Architecture readiness scored
- Overall quality rating assigned (1-5)
- Top 3 improvements identified
- Findings appended to report
- Auto-proceeds without user input
