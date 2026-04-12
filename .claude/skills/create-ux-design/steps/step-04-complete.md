---
name: 'step-04-complete'
description: 'Define quality requirements, validation strategy, and finalize UX specification'

# File references
outputFile: '{planning_artifacts}/ux-design-specification.md'
---

# Step 4: Complete

**Progress: Step 4 of 4** - Final Step

## STEP GOAL

Define responsive design, accessibility requirements, testing strategy, and finalize the UX specification.

## EXECUTION RULES

- **Interactive step** - requires user confirmation
- You are a UX Facilitator - ensure quality and completeness
- Synthesize all previous work into implementation-ready spec

## SEQUENCE (Follow Exactly)

### 1. Responsive Strategy

#### A. Define Breakpoints

"**Desktop (1024px+):**
- How to use extra space?
- Multi-column layouts?

**Tablet (768-1023px):**
- Simplified or touch-optimized?

**Mobile (320-767px):**
- Bottom nav or hamburger?
- Layout collapse strategy?
- Priority content?"

| Breakpoint | Width | Key Layout Changes |
|------------|-------|-------------------|
| Mobile | 320-767px | [changes] |
| Tablet | 768-1023px | [changes] |
| Desktop | 1024px+ | [changes] |

**Approach:** Mobile-first / Desktop-first

### 2. Accessibility Requirements

#### A. Compliance Level

"**WCAG Level:** [A / AA / AAA]
Recommendation: AA for most products"

#### B. Requirements

**Color & Contrast:**
- Normal text: 4.5:1 minimum
- Large text: 3:1 minimum
- UI components: 3:1 minimum

**Keyboard Navigation:**
- All interactive elements focusable
- Logical tab order
- Visible focus indicators
- Skip links for main content

**Screen Readers:**
- Semantic HTML structure
- ARIA labels for complex components
- Alt text for images
- Meaningful link text

**Touch Targets:**
- Minimum: 44x44px
- Adequate spacing between targets

### 3. Testing Strategy

#### A. Usability Testing Plan

| Test Type | When | Method | Participants |
|-----------|------|--------|--------------|
| Concept validation | Before build | [method] | [count] |
| Prototype testing | Mid-development | [method] | [count] |
| Usability testing | Pre-launch | [method] | [count] |

#### B. Success Metrics

- Task completion rate: [target]
- Time on task: [target]
- Error rate: [target]
- Satisfaction score: [target]

#### C. Quality Checks

**Responsive Testing:**
- Real device testing (phones, tablets)
- Browser coverage (Chrome, Firefox, Safari, Edge)

**Accessibility Testing:**
- Automated tools (axe, WAVE)
- Screen reader testing (VoiceOver, NVDA)
- Keyboard-only navigation
- Color blindness simulation

### 4. Implementation Guidelines

**For Developers:**

Responsive:
- Use relative units (rem, %, vw)
- Mobile-first media queries
- Test touch targets
- Optimize assets per device

Accessibility:
- Semantic HTML first
- ARIA only when needed
- Focus management
- prefers-reduced-motion support

### 5. Update Document

Append quality and validation content to `{outputFile}`:

```markdown
## Quality & Validation

### Responsive Design

#### Responsive Strategy
{responsive_approach}

#### Breakpoints
| Breakpoint | Width | Changes |
|------------|-------|---------|
{breakpoint_table}

### Accessibility

#### Compliance Level
{wcag_level}

#### Requirements
{accessibility_requirements}

### Testing Strategy

#### Usability Testing Plan
{testing_plan}

#### Success Metrics
{success_metrics}

#### Quality Checklist
{quality_checks}

### Implementation Guidelines
{developer_guidelines}
```

Update frontmatter: `stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-03-design-system', 'step-04-complete']`

### 6. Validate Completeness

**Checklist:**
- [ ] Discovery & IA present
- [ ] User journeys diagrammed
- [ ] Core experience defined
- [ ] Design system chosen
- [ ] Visual tokens specified
- [ ] Components and patterns documented
- [ ] Content guidelines defined
- [ ] Responsive strategy set
- [ ] Accessibility requirements defined
- [ ] Testing strategy documented

### 7. Present Final Report

"**UX Design Complete for {{project_name}}!**

**What we accomplished:**
- ✅ Discovery & Information Architecture
- ✅ User Journeys with Diagrams
- ✅ Core Experience Principles
- ✅ Design Foundation & Inspiration
- ✅ Visual System (colors, typography, spacing)
- ✅ Components & UX Patterns
- ✅ Content & Micro-interactions
- ✅ Quality & Validation Strategy

**Deliverable:** `{outputFile}`

**This specification provides:**
- Visual design guidance
- Interaction requirements for developers
- Consistency patterns
- Accessibility standards
- Testing strategy

**Recommended Next Steps:**

**Design Path:**
1. Wireframe generation → detailed layouts
2. Interactive prototype → user testing
3. High-fidelity design → implementation

**Development Path:**
1. `/create-architecture` → technical design
2. `/build-from-prd` → implementation with UX context

What would you like to tackle next?"

---

## SUCCESS CRITERIA

- Responsive strategy defined with breakpoints
- Accessibility requirements documented (WCAG level)
- Testing strategy and success metrics established
- Implementation guidelines provided
- Completeness validated
- User informed about next steps and integrations
- Document finalized with all sections complete
