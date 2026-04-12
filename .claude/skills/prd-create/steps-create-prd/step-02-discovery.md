---
name: 'step-02-discovery'
description: 'Gather vision, classification, actors, success metrics, and scope'

# File references
nextStepFile: '{skill_base}/steps-create-prd/step-03-journeys.md'
prdPurpose: '{skills_root}/_prd-data/prd-purpose.md'
---

# Step 2: Discovery

**Progress: Step 2 of 6** - Next: Journeys & Mapping

## STEP GOAL

Extract essential context for AI implementation — vision, classification, actors, success metrics, and scope. Journeys/workflows and capability areas are handled in step 3.

## EXECUTION RULES

- User is the domain expert — extract, don't lecture
- Adapt conversation depth to project complexity — simple projects need fewer exchanges, complex ones deserve thorough exploration

## SEQUENCE (Follow Exactly)

### 1. Load Context

Read `{prdPurpose}` to understand PRD quality standards. This is the single load point for prd-purpose across the entire workflow.

### 2. Discovery Conversation

Gather all discovery information following the one-question-at-a-time principle. Cover these areas in natural order:

#### A. Vision

Topics to cover:
- What problem does this product solve?
- What makes this different from alternatives?

**Smart defaults:** Before asking each question, check loaded input documents for relevant information. If found, propose it and ask the user to confirm or refine.

#### B. Classification

Project Type (Greenfield/Brownfield) was already captured in step-01. Confirm or reference it — do not re-ask.

Topics to cover:
- Product category? (Present options: Web App, Mobile App, Desktop App, API Service, CLI Tool, Library/SDK, Data Pipeline, ML Model/Service, Infrastructure/IaC, Microservices System, Plugin/Extension, Full Stack App, Prototype/MVP)
- Context: Enterprise / Consumer / Internal / B2B?

**After product category identified:** Use the category-specific discovery questions below:

| Product Category | Key Discovery Questions |
|-----------------|------------------------|
| Web App / Full Stack App | What pages/views are core? SPA or multi-page? Auth requirements? |
| Mobile App | iOS, Android, or both? Offline capability needed? Push notifications? |
| Desktop App | Target OS? Auto-update needed? System integration points? |
| API Service | REST, GraphQL, or gRPC? Auth model? Rate limiting needs? |
| CLI Tool | Interactive or batch mode? Config file format? Piping/scripting support? |
| Library/SDK | Target language(s)? Dependency constraints? Versioning strategy? |
| Data Pipeline | Batch or streaming? Data volume estimates? Error/retry strategy? |
| ML Model/Service | Training data source? Inference latency requirements? Model versioning? |
| Infrastructure/IaC | Cloud provider(s)? Multi-region? Existing infra to integrate? |
| Microservices System | Service boundaries? Inter-service communication? Shared data? |
| Plugin/Extension | Host platform? API surface available? Sandboxing constraints? |
| Prototype/MVP | Core hypothesis to test? Success criteria for next phase? Time constraint? |

#### C. Actors

Topics to cover:
- Who are the primary actor types? (Users, operators, admins, systems)
- What is each actor's primary goal?

Gather enough detail to populate the Actors table (Actor Type + Primary Goal for each).

#### D. Brownfield Context (If Brownfield)

If project type is brownfield, gather additional context:
- What existing systems are being replaced or integrated with?
- Is there legacy data that needs to be migrated? (Volume, complexity)
- Are there existing users whose workflows will change?
- What technical constraints come from the legacy systems?
- What's the coexistence strategy? (Parallel run, phased cutover, big bang)

**Store brownfield context explicitly for step 3 (migration journeys, brownfield-specific capability areas) and step 5 (tech constraints from legacy systems).**

#### E. Success & Scope

Topics to cover:
- What are the key metrics that define success? (1-3 metrics; designate one as primary)
- What's in MVP scope? (Core capabilities)
- What's explicitly out of scope? (Deferred to later phases)

### 3. Update Document

After gathering information, read `outputPath` from the PRD document's frontmatter to determine the target file. Write Section 1 (Overview) following the PRD template structure — fill in Vision, Classification, Actors, Success Metrics, and MVP Scope. Include Brownfield Context sub-section if applicable.

### 4. Validation

Before proceeding, verify:

| Check | Requirement |
|-------|-------------|
| Vision | 2-3 sentences, clear value proposition |
| Classification | Product Category and Primary Context filled in |
| Actors | At least 1 actor type with goal |
| Success Metrics | 1-3 metrics with primary designation |
| Scope | At least 2 in-scope, 1 out-of-scope items |

**If validation fails:** Ask targeted questions to fill gaps.

### 5. Report & Menu

**Report:**
- Summary of what was captured
- Any gaps or areas needing clarification

**Menu:**

**[C] Continue** - Proceed to Journeys & Mapping (Step 3)
**[R] Revise** - Discuss changes to Overview
