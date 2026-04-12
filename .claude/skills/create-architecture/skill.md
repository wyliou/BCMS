---
name: create-architecture
description: Collaborative architectural decision facilitation for AI-agent consistency. Produces a decision-focused architecture document optimized for preventing agent conflicts.
---

# Architecture Workflow

**Goal:** Create an architecture document that gives AI agents everything they need to build the application. Together with the PRD, these two documents provide complete implementation guidance.

**Your Role:** Architectural facilitator. Derive decisions from PRD, only ask when truly ambiguous.

---

## What This Produces (that PRD doesn't provide)

| Output | Purpose |
|--------|---------|
| Technology Stack + Build Commands | Specific choices with versions and exact build/test/lint commands |
| Project Structure | Exact directory layout with src/test markers |
| Coding Patterns | Naming, error format, error propagation, logging pattern, side-effect ownership |
| Module Boundaries | What code goes where, with paths, exports, and dependencies |
| Contracts | Project-type-adaptive: REST endpoints, CLI commands, or library API surface |
| Testing Strategy | Test tiers, fixture strategy, high-risk areas, golden files |
| Implementation Order | Build batch sequence derived from module dependency graph |
| Database Schema | Actual definitions from Data Entities (if applicable) |
| Legacy Integration | (Brownfield) Integration points, adapters, constraints |

---

## Workflow Overview

| Step | Name | Purpose | Mode |
|------|------|---------|------|
| 1 | **Init & Discovery** | Find PRD, detect state/continuation, extract constraints, detect brownfield, strip N/A sections | Derive + Confirm |
| 2 | **Technology & Foundation** | Stack selection, build commands, project structure, coding patterns, error propagation | Derive + Confirm |
| 3 | **Modules & Contracts** | Module boundaries, inter-module interfaces, project-type-adaptive contracts, cross-validation | Generate |
| 4 | **Testing & Build Order** | Test strategy, fixture plan, high-risk areas, implementation batch sequence | Generate |
| 5 | **Schema & Finalize** | DB schema, env vars, brownfield section, build-from-prd readiness validation | Generate |

---

## Project Type Adaptation

| Project Type | Has API Contracts | Has DB Schema | Has CLI Commands | Has Library API | Has Data Contracts | Has Resource Defs |
|--------------|-------------------|---------------|------------------|-----------------|--------------------|--------------------|
| Web App | Yes | Yes | No | No | No | No |
| API Service | Yes | Yes | No | No | No | No |
| CLI Tool | No | Maybe | Yes | No | No | No |
| Library/SDK | No | No | No | Yes | No | No |
| Desktop App | Maybe | Maybe | No | No | No | No |
| Mobile App | Maybe | Maybe | No | No | No | No |
| Full Stack | Yes | Yes | No | No | No | No |
| Data Pipeline | Maybe | Yes | Maybe | No | Yes | No |
| ML Model/Service | Yes | Yes | No | No | No | No |
| Infrastructure/IaC | No | No | Maybe | No | No | Yes |
| Microservices | Yes | Yes | No | No | No | No |
| Plugin/Extension | Maybe | Maybe | No | Yes | No | No |
| Prototype/MVP | Maybe | Maybe | Maybe | No | No | No |

---

## PRD Integration

**Required Input:** PRD document (up to 7 sections)

| PRD Section | Architecture Uses For |
|-------------|----------------------|
| 1. Overview | Project context, type detection (Greenfield/Brownfield), product category |
| 2. User Journeys | Flow understanding (read-only) |
| 3. Functional Requirements | Contracts (Input→Request, Output→Response, Error→Handling) |
| 4. Non-Functional Requirements | Architecture decisions (scale, security, performance) |
| 5. Data Entities | Database Schema generation |
| 6. Technology Constraints | Stack selection (Decided = locked, Open = select) |
| 7. Implementation Reference | Config schemas, output formats, error catalogs, algorithms |

**Optional Input:** Project Charter with Brownfield Context (Section 7)

| Charter Section | Architecture Uses For |
|-----------------|----------------------|
| Existing Systems | Integration points, API compatibility |
| Legacy Data | Migration strategy, schema mapping |
| Technical Constraints | Stack limitations from legacy |

---

## Design Principles

- **Build-from-prd compatible** - Output contains every field build-from-prd needs to plan batches
- **Project-type adaptive** - Contracts adapt to project type (REST, CLI, Library)
- **Greenfield and Brownfield** - supports both new builds and legacy integration
- **Derive, don't ask** - PRD provides context, only ask if truly ambiguous
- **No menus during generation** - flow through naturally, confirm at checkpoints
- **Lean output** - only what AI needs to build
- **PRD as source of truth** - reference FRs, don't duplicate content

---

## Navigation

**Natural Conversation (Preferred):**
Allow user to direct the workflow conversationally:
- "That stack looks good, continue" → Proceed to next step
- "I'd prefer using PostgreSQL instead" → Revise technology selection
- "Let's get architect and dev perspectives" → Launch party mode
- "Analyze the trade-offs more deeply" → Launch deep dive

**Menu (Fallback for Structure):**
Checkpoints use consistent menu patterns:

- **[C] Continue** - Proceed to next step
- **[R] Revise** - Make changes before proceeding
- **[P] Party Mode** - Multi-agent discussion (Steps 2, 3, 4)
- **[D] Deep Dive** - Advanced elicitation methods (Steps 2, 3, 4)
- **[X] Exit** - Stop workflow (state saved in frontmatter)

**Enhancement Options (Steps 2, 3, 4):**
- **Party Mode:** Get perspectives from architect, dev, and test agents on decisions
- **Deep Dive:** Apply technical, risk, and competitive analysis methods to validate choices

---

## Workflow Architecture

Uses **step-file architecture** for disciplined execution:

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file
- **Just-In-Time Loading**: Only current step file in memory
- **Sequential Enforcement**: Steps completed in order, no skipping
- **State Tracking**: Progress tracked in architecture document frontmatter
- **Inline Continuation**: Resume interrupted workflows detected in step-01

### Execution Rules

These principles ensure reliable execution. Deviate only with explicit reasoning documented in conversation:

- Load one step file at a time (keeps context focused)
- Read the entire step file before starting (ensures complete understanding)
- Complete steps in order (dependencies build on each other)
- Update architecture frontmatter when completing a step (enables continuation)
- Follow step file instructions (they encode best practices)

**When to Deviate:** If the user has specific preferences for structure or patterns that differ from defaults, acknowledge the deviation and proceed.

---

## Paths

- `template_path` = `{skill_base}/architecture-template.md`
- `data_files_path` = `{skill_base}/data/`

---

## Execution

Load and execute `steps/step-01-init.md` to begin.
