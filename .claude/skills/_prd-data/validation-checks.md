# PRD Validation Checks

**Shared validation criteria for prd-validate and prd-edit workflows.**

---

## Structure Checks

### Section Requirements by Project Type

| Project Type | Required | Recommended | Optional |
|--------------|----------|-------------|----------|
| **Web App / Mobile** | 1, 3 | 2, 4, 5 | 6, 7 |
| **API Service** | 1, 3 | 4, 5, 6 | 2, 7 |
| **CLI Tool** | 1, 3 | 4, 6 | 2, 5, 7 |
| **Library/SDK** | 1, 3 | 4, 6 | 2, 5, 7 |
| **Data Pipeline** | 1, 3 | 2, 4, 5 | 6, 7 |
| **ML Model/Service** | 1, 3 | 2, 4, 5 | 6, 7 |
| **Infrastructure/IaC** | 1, 3 | 2, 4, 6 | 5, 7 |
| **Microservices System** | 1, 3 | 2, 4, 5 | 6, 7 |
| **Plugin/Extension** | 1, 3 | 2, 4, 6 | 5, 7 |
| **Full Stack App** | 1, 3 | 2, 4, 5 | 6, 7 |
| **Prototype/MVP** | 1, 3 | 2 | 4, 5, 6, 7 |

### Section Reference

| # | Section | Purpose |
|---|---------|---------|
| 1 | Overview | Vision, classification, actors, success metrics, scope |
| 2 | Journeys/Workflows | Step-by-step actor flows |
| 3 | Functional Requirements | What the system does |
| 4 | Non-Functional Requirements | Quality constraints |
| 5 | Data Entities | Persistent data structures |
| 6 | Technology Constraints | Tech decisions/restrictions |
| 7 | Implementation Reference | Config schemas, output formats, error catalogs, algorithms |

### Classification Criteria

| Classification | Criteria |
|----------------|----------|
| **Complete** | All recommended sections for project type |
| **Adequate** | Required sections + some recommended |
| **Minimal** | Required sections only |
| **Incomplete** | Missing required sections |

---

## FR Format Checks

### FR Structure

Each FR should have:
- [ ] **Input:** Field names with constraints
- [ ] **Rules:** Business logic (not implementation)
- [ ] **Output:** Observable, testable behavior
- [ ] **Error:** Specific cases with handling

Optional:
- [ ] **Depends:** References to blocking FRs

### FR Quality Criteria

- Actor is explicit (User, System, Admin, Operator)
- No vague descriptors ("various", "multiple", "some")
- No subjective terms ("easy", "intuitive", "fast") without metrics
- No technology names in Input/Rules/Output/Error

### ID Format (Flexible)

Accept any consistent format:
- Area-based: `FR-AUTH-001`
- Sequential: `FR-001`
- Descriptive: `user-registration`

Flag as warning only if IDs are inconsistent or missing.

---

## NFR Format Checks

### NFR Structure

Single line with:
- [ ] Measurable metric
- [ ] Specific target
- [ ] Condition/context

Example: `API response time under 200ms for 95th percentile under normal load`

### When NFRs Are Required

- Production systems: Required
- Prototypes/MVPs: Optional
- Internal tools: Recommended for performance-critical features

---

## Quality Checks

### Information Density

**Anti-patterns to detect:**
- "The system will allow users to..." → "Users can..."
- "It is important to note that..." → State directly
- "In order to..." → "To..."
- "Due to the fact that..." → "because"
- Redundant: "future plans", "past history", "absolutely essential"

Severity: Warning (5-10 violations) / Info (<5)

### Measurability

**Success Metrics:**
- Should be quantifiable with specific targets
- At least one designated as primary

**NFRs:**
- Each should have metric + target + condition

### Implementation Leakage

**Technology names in FRs (Sections 1-5):**

Flag as info/warning (not error) - sometimes intentional:
- Frameworks: React, Django, FastAPI
- Databases: PostgreSQL, MongoDB
- Cloud: AWS, Azure, S3

**Exception:** Section 6 (Technology Constraints) should contain these

---

## Traceability Checks

### Dependency Validation

- All `Depends:` references should exist
- No circular dependencies

### Data Entity Validation (If Section 5 Present)

- Each entity should have Related FRs
- Related FRs should exist

### Capability Area Validation (If Section 3 Present)

- FRs are grouped under `### Capability Area` headers
- Every FR belongs to exactly one capability area
- FR count >= capability area count (at least 1 FR per area)

---

## Compliance Checks (Optional)

### Domain Compliance

Apply based on project context:

**Enterprise/B2B:**
- Security requirements in NFRs
- Audit/logging mentioned
- Role-based access implied

**Consumer:**
- Privacy considerations
- Accessibility mentions

**Fintech:**
- Encryption requirements
- Compliance mentions

**Healthcare:**
- Privacy requirements (HIPAA)
- Consent management

### Project-Type Compliance

**CLI Tool:**
- Input/output formats in FRs
- Exit codes or status reporting

**API Service:**
- Rate limiting in NFRs
- Authentication method
- Error response format

**Web App:**
- Session/auth handling
- Responsive/accessibility

---

## Architecture Readiness

| Check | Enables |
|-------|---------|
| FR Input fields | API request specs |
| FR Output fields | API response specs |
| FR Error fields | Error taxonomy |
| Data Entities | Database schema |
| Technology Constraints | Stack selection |
| FR Dependencies | Implementation order |

**Ready:** Core checks pass (FR structure, Data Entities if needed)
**Needs Work:** Missing FR structure or required sections

> **Note:** The step 6 readiness gate in prd-create checks structural completeness and cross-reference integrity. The prd-validate workflow performs deep quality validation (density, measurability, leakage analysis). These are complementary, not duplicative.

---

## Scoring Guidelines

### Overall Quality Rating

| Rating | Label | Criteria |
|--------|-------|----------|
| 5/5 | Excellent | Complete for project type, exemplary format |
| 4/5 | Good | Adequate with minor gaps |
| 3/5 | Acceptable | Required sections present, some format issues |
| 2/5 | Needs Work | Missing recommended sections or format issues |
| 1/5 | Incomplete | Missing required sections |

### Validation Approach

**Strict mode:** For formal PRDs, enterprise projects
**Flexible mode:** For prototypes, MVPs, internal tools

Default to flexible mode - flag issues as info/warning rather than errors unless critical.
