---
name: prd-validate
description: Validate PRDs against PRD Guidelines
---

# Validate PRD Workflow

**Goal:** Validate PRDs against PRD Guidelines through a streamlined 4-step workflow.

**Your Role:** Product Analyst (Validator) - you bring systematic quality assessment against PRD Guidelines; the user owns remediation decisions.

---

## WORKFLOW OVERVIEW (4 Steps)

| Step | Name | Purpose | Mode |
|------|------|---------|------|
| 1 | **Init** | Load PRD, discover inputs, init report | Interactive |
| 2 | **Validate** | Structure, format, quality, compliance checks | Auto-proceed |
| 3 | **Assess** | Holistic quality rating and improvements | Auto-proceed |
| 4 | **Complete** | Finalize report, present findings | Interactive |

**Autonomous Execution:** Steps 2-3 run autonomously without user input. Only steps 1 (setup) and 4 (results) require user interaction.

---

## VALIDATION SCOPE

The workflow validates against PRD Guidelines defined in `_prd-data/validation-checks.md`:

### Structure Checks
- Required sections present for project type
- Recommended sections evaluated
- FR IDs are consistent (flexible format)
- Data Entities mapped to FRs (if present)

### Format Checks
- Each FR has: Input, Rules, Output, Error
- Each NFR is single-line with metric/target/condition (if present)

### Quality Checks
- Information density (no filler)
- Measurable success metric
- No implementation leakage
- Traceability (FRs linked, entities linked)

### Compliance Checks
- Domain-specific requirements
- Project-type requirements
- Architecture readiness

---

## OUTPUT

Validation Report with:
- Overall status: Pass / Warning / Critical
- Quality rating: 1-5
- Section-by-section findings
- Architecture readiness score
- Top 3 improvements

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file
- **Just-In-Time Loading**: Only current step file in memory
- **Sequential Enforcement**: Steps completed in order, no skipping
- **State Tracking**: Progress tracked in validation report frontmatter
- **Append-Only Building**: Report built by appending findings

### Execution Rules

1. **READ COMPLETELY**: Always read entire step file before action
2. **FOLLOW SEQUENCE**: Execute all sections in order
3. **AUTO-PROCEED**: Steps 2-3 proceed automatically after completion
4. **WAIT AT BOUNDARIES**: Steps 1 and 4 require user interaction
5. **SAVE STATE**: Update report frontmatter after each step
6. **LOAD NEXT**: Load, read entire file, then execute next step

These principles ensure reliable execution. Deviate only with explicit reasoning documented in conversation:

- Load one step file at a time (keeps context focused)
- Read the entire step file before starting (ensures complete understanding)
- Complete steps in order (dependencies build on each other)
- Update report frontmatter when completing a step (enables continuation)
- Follow step file instructions (they encode best practices)

**When to Deviate:** If the user has a valid reason to skip checks or adjust validation strictness (e.g., validating a prototype), acknowledge the deviation and proceed.

---

## NAVIGATION

**Menu:**
- **[C] Continue** - Proceed to next step
- **[R] Review** - Walk through findings
- **[A] Architecture** - Proceed to /create-architecture (if ready)
- **[E] Edit** - Launch /prd-edit workflow
- **[X] Exit** - Stop workflow

---

## Execution

**Prompt for PRD path:** "Which PRD would you like to validate? Please provide the path."

Then load and execute `./steps-validate-prd/step-01-init.md` to begin.
