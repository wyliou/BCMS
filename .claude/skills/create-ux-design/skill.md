---
name: create-ux-design
description: Create comprehensive UX design specifications through collaborative visual exploration
---

# Create UX Design Workflow

**Goal:** Create comprehensive UX specifications optimized for AI-powered implementation through a streamlined 4-step workflow.

**Your Role:** UX facilitator collaborating with a product stakeholder to define visual and interaction design.

---

## WORKFLOW OVERVIEW (4 Steps)

| Step | Name | Purpose | Mode |
|------|------|---------|------|
| 1 | **Init** | Setup, load PRD, detect continuation | Interactive |
| 1b | **Continue** | Resume interrupted workflow (auto-triggered) | Interactive |
| 2 | **Discovery** | Users, IA, journeys, core experience | Interactive |
| 3 | **Design System** | Visual foundation, components, patterns, content | Interactive |
| 4 | **Complete** | Quality, validation, finalization | Interactive |

---

## OUTPUT STRUCTURE

```markdown
# UX Design Specification: {project_name}

## Discovery & Information Architecture
- Project Vision, Target Users
- Information Architecture, Site Map
- Design Challenges & Opportunities

## User Journeys
- Critical Journeys with Mermaid Diagrams
- Journey Patterns, Optimization Notes

## Core Experience
- Defining Interaction, Emotional Goals
- Effortless Interactions, Platform Strategy
- Experience Principles

## Design Foundation
- Inspiring Products Analysis
- Transferable Patterns, Anti-Patterns
- Design System Choice & Rationale

## Visual System
- Color System (tokens, semantic colors)
- Typography System (scale, weights)
- Spacing System (tokens, grid)

## Components & Patterns
- Component Strategy (available + custom)
- Button Hierarchy, Feedback Patterns
- Form Patterns, Navigation Patterns
- Loading & Empty States

## Content & Micro-interactions
- Voice & Tone, Microcopy Guidelines
- Animation Specifications, Transitions
- Motion Principles

## Quality & Validation
- Responsive Strategy, Breakpoints
- Accessibility (WCAG level, requirements)
- Testing Strategy, Implementation Guidelines
```

---

## KEY FEATURES

- **PRD Integration:** Loads existing PRD and brief for context
- **Journey-First:** User journeys inform all design decisions
- **AI-Optimized:** Design tokens and specs in structured format
- **Consolidated Workflow:** 4 focused steps instead of 10 granular ones

---

## WORKFLOW ARCHITECTURE

This uses **step-file architecture** for disciplined execution:

### Core Principles

- **Micro-file Design**: Each step is a self-contained instruction file
- **Just-In-Time Loading**: Only current step file in memory
- **Sequential Enforcement**: Steps completed in order, no skipping
- **State Tracking**: Progress tracked in document frontmatter
- **Collaborative**: Never generate content without user input

### Core Principles

These principles ensure reliable execution. Deviate only with explicit reasoning documented in conversation:

- Load one step file at a time (keeps context focused)
- Read the entire step file before starting (ensures complete understanding)
- Complete steps in order (dependencies build on each other)
- Show content preview before menu (validates output)
- Update frontmatter when completing a step (enables continuation)

**When to Deviate:** If the user has strong design preferences or existing brand guidelines, adapt recommendations accordingly.

---

## NAVIGATION

**Natural Conversation (Preferred):**
Allow user to direct the workflow conversationally:
- "The color system looks great, continue" → Proceed to next section
- "Let's use Material Design instead" → Adjust design system choice
- "Explore accessibility requirements more" → Launch deep dive
- "Get UX designer and developer perspectives" → Launch party mode

**Menu (Fallback for Structure):**
- **[C] Continue** - Save content, proceed to next step
- **[R] Revise** - Make changes before proceeding
- **[D] Deep Dive** - Apply advanced elicitation techniques
- **[P] Party Mode** - Multi-agent perspective gathering

---

## INTEGRATION

UX specifications feed into:
- `/build-from-prd` - Visual design context for implementation
- Solution architecture - UI technology decisions
- Wireframe/prototype generation - Detailed layout work

---

## Execution

Load and execute `./steps/step-01-init.md` to begin.
