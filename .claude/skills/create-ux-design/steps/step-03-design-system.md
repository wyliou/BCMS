---
name: 'step-03-design-system'
description: 'Define visual foundation, components, patterns, and content guidelines'

# File references
nextStepFile: '{skill_base}/steps/step-04-complete.md'
outputFile: '{planning_artifacts}/ux-design-specification.md'
deepDiveSkill: '{skills_root}/_deep-dive/skill.md'
partyModeSkill: '{skills_root}/_party-mode/skill.md'
---

# Step 3: Design System

**Progress: Step 3 of 4** - Next: Complete

## STEP GOAL

Define design foundation, visual system, component strategy, patterns, and content guidelines.

## EXECUTION RULES

- **Interactive step** - requires user collaboration
- You are a UX Facilitator - guide decisions, don't dictate
- Build on emotional goals and experience principles from Step 2

## SEQUENCE (Follow Exactly)

### 1. Design Foundation

#### A. Gather Inspiration

"**Inspiration Questions:**
- Name 2-3 apps your target users love and use frequently
- For each: What do they do well from a UX perspective?
- What makes their experience compelling?"

#### B. Analyze Inspiring Products

For each inspiring app, extract:
- Core problem solved elegantly
- Onboarding approach
- Navigation and hierarchy
- Innovative interactions
- Visual design choices

#### C. Extract Transferable Patterns

"**Transferable Patterns:**
- Navigation: [pattern] → for [your use case]
- Interaction: [pattern] → for [your goal]
- Visual: [pattern] → for [your emotional goal]

**Anti-Patterns to Avoid:**
- [Anti-pattern 1] - why
- [Anti-pattern 2] - why"

#### D. Design System Decision

| Approach | Pros | Cons | Best For |
|----------|------|------|----------|
| **Custom** | Full uniqueness | Higher investment | Established brands |
| **Established** (Material, Ant) | Fast, proven | Less differentiation | Startups, internal tools |
| **Themeable** (MUI, Chakra, Tailwind) | Balance | Moderate learning | Most projects |

"**Based on {{project_name}}:**
- Platform: [from Step 2]
- Brand requirements: [existing guidelines?]
- Team expertise: [design capability]

**Recommendation:** [system] because [rationale]"

### 2. Visual System

#### A. Color System

"Do you have existing brand guidelines or color palette? (y/n)

If yes: I'll extract and map to semantic colors
If no: I'll generate theme options based on emotional goals"

**Color Tokens:**
| Token | Value | Usage |
|-------|-------|-------|
| Primary | [hex] | Main actions, brand |
| Secondary | [hex] | Supporting elements |
| Accent | [hex] | Highlights |
| Background | [hex] | Page background |
| Surface | [hex] | Cards, panels |
| Text | [hex] | Body text |
| Success | [hex] | Positive feedback |
| Warning | [hex] | Caution states |
| Error | [hex] | Error states |

Ensure 4.5:1 contrast minimum for accessibility.

#### B. Typography System

"**Typography Questions:**
- Overall tone: Professional / Friendly / Modern / Classic?
- Content type: Headings only / Long-form reading?
- Brand fonts to use?"

| Element | Font | Size | Weight | Line Height |
|---------|------|------|--------|-------------|
| h1 | [font] | [size] | [weight] | [height] |
| h2 | [font] | [size] | [weight] | [height] |
| h3 | [font] | [size] | [weight] | [height] |
| body | [font] | [size] | [weight] | [height] |
| caption | [font] | [size] | [weight] | [height] |

#### C. Spacing System

"**Layout Questions:**
- Density: Dense/efficient or Airy/spacious?
- Base spacing unit: 4px / 8px?"

| Token | Value | Usage |
|-------|-------|-------|
| xs | [value] | Tight spacing |
| sm | [value] | Related elements |
| md | [value] | Standard gaps |
| lg | [value] | Section spacing |
| xl | [value] | Major sections |

### 3. Components & Patterns

#### A. Component Strategy

"**Available from [Design System]:**
[List available components]

**Required for {{project_name}}:**
[Components needed from journey analysis]

**Gaps (Custom Components Needed):**
- [Gap 1]
- [Gap 2]"

#### B. Button Hierarchy

| Type | Usage | Visual Treatment |
|------|-------|------------------|
| Primary | Main CTA, one per view | [treatment] |
| Secondary | Supporting actions | [treatment] |
| Tertiary | Low-emphasis actions | [treatment] |
| Destructive | Delete, remove | [treatment] |
| Ghost | Minimal emphasis | [treatment] |

#### C. Feedback Patterns

- **Success:** [visual, duration, placement]
- **Error:** [visual, recovery guidance]
- **Warning:** [visual, action required]
- **Info:** [visual, dismissal]
- **Loading:** [visual, messaging]

#### D. Form Patterns

- **Validation:** inline vs. on-submit
- **Error display:** placement, messaging
- **Required fields:** indication method
- **Help text:** when and where
- **Input states:** focus, error, disabled, filled

#### E. Navigation Patterns

- **Primary nav:** [structure, behavior]
- **Secondary nav:** [structure, behavior]
- **Breadcrumbs:** [when to show]
- **Mobile nav:** [pattern]

#### F. State Patterns

**Loading States:**
- Initial load: [treatment]
- Action pending: [treatment]
- Background refresh: [treatment]

**Empty States:**
- First use: [content, CTA]
- No results: [content, suggestions]
- Error state: [content, recovery]

### 4. Content & Micro-interactions

#### A. Voice & Tone

"**Brand Voice:**
- Personality: [3-5 adjectives]
- How we speak: [description]
- How we don't speak: [anti-patterns]

**Tone Variations:**
| Context | Tone | Example |
|---------|------|---------|
| Success | [tone] | [example] |
| Error | [tone] | [example] |
| Onboarding | [tone] | [example] |
| Empty state | [tone] | [example] |"

#### B. Microcopy Patterns

- **Button Labels:** Use action verbs ("Save", "Create"), avoid "Submit", "OK"
- **Error Messages:** What happened + Why + How to fix
- **Empty States:** Explain what will appear + Guide to populate
- **Confirmation:** Confirm what happened + What's next

#### C. Micro-interactions

| Interaction | Animation | Duration | Easing |
|-------------|-----------|----------|--------|
| Button click | [description] | [ms] | [curve] |
| Form submit | [description] | [ms] | [curve] |
| Success | [description] | [ms] | [curve] |
| Error | [description] | [ms] | [curve] |
| Loading | [description] | [ms] | [curve] |

#### D. Motion Principles

1. Purpose: Animation should inform, not decorate
2. Speed: Fast for feedback, slower for emphasis
3. Consistency: Same actions = same animations
4. Accessibility: Respect prefers-reduced-motion

### 5. Update Document

Append all design system content to `{outputFile}`:

```markdown
## Design Foundation

### Inspiring Products Analysis
{inspiration_analysis}

### Transferable Patterns
{patterns_to_adopt}

### Anti-Patterns to Avoid
{patterns_to_avoid}

### Design System Choice
{system_choice}

### Selection Rationale
{selection_rationale}

---

## Visual System

### Color System
| Token | Value | Usage |
|-------|-------|-------|
{color_tokens_table}

### Typography System
| Element | Font | Size | Weight | Line Height |
|---------|------|------|--------|-------------|
{typography_table}

### Spacing System
| Token | Value | Usage |
|-------|-------|-------|
{spacing_table}

---

## Components & Patterns

### Component Strategy

#### Design System Components
{available_components}

#### Custom Components
{custom_component_specs}

### UX Patterns

#### Button Hierarchy
{button_patterns}

#### Feedback Patterns
{feedback_patterns}

#### Form Patterns
{form_patterns}

#### Navigation Patterns
{navigation_patterns}

#### Loading & Empty States
{state_patterns}

---

## Content & Micro-interactions

### Voice & Tone

#### Brand Voice
{voice_description}

#### Tone by Context
| Context | Tone | Example |
|---------|------|---------|
{tone_table}

### Microcopy Guidelines

#### Button Labels
{button_guidelines}

#### Error Messages
{error_message_pattern}

#### Empty States
{empty_state_pattern}

### Micro-interactions

#### Animation Specifications
| Interaction | Animation | Duration | Easing |
|-------------|-----------|----------|--------|
{animation_table}

#### Motion Principles
{motion_guidelines}
```

### 6. Report & Menu

**Report:**
"Design system complete for {{project_name}}.

**Defined:**
- ✅ Design Foundation & Inspiration
- ✅ Visual System (colors, typography, spacing)
- ✅ Components & UX Patterns
- ✅ Content & Micro-interactions

**Design System:** [chosen system]

Ready to finalize with quality validation?"

**Menu:**

**[C] Continue** - Proceed to Complete (Step 4)
**[R] Revise** - Discuss changes to design system
**[D] Deep Dive** - Refine specific area (visual, components, content)
**[P] Party Mode** - Design perspectives on choices

**On [C]:** Update frontmatter (`stepsCompleted` add `'step-03-design-system'`), then load and execute `{nextStepFile}`.

---

## SUCCESS CRITERIA

- Design inspiration analyzed with transferable patterns
- Design system chosen with rationale
- Visual tokens defined (color, typography, spacing)
- Component strategy documented
- UX patterns specified (buttons, feedback, forms, nav, states)
- Voice, tone, and microcopy guidelines defined
- Micro-interaction specifications complete
- User confirmed before proceeding
