# PRD Guidelines

**Purpose:** Create PRDs optimized for both human stakeholders and AI agent consumption.

---

## Core Philosophy

### Dual-Audience Design

PRDs serve two audiences:
1. **Humans** - Product managers, stakeholders, developers reviewing requirements
2. **AI Agents** - Architecture generation, epic breakdown, implementation

### Information Density

Every sentence should carry information weight. AI agents consume precise, dense content efficiently.

**Avoid:**
- "The system will allow users to..." → "Users can..."
- "It is important to note that..." → State directly
- "In order to..." → "To..."
- Conversational filler and padding

**Goal:** Maximum information per word. Zero fluff.

### Consistent Terminology

Use one term per concept throughout the PRD. If the domain calls it an "order," never switch to "transaction" or "purchase" mid-document. Define domain-specific terms on first use when their meaning isn't obvious.

---

## Document Structure

### Required Sections (All Projects)

| Section | Purpose |
|---------|---------|
| **1. Overview** | Vision, classification, actors, success metrics, scope |
| **3. Functional Requirements** | What the system does |

### Conditional Sections (By Project Type)

| Section | Include When |
|---------|--------------|
| **2. Journeys/Workflows** | UI-based products (Web App, Mobile, Desktop), data pipelines, infrastructure |
| **4. Non-Functional Requirements** | Production systems with quality constraints |
| **5. Data Entities** | Systems with persistent storage |
| **6. Technology Constraints** | Existing tech decisions, restrictions, or integration points |
| **7. Implementation Reference** | Project has defined formats, codes, algorithms, or config schemas |

### Section Applicability

Sections 1 (Overview) and 3 (Functional Requirements) are required for all projects. For conditional sections, assess based on actual project needs:

| Section | Include When |
|---------|-------------|
| **2. Journeys/Workflows** | Product has user-facing flows or multi-step processes. Format adapts by category (User Journeys, Command Workflows, Data Workflows, etc.) |
| **4. Non-Functional Requirements** | Production system with quality constraints. Skip for prototypes. |
| **5. Data Entities** | System has persistent storage |
| **6. Technology Constraints** | Tech decisions are pre-made or integrations exist |
| **7. Implementation Reference** | Defined formats, algorithms, or config schemas exist |

### Brownfield Projects

Brownfield PRDs must additionally address:
- **Existing systems** — what is being replaced, integrated with, or migrated from
- **Legacy data** — volume, complexity, migration strategy
- **Coexistence** — how old and new systems run in parallel during transition
- **Brownfield-specific capability areas** — Data Migration, Legacy Compatibility, Transition Management (include only those that apply)

---

## Functional Requirements Format

### Recommended FR Structure

```markdown
**[Descriptive ID]**: [Actor] [capability]
- **Input:** field1 (constraints), field2 (constraints)
- **Rules:** Business logic, conditions
- **Output:** Success behavior (testable)
- **Error:** Error cases → handling
- **Depends:** Other FRs this requires (if any)
```

### ID Conventions (Flexible)

Choose an approach that fits your project:

| Style | Example | Best For |
|-------|---------|----------|
| Area-based | `FR-AUTH-001` | Large projects with many FRs |
| Sequential | `FR-001` | Small projects |
| Descriptive | `user-registration` | When readability matters most |

### FR Quality Criteria

| Criterion | Requirement |
|-----------|-------------|
| **Actor** | Explicit (User, System, Admin, Operator) — never "the system" without context |
| **Input** | Types, formats, limits, and validation rules specified |
| **Rules** | Business logic only — no implementation details (no "use SQL query," "call API") |
| **Output** | Observable result + state change — specific enough to write a test against |
| **Error** | Every input validation failure and business rule violation has explicit handling |
| **Boundary conditions** | Min/max values, empty states, and edge cases addressed in Rules or Error |
| **State transitions** | If the FR changes entity state (e.g., order: pending → confirmed), state flow is explicit |
| **Data flow direction** | Clear who provides input and who receives output |

---

## Non-Functional Requirements Format

### Single-Line Format

```markdown
**[ID]**: [metric] [target] under [condition]
```

Every NFR **must** include a measurable target. Vague NFRs like "system should be fast" or "high availability" are not acceptable.

### Examples

```markdown
**NFR-PERF-001**: API response time under 200ms for 95th percentile under normal load
**NFR-SEC-001**: All data encrypted at rest using AES-256
**NFR-REL-001**: 99.9% uptime during business hours
```

**Anti-pattern:** `NFR-PERF-001: System should perform well` — no metric, no target, not testable.

### Categories

| Category | Code | Examples |
|----------|------|----------|
| Performance | PERF | Response time, throughput, startup time |
| Security | SEC | Encryption, auth expiry, data protection |
| Scalability | SCALE | Concurrent users, data volume |
| Reliability | REL | Uptime, recovery time, durability |
| Accessibility | ACC | WCAG compliance level, screen reader support, keyboard navigation |
| Usability | USE | Task completion rate, learning curve, error recovery |
| Maintainability | MAINT | Code coverage, dependency freshness, deployment frequency |
| Compatibility | COMPAT | Browser support, OS support, API version compatibility |

Select categories relevant to the project — not all apply to every project type. PERF and at least one other are typically required for production systems.

---

## Data Entities

When your system has persistent storage, document entities:

```markdown
## Data Entities

| Entity | Key Attributes | Related FRs |
|--------|---------------|-------------|
| User | id, email, password_hash, created_at | FR-AUTH-001, FR-AUTH-002 |
| Order | id, user_id, status, total, created_at | FR-ORDER-001 |
```

---

## Technology Constraints

Document decisions that constrain implementation:

```markdown
## Technology Constraints

**Decided:**
- Backend: Python 3.11+ with FastAPI
- Database: PostgreSQL 15+

**Open (implementer decides):**
- ORM choice
- Caching strategy
```

**Integration Points:** For projects connecting to external systems, document each integration with direction (In/Out/Both), data exchanged, and auth method.

**Compliance Notes:** Single line summarizing regulatory or policy requirements when applicable.

Skip this section if the implementer has full freedom and no integrations exist.

---

## Implementation Reference (Section 7)

Include when the project has defined formats, codes, algorithms, or config schemas that implementing agents need as reference. This section bridges the gap between "what" (FRs) and "how" by providing reference material without dictating implementation.

### Sub-sections (include only those that apply)

| Sub-section | Include When |
|-------------|-------------|
| **Configuration Schema** | User-editable config files (YAML, JSON, env vars) |
| **Output Formats** | Defined console output, file formats, or API response structures |
| **Error/Status Code Catalog** | Coded errors (ERR_001) or status codes for consistent reporting |
| **Algorithm Details** | Multi-step logic, calculations, or processing pipelines needing exact specification |
| **Examples & Edge Cases** | Complex rules that benefit from concrete input/output examples |

### Quality Criteria

- Algorithm steps must be ordered and unambiguous — an AI agent should reproduce the same logic from the description alone
- Error codes must map to specific FR error conditions
- Config schemas must specify types, defaults, and valid ranges
- Examples must show both typical cases and boundary/edge cases
- Test corpus notes must identify the file, the pattern, and the affected FR(s)

---

## Capability Areas

Capability areas are logical groupings of related functional requirements. FRs are grouped under `### Capability Area Name` headers in Section 3.

FRs are grouped under `### Capability Area Name` headers in Section 3. All FRs are implemented — scope is controlled at the MVP Scope level (Section 1), not per-FR.

---

## Traceability

Good PRDs maintain end-to-end traceability:

```
Vision → Success Metrics → Journeys/Workflows → Functional Requirements → Data Entities
```

### Traceability Checks

| Check | How to Verify | Gap Indicator |
|-------|---------------|---------------|
| Vision → Metrics | Each success metric ties to the stated vision | Metric measures something unrelated to the vision |
| Metrics → Journeys | Each journey supports at least one success metric | Journey exists with no metric connection |
| Journeys → FRs | Each journey step maps to at least one FR | Journey step has no implementing FR |
| FRs → Entities | Each FR that reads/writes data references a data entity | FR mentions data not in Section 5 |
| Scope → FRs | Every in-scope item has at least one FR | Scope item with zero FRs |
| FRs → Capability Areas | Every FR belongs to a capability area | Orphan FR outside any capability area |

### Common Traceability Gaps

- **Orphan FR:** FR exists but traces to no journey step or scope item — question whether it's needed
- **Empty scope item:** Scope item declared but no FRs implement it — missing requirements
- **Phantom entity:** Data entity listed but no FR references it — remove or add FRs

---

## Anti-Patterns

Patterns that weaken PRD quality and cause implementation errors:

| Anti-Pattern | Example | Fix |
|--------------|---------|-----|
| **Implementation leak** | "Use PostgreSQL JOIN to fetch..." in FR Rules | Rewrite as business logic: "Retrieve user's orders sorted by date" |
| **Vague success metric** | "Improve user satisfaction" | Add target: "Increase NPS from 30 to 50 within 6 months" |
| **Missing error path** | FR specifies happy path only | Add Error field with every failure condition |
| **Scope creep** | Too many capability areas for MVP | Re-evaluate — move non-essential items to Out of Scope |
| **Copy-paste NFR** | "99.99% uptime" for an internal tool | Match NFR targets to actual project context |
| **Ambiguous actor** | "The system processes..." | Specify: "System (triggered by cron schedule) processes..." |
| **Untraceable requirement** | FR exists but connects to no journey or scope item | Either trace it or remove it |

---

## What Makes a Good PRD?

| Principle | Description | Test |
|-----------|-------------|------|
| **Dense** | Every sentence carries weight | No sentence can be removed without losing information |
| **Measurable** | Success metrics and NFRs have quantifiable targets | Every metric has a number and timeframe |
| **Traceable** | Requirements link to actor needs | Every FR traces back to a journey step or scope item |
| **Consistent** | One term per concept, uniform formatting | No synonym drift, no format variations |
| **Bounded** | Clear in-scope and out-of-scope | An AI agent can determine what NOT to build |
| **Actionable** | AI agents can implement from FRs alone | Each FR has enough detail to write code and tests |

The goal is **useful documentation**, not **comprehensive documentation**.
