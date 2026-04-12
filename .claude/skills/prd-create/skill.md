---
name: prd-create
description: Create comprehensive PRDs optimized for AI-powered development
---

# Create PRD Workflow

**Goal:** Create PRDs optimized for AI agent consumption through a 6-step workflow with dedicated FR generation and readiness gate validation.

**Output:** A structured PRD document (up to 7 sections: Overview, Journeys, Functional Requirements, NFRs, Data Entities, Tech Constraints, Implementation Reference) saved to the user's chosen path.

**Your Role:** Product Analyst - you bring systematic requirements elicitation and structured decomposition; the user brings domain expertise and product decisions.

---

## WORKFLOW OVERVIEW (6 Steps)

| Step | Name | Purpose |
|------|------|---------|
| 1 | **Init** | Discover existing PRDs, determine output path, detect continuation |
| 2 | **Discovery** | Vision, classification, actors, success metrics, scope |
| 3 | **Journeys & Mapping** | Journeys/workflows, capability mapping |
| 4 | **Requirements** | FR generation, completeness verification, FR deepening |
| 5 | **Specifications** | Tech Constraints, NFRs, Data Entities, Section 7 |
| 6 | **Complete** | Readiness gate and handoff |

---

## KEY RULES

- **One Question at a Time:** Ask a single focused question, wait for the answer, then ask the next. Never batch multiple questions. The only exception is the step-end menu.
- **Smart Defaults:** Before asking a question, check loaded input documents and prior context for relevant information. If found, propose it and ask the user to confirm or refine — don't make the user repeat what's already known.
- **Compose-Then-Write:** Gather all information for a section completely before writing it to the document. Never leave a section in a partial state. Different sections can be written at different times. **This rule applies in every step — steps 2 through 5 must each verify section completeness before writing.**
- **Readiness Gate:** Step 6 validates structural completeness only; deep quality validation is /prd-validate's domain.
- **Frontmatter Updates:** Always update `stepsCompleted` in frontmatter when the user selects [C] Continue, BEFORE loading the next step file. This ensures progress is saved even if the session is interrupted.

---

## NAVIGATION

Each step ends with a menu. The standard menu includes:
- **[C] Continue** - Proceed to next step
- **[R] Revise** - Make changes before proceeding
- **[X] Exit** - Save progress and stop
*Always available: **[P] Party Mode** | **[D] Deep Dive***

Step files specify what [C] leads to and what [R] means in context. The shared items ([X], [P], [D]) are not repeated in step files.

**On [C]:** Update frontmatter (add current step to `stepsCompleted`), then load and execute the next step file.

**Return Protocol:** After [P] Party Mode or [D] Deep Dive completes, return to the current step's menu. For each actionable recommendation, ask the user: "The agents suggested {X}. Apply this change? [Y/N]" Apply approved changes before proceeding.

**Deviation:** If the user has a valid reason to skip or reorder steps, acknowledge and proceed.

---

## Execution

Load and execute `./steps-create-prd/step-01-init.md` to begin.
