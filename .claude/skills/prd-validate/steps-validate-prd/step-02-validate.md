---
name: 'step-02-validate'
description: 'Run all validation checks: structure, format, quality, compliance'

# File references
nextStepFile: '{skill_base}/steps-validate-prd/step-03-assess.md'
validationChecks: '{skills_root}/_prd-data/validation-checks.md'
---

# Step 2: Validate

**Progress: Step 2 of 4** - Next: Assess

## STEP GOAL

Run comprehensive validation checks against PRD Guidelines: structure, format, quality, and compliance.

## EXECUTION RULES

- **Auto-proceed step** - no user input required
- You are a Product Analyst (Validator) — running validation checks
- Run all checks in sequence
- Display progress, append findings, auto-proceed to next step
- Reference `{validationChecks}` for detailed criteria

## SEQUENCE (Follow Exactly)

---

### PART A: STRUCTURE & FORMAT

#### A1. Extract PRD Structure

Scan entire PRD and extract:
- All `##` (Level 2) section headers in order
- Frontmatter metadata if present

#### A2. Check Section Structure

First, identify project type from Overview/Classification. Then check sections based on type:

Refer to `{validationChecks}` Section Requirements table to determine which sections are Required, Recommended, or Optional for this project type.

| Section | Variations |
|---------|------------|
| 1. Overview | Executive Summary, Introduction |
| 2. Journeys/Workflows | User Journeys, Command Workflows, Data Workflows, Integration Scenarios, Operational Workflows, etc. |
| 3. Functional Requirements | Features, Capabilities |
| 4. Non-Functional Requirements | NFRs, Quality Attributes |
| 5. Data Entities | Data Model, Entities |
| 6. Technology Constraints | Tech Stack, Constraints |
| 7. Implementation Reference | Config Schema, Output Formats, Error Catalog, Algorithms |

**Classify:**
- Complete: All recommended sections for project type
- Adequate: Required sections + some recommended
- Minimal: Required sections only
- Incomplete: Missing required sections

#### A3. FR ID Format Check

**Accept any consistent format:**
- Area-based: `FR-AUTH-001`
- Sequential: `FR-001`
- Descriptive: `user-registration`

**Check:**
- IDs are present
- IDs are consistent in style
- No duplicates

#### A4. FR Structure Check

For each FR, verify:
- [ ] Has Input with constraints
- [ ] Has Rules with business logic
- [ ] Has Output with testable behavior
- [ ] Has Error with handling
- [ ] Has Depends if references other FRs (optional)

Calculate FR format compliance: (complete FRs / total FRs) * 100

#### A5. NFR ID Format Check (If NFRs Present)

**Accept any consistent format** (NFR-PERF-001, NFR-001, or descriptive)
- Check IDs are present and consistent

#### A6. NFR Structure Check

For each NFR:
- [ ] Has measurable metric
- [ ] Has specific target
- [ ] Has condition/context

#### A7. Dependency Validation

- Verify all `Depends: FR-xxx` references exist
- Flag orphaned dependencies

#### A8. Capability Area Validation

- FRs are grouped under `### Capability Area` headers in Section 3?
- Every FR belongs to exactly one capability area (no orphan FRs outside headers)?
- At least 1 FR per capability area (no empty areas)?

#### A9. Traceability Check

Verify cross-references between sections. Skip checks for sections not present in the PRD.

| Chain | Check | Gap Indicator |
|-------|-------|---------------|
| Scope → FRs | Every in-scope item (Section 1) has at least one FR | Scope item with zero FRs |
| Journeys → FRs | Each journey step (Section 2) maps to at least one FR | Journey step with no implementing FR |
| FRs → Entities | Each FR that reads/writes data references a data entity (Section 5) | FR mentions data not in Section 5 |

Count: {covered}/{total} traceable links verified. Flag gaps as warnings.

---

### PART B: CONTENT QUALITY

#### B1. Information Density Check

Scan for anti-patterns:
- "The system will allow users to..."
- "It is important to note that..."
- "In order to", "Due to the fact that"
- Redundant phrases

Count violations. Severity: Critical (>10) / Warning (5-10) / Pass (<5)

#### B2. Measurability Check

**Success Metrics (Section 1):**
- Are Success Metrics present with quantifiable targets? Is one designated primary?

**NFRs:**
- Count NFRs with metric + target + condition

Severity: Critical (<50%) / Warning (50-80%) / Pass (>80%)

#### B3. FR Quality Check

For each FR, check against FR Quality Criteria from prd-purpose.md:
- Actor is explicit (not vague "the system")?
- Input has types, formats, limits, and validation rules?
- Rules capture business logic only (no implementation details)?
- Output is observable with state change — specific enough to test?
- Error covers every input validation failure and business rule violation?
- Boundary conditions addressed (min/max, empty states, edge cases)?
- State transitions explicit if entity state changes (e.g., pending → confirmed)?
- Data flow direction clear (who provides input, who receives output)?

#### B4. Implementation Leakage Check

Scan Sections 1-5 for technology names:
- Frameworks (React, Django, FastAPI)
- Databases (PostgreSQL, MongoDB)
- Cloud (AWS, Azure, S3)
- Languages in requirements

**Exception:** Section 6 (Technology Constraints) MAY contain these

Severity: Critical (>5) / Warning (2-5) / Pass (<2)

#### B5. Data Entities Quality

- Each entity has Related FRs?
- Related FRs exist?
- No orphaned references?

#### B6. Implementation Reference Quality (If Section 7 Present)

For each sub-section present, verify:

**7.1 Configuration Schema:**
- [ ] Structure documented with field types
- [ ] Validation rules specified where applicable

**7.2 Output Formats:**
- [ ] Exact format examples provided
- [ ] Matches FR Output specifications

**7.3 Error Code Catalog:**
- [ ] All error codes from FRs documented
- [ ] Each has Description, Cause, Resolution
- [ ] Codes are consistent format (ERR_xxx, ATT_xxx)

**7.4 Algorithm Details:**
- [ ] Multi-step processes have numbered steps
- [ ] Input/Process/Output for each step
- [ ] Aligns with FR Rules

**7.5 Examples & Edge Cases:**
- [ ] Complex rules have concrete examples
- [ ] Edge cases include expected handling

---

### PART C: COMPLIANCE

#### C1. Extract Classification

From Overview, extract:
- Project Type, Product Category, Primary Context

#### C2. Domain Compliance

Based on Primary Context, check required patterns:

**Enterprise/B2B:** Security NFRs, audit/logging, role-based access
**Consumer:** Privacy, UX metrics, accessibility
**Fintech:** Encryption, compliance, audit trail
**Healthcare:** Privacy (HIPAA), consent management

#### C3. Project-Type Compliance

Based on Product Category, check required elements. Refer to `{validationChecks}` Project-Type Compliance section for detailed checks. Common patterns:

**CLI Tool:** Input/output formats, exit codes, config
**Web App:** Responsive, session/auth, frontend NFRs
**API Service:** API FRs, rate limiting, auth, error format
**Desktop App:** Platform targets, installation, offline
**Mobile App:** Platform targets, offline, push notifications
**Data Pipeline:** Data sources, transforms, scheduling, error handling
**ML Model/Service:** Training data, inference latency, model versioning
**Infrastructure/IaC:** Cloud resources, networking, DR strategy
**Microservices:** Service boundaries, communication contracts, data ownership
**Library/SDK:** Language support, API surface, documentation
**Plugin/Extension:** Host API, extension points, version compatibility
**Full Stack App:** Frontend + backend + database coherence
**Prototype/MVP:** Core hypothesis testable, minimal but complete

#### C4. Technology Constraints Check

- Decided section present with non-negotiable items?
- Open section present with areas for agent decision?

---

### PART D: APPEND TO REPORT

```markdown
## Structure & Format

**Sections:** {count} present - {classification}
**FR Format:** {compliance}% ({count}/{total} with Input/Rules/Output/Error)
**NFR Format:** {compliance}% ({count}/{total} single-line)
**Dependencies:** {valid}/{total} valid
**Capability Areas:** {area_count} areas, {orphan_frs} orphan FRs
**Traceability:** {covered}/{total} links verified

### FR Format Details
| Check | Pass | Fail |
|-------|------|------|
| Has Input | {n} | {n} |
| Has Rules | {n} | {n} |
| Has Output | {n} | {n} |
| Has Error | {n} | {n} |

### Traceability Gaps
| Chain | Gap |
|-------|-----|
{gaps or "No traceability gaps found"}

## Content Quality

**Information Density:** {severity} ({count} violations)
**Measurability:** {severity} ({percentage}%)
**FR Quality Score:** {percentage}%
**Implementation Leakage:** {severity} ({count} found)
**Data Entities:** {count} entities, {orphans} orphaned
**Implementation Reference:** {status} (Section 7: {sub-sections present or "N/A"})

{If violations, list top 5 examples with locations}

## Compliance

**Domain ({context}):** {percentage}% ({met}/{total})
**Project-Type ({category}):** {percentage}% ({met}/{total})
**Technology Constraints:** {status}

### Compliance Gaps
| Gap | Impact | Remediation |
|-----|--------|-------------|
{gaps or "No significant gaps"}
```

Update frontmatter: add `'step-02-validate'` to `stepsCompleted`

---

### PART E: DISPLAY PROGRESS AND PROCEED

**Validation Complete**
- Structure: {classification} ({count} sections)
- FR Format: {severity} ({percentage}%)
- NFR Format: {severity} ({percentage}%)
- Traceability: {covered}/{total} links verified
- Quality: {severity}
- Compliance: {severity}
- Implementation Reference: {status if Section 7 present, else 'N/A'}

Proceeding to assessment...

**Auto-proceed:** Load and execute `{nextStepFile}`

---

## SUCCESS CRITERIA

- All structure checks completed
- All format checks completed
- All quality checks completed
- All compliance checks completed
- Findings appended to report
- Auto-proceeds without user input
