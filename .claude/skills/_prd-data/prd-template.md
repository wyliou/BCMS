---
stepsCompleted: []
outputPath: ''
---

# Product Requirements Document - {{project_name}}

**Author:** {{user_name}}
**Date:** {{date}}

---

## 1. Overview

### Vision
{{2-3 sentences describing the core product vision and value proposition}}

### Classification
| Attribute | Value |
|-----------|-------|
| Project Type | {{Greenfield / Brownfield}} |
| Product Category | {{Web App / Mobile App / Desktop App / API Service / CLI Tool / Library/SDK / Data Pipeline / ML Model/Service / Infrastructure/IaC / Microservices System / Plugin/Extension / Full Stack App / Prototype/MVP / Custom: describe}} |
| Primary Context | {{Enterprise / Consumer / Internal / B2B}} |

### Brownfield Context (If Applicable)

> *Complete for Brownfield projects. Remove this section if Greenfield with no legacy systems.*

| Existing System | Disposition | Integration Type |
|-----------------|-------------|------------------|
| {{system_name}} | Replace / Integrate / Migrate From | API / DB / File |

**Legacy Data:** {{description of data to migrate, or "N/A"}}
**Coexistence Strategy:** {{Parallel Run / Phased Cutover / Big Bang / N/A}}

### Actors
| Actor Type | Primary Goal |
|------------|--------------|
| {{actor_type_1}} | {{what they want to accomplish}} |
| {{actor_type_2}} | {{what they want to accomplish}} |

### Success Metrics
| Metric | Target | Primary |
|--------|--------|---------|
| {{metric_1}} | {{quantifiable target}} | Yes |
| {{metric_2}} | {{quantifiable target}} | No |

### MVP Scope

**In Scope:**
- {{core capability 1}}
- {{core capability 2}}
- {{core capability 3}}

**Out of Scope:**
- {{deferred capability 1}}
- {{deferred capability 2}}

---

## 2. Journeys/Workflows

> *Format adapts by product category: User Journeys, Command Workflows, Data Workflows, Integration Scenarios, etc.*

### {{Actor Type}}: {{Journey/Workflow Name}}
{{3-5 steps describing the actor's flow through the system}}

---

## 3. Functional Requirements

### {{Capability Area 1}}

**FR-001**: [Actor] [capability]
- **Input:** field1 (constraints), field2 (constraints)
- **Rules:** IF condition THEN action; business logic
- **Output:** success behavior
- **Error:** error case → handling
- **Depends:** FR-xxx (if any)

**FR-002**: [Actor] [capability]
- **Input:** field1 (constraints), field2 (constraints)
- **Rules:** IF condition THEN action
- **Output:** success behavior
- **Error:** error case → handling

### {{Capability Area 2}}

**FR-003**: [Actor] [capability]
- **Input:** field1 (constraints)
- **Rules:** business logic
- **Output:** success behavior
- **Error:** error case → handling

---

## 4. Non-Functional Requirements

> *Include only categories relevant to the project. See prd-purpose.md for the full category list (PERF, SEC, SCALE, REL, ACC, USE, MAINT, COMPAT).*

### {{Category}}
- **NFR-{{CODE}}-001**: {{metric}} {{target}} under {{condition}}

---

## 5. Data Entities

| Entity | Key Attributes | Related FRs |
|--------|---------------|-------------|
| {{Entity1}} | id, {{attr1}}, {{attr2}}, created_at | FR-xxx, FR-xxx |
| {{Entity2}} | id, {{attr1}}, {{attr2}} | FR-xxx |

---

## 6. Technology Constraints

**Decided (non-negotiable):**
- {{constraint 1}}
- {{constraint 2}}

**Open (agent can decide):**
- {{decision area 1}}
- {{decision area 2}}

### Integration Points (Optional)

> *Complete for projects connecting to existing systems. Skip if greenfield with no integrations.*

| System | Direction | Data/Purpose | Auth Method |
|--------|-----------|--------------|-------------|
| {{system name}} | In/Out/Both | {{what data flows}} | {{SSO/API Key/etc.}} |

### Compliance Notes (Optional)

> *Single line summarizing regulatory or policy requirements.*

{{e.g., "SOX audit logging required" or "Contains PII - encryption at rest" or "N/A"}}

---

## 7. Implementation Reference (Optional)

> *Include sub-sections as needed: Configuration Schema, Output Formats, Error/Status Code Catalog, Algorithm Details, Examples & Edge Cases, Test Corpus Notes (for data-processing projects with test data). See prd-purpose.md for quality criteria.*
