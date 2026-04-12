---
name: 'step-03-journeys'
description: 'Journeys/workflows and capability mapping'

# File references
nextStepFile: '{skill_base}/steps-create-prd/step-04-requirements.md'
validationChecks: '{skills_root}/_prd-data/validation-checks.md'
---

# Step 3: Journeys & Capability Mapping

**Progress: Step 3 of 6** - Next: Requirements

## STEP GOAL

Document journeys/workflows for each actor type and build the capability mapping. This creates the foundation for FR generation in step 4.

## EXECUTION RULES

- Journeys and capability areas require user confirmation before writing

## SEQUENCE (Follow Exactly)

### 1. Check Section Applicability

Read the PRD document from the frontmatter `outputPath` to load Section 1 (product category, actors, scope items, brownfield context). This ensures the agent has current context even on continuation or after a long step-02 conversation.

Read the product category from Section 1 Classification. Refer to the `{validationChecks}` Section Requirements table to determine if Section 2 is Recommended or Optional for this project type (Section 2 is never Required).

**If Recommended:** "Section 2 (Journeys) is recommended for {category} projects. Proceeding with journey creation — let me know if you'd prefer to skip."
**If Optional:** Ask the user: "Section 2 (Journeys) is optional for {category} projects. Include it? [Y/N]"

If skipped, note "Section 2: Not applicable for {category}" in the PRD and proceed directly to Capability Mapping (section 3 below).

### 2. Journeys/Workflows

For each actor type identified in Section 1, propose a draft journey based on the vision and scope, then ask the user to confirm or refine. Work through one actor type at a time.

**Journey step format:** Write each journey as a numbered list under the heading `### {Actor Type}: {Journey/Workflow Name}`. Each step should be a concise action sentence (e.g., "1. User enters credentials on login page"). This format ensures step-04 can map individual journey steps to FRs.

**Adapt Section 2 format to product category:**

| Product Category | Section 2 Format |
|-----------------|------------------|
| Web App / Mobile / Desktop | **User Journeys** — 3-5 step flows per actor type |
| API Service | **API Consumer Journeys** — request/response flows, briefer |
| CLI Tool | **Command Workflows** — command sequences with expected outputs |
| Library/SDK | **Integration Scenarios** — code usage patterns showing typical integration |
| Data Pipeline | **Data Workflows** — data flow from source to destination per pipeline |
| ML Model/Service | **Training/Inference Workflows** — model lifecycle flows |
| Infrastructure/IaC | **Operational Workflows** — provisioning, scaling, recovery flows |
| Microservices System | **Service Interaction Flows** — cross-service request flows |
| Plugin/Extension | **Extension Scenarios** — plugin lifecycle and interaction patterns |
| Full Stack App | **User Journeys** — end-to-end flows spanning frontend and backend |
| Prototype/MVP | **User Journeys** — simplified, 2-3 steps |

**Journey Validation:**
- At least 1 journey per actor type
- 3-5 steps each (2-3 for prototypes)
- Brownfield projects: must include a migration/transition journey if legacy data or users exist. Assign it to the actor most responsible for migration (often Admin or System). If no existing actor fits, propose a new actor type to the user.

**If validation fails:** Ask targeted questions to fill gaps.

### 3. Capability Mapping

Build the capability area mapping from scope items and journey steps:

1. **Check Section 3 headers** in the PRD for existing `### Area` headers. Ignore any headers containing `{{...}}` template placeholders — these are from the template, not from a previous session.
   - If real (non-placeholder) headers present: use as starting point (already user-approved from a previous session)
   - If absent or only placeholders: derive from scope items + journey steps

2. **Build coverage map** — verify every scope item maps to at least one capability area. If unmapped scope items exist, propose new capability areas to cover them and ask the user to confirm. (Brownfield-specific areas from point 3 below are derived from brownfield context, not scope items — they do not need a scope item mapping.)

3. **Brownfield-Specific Capability Areas:** Brownfield context discovered in step 2 is stored in Section 1 under `### Brownfield Context` (per the template). Reference this section when adding brownfield-specific capability areas below and when informing tech constraints in step 5.

   If brownfield project detected in Section 1, ask the user which of these apply (one at a time):
   - **Data Migration** — "Do you need to migrate legacy data to the new system?"
   - **Legacy Compatibility** — "Do you need to maintain interfaces with systems not yet replaced?"
   - **Transition Management** — "Do you need a managed cutover period?"
   Add only the areas the user confirms.

### 4. Write to Document

After gathering all information, write to the PRD:

1. **Write Section 2** (Journeys/Workflows) — or note "Not applicable for {category}" if skipped. Replace any template placeholder content in Section 2.
2. **Write capability area headers into Section 3** as `### Area Name` headers. Remove all template placeholder content from Section 3 (any `{{...}}` headers and their placeholder FR content). On continuation, merge new areas with pre-existing real headers — do not duplicate.

Section 3 will contain headers only at this point — FRs are generated in step 4. This is the expected intermediate state.

### 5. Report & Menu

**Report:**
- Journeys gathered (count by actor type)
- Capability areas mapped
- Coverage summary (scope items → capability areas)

**Menu:**

**[C] Continue** - Proceed to FR Generation (Step 4)
**[R] Revise** - Modify journeys or capability areas

**On [R]:** Make requested changes. If a journey is added for a new actor type, propose new capability areas if needed. If a journey is removed, re-evaluate whether its derived capability areas still have coverage from other journeys or scope items — remove orphaned areas with user approval. After any revision, re-verify the scope → capability area coverage map before returning to menu.
