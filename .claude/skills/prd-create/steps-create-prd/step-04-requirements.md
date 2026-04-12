---
name: 'step-04-requirements'
description: 'FR generation, completeness verification, and deepening'

# File references
nextStepFile: '{skill_base}/steps-create-prd/step-05-specifications.md'
prdPurpose: '{skills_root}/_prd-data/prd-purpose.md'
---

# Step 4: Functional Requirements

**Progress: Step 4 of 6** - Next: Specifications

## STEP GOAL

Generate Functional Requirements from the capability mapping established in step 3, verify completeness, and deepen each FR through focused Q&A.

## EXECUTION RULES

- Apply FR Quality Criteria from prd-purpose.md during generation: explicit actor, constrained inputs, business-logic-only rules, testable output, exhaustive errors, boundary conditions, state transitions, data flow direction. If FR Quality Criteria are not in context, reload from `{prdPurpose}`.
- This step handles FRs only — do NOT generate NFRs, Data Entities, or Tech Constraints here

## SEQUENCE (Follow Exactly)

### 1. Generate Functional Requirements

Read the PRD document from the frontmatter `outputPath` to load Section 1 (actors, scope items, classification) and Section 3 (capability area headers from step 3). For brownfield projects, also note the Brownfield Context sub-section — it informs brownfield-specific capability areas.

For each capability area from Section 3's `### Area` headers:

#### FR Format
```markdown
### {Capability Area Name}

**FR-001**: [Actor] [capability]
- **Input:** field1 (type, format constraint, validation rule), field2 (type, constraints)
- **Rules:** IF condition THEN action; ELSE alternative. Express as business logic, not implementation.
- **Output:** Observable result. What changes in system state? What does the actor see?
- **Error:** trigger condition → handling; second condition → handling. Be exhaustive.
- **Depends:** FR-xxx (if any)
```

FRs are grouped under `### Capability Area Name` section headers. The header carries the domain context — IDs are sequential (`FR-001`, `FR-002`, ...).

**For large projects (15+ FRs):** Area-based IDs (`FR-AUTH-001`) are acceptable if the user prefers them. The capability area is still in the section header regardless of ID format.

Match detail depth to project context from Section 1 Classification — enterprise gets exhaustive detail, prototypes get essentials only. The Input/Rules/Output/Error **format** is always used; what changes is the **depth** within each field.

**Brownfield-specific capability areas** (Data Migration, Legacy Compatibility, Transition Management): These often involve one-time batch operations rather than ongoing functionality. Probe for: data volume/batch sizing, rollback strategy, validation and reconciliation rules, cutover sequencing.

### 2. Coverage Verification & Draft Presentation

After generating FRs, verify completeness before presenting to the user:

1. **Run all three coverage checks:**
   - **Scope → FRs:** Every in-scope item (Section 1) maps to ≥1 FR
   - **Journeys → FRs:** Every journey step (Section 2) maps to ≥1 FR
   - **Actors → FRs:** Every actor (Section 1) appears in ≥1 FR

   Skip Journeys check if Section 2 was marked not applicable or contains no journey steps. Skip Actors check if single actor.

2. **If gaps exist:** Generate additional FRs to close them.

3. **Present the complete FR set** grouped by capability area, with coverage summary:
   **"X FRs across Y areas. Coverage: scope {n}/{n}, journeys {n}/{n}, actors {n}/{n}."**

4. **After user review:** Re-verify zero gaps remain. If the user's changes introduced new gaps, repeat from step 1.

### 2b. Granularity Check

Before deepening, review each FR for single-responsibility:
- Does the FR contain two distinct algorithms or processes?
- Could the FR's Input/Rules be split into independent operations?
- Would an implementing agent naturally build this as two separate functions?

**Quantitative splitting signals** — recommend a split when any of these apply:
- **Rules section exceeds 5 bullet points** — likely covering multiple behaviors
- **FR touches 3+ distinct data fields or entities being processed** — scope is too broad for one FR
- **FR covers both detection/identification AND extraction/processing** — these are naturally separate operations (e.g., "detect table regions and extract cell values" should be two FRs)

If any FR does double duty (by heuristic or quantitative signal), recommend splitting and get user approval BEFORE deepening begins. Splitting after deepening wastes work.

**Splitting convention:** When splitting FR-NNN, keep the first half as FR-NNN (updating its scope) and assign the second half the next sequential ID. Update any `Depends:` references that pointed to the original FR to reference whichever half now owns the depended-upon behavior.

### 2c. Real Data Examination (Data-Processing Projects)

**Applicability:** This section is mandatory when the project processes external files or variable-format input. Detect from:
- **Product category:** CLI Tool, Data Pipeline, ML Model/Service, API Service with file ingestion
- **FR content:** FRs that parse, extract, transform, or validate external data

When not applicable (e.g., web app, library, internal API without file processing), skip this section entirely.

**Process:**
1. Ask the user to identify input files, data sources, or sample data available for examination
2. **Adaptive sampling** — scale examination breadth to corpus variability:
   - Small corpus (≤5 files) or uniform format: examine all or most
   - Medium corpus (6-20 files): examine 4-6 files spanning known format clusters
   - Large corpus (>20 files): examine 6-10 files, biased toward variety. Ask the user: "Which files have the most unusual or different formats?" and prioritize those
3. For each file, systematically document:
   - **Structural patterns:** header layout, row organization, section boundaries, stop markers
   - **Cell merging:** horizontal merges (adjacent columns merged), vertical merges (same column spanning rows), and their semantics after unmerging (value propagation vs. empty artifacts)
   - **Data representation variants:** same field appearing in different forms across files (e.g., empty = missing vs. empty = continuation vs. empty = merged artifact; ditto marks; encoded values in unexpected columns)
   - **Encoding and platform:** character sets, special characters, platform-specific I/O considerations
   - **Edge cases:** empty fields, optional sections, unexpected delimiters, numeric precision differences
4. Summarize findings as a **Data Variation Catalog** — a structured list of observed patterns grouped by category. Present to user: "I examined {N} files. Here are the patterns I found: {catalog}. Any patterns I missed?"
5. Use findings to:
   - Inform deepening questions in section 3 (ask about real patterns, not hypotheticals)
   - Generate additional FRs if new behaviors are discovered
   - Seed the **Test Corpus Notes** sub-section for Section 7 (see step 5 changes)
   - Identify cross-FR consistency requirements (when two FRs read the same field, both must handle all observed variants)

If new FRs are generated, apply the same coverage checks from section 2 and get user approval before proceeding to deepening.

### 3. FR Deepening Pass

After the user approves the draft (including any granularity splits), **deepen each FR one at a time** through focused Q&A. This is where FRs gain the precision needed for AI-agent implementation.

#### Deepening Scope Selection

Present the user with scope options to manage conversation length:

"Now I can deepen each FR with targeted questions to improve implementation precision. This typically takes 1-3 exchanges per FR.

**Deepening strategy:**
**[All]** Deepen every FR (~{FR count × 2} exchanges)
**[Area]** Select capability areas to deepen (e.g., "Authentication and Data Processing")
**[Skip]** Skip deepening, proceed to writing

You can say **'skip remaining'** at any point during deepening to stop early and proceed to writing with FRs deepened so far."

If user selects [Area]: Present the capability area list with FR counts per area. User selects one or more areas. Deepen only FRs under those area headers. Remaining FRs keep their draft state.

If user selects [All] and FR count > 15: Warn "This will take 30+ exchanges. Consider [Area] for a focused pass. Continue with All? [Y/N]"

#### Deepening Process

Process FRs in capability area order, and within each area, in ID order. If FR-B depends on FR-A, deepen FR-A first regardless of ID order — answers about a dependency often clarify its dependents.

##### Complexity Tier Assessment

Before deepening each FR, assess its complexity tier to calibrate depth:

| Tier | FR Nature | Deepening Approach |
|------|-----------|-------------------|
| **Standard** | CRUD operations, validation, configuration, logging, simple state transitions | 1-2 exchanges — confirm key rules, move on |
| **Data-processing** | Parses external input, handles format variability, transforms or extracts data | Multi-round — probe for input variations, edge cases, precision rules, format-specific handling |
| **Algorithm** | Calculations, allocation logic, matching/scoring, multi-step processing | Multi-round — probe for exact steps, precision/rounding, boundary conditions, failure modes |

Tier is assessed from the FR's nature, not a fixed count. State the assessed tier when beginning each FR so the user knows the expected depth (e.g., *"FR-005 is data-processing tier — I'll ask about input variations and edge cases."*).

##### Per-FR Deepening

For each FR in the selected scope:
1. Assess the complexity tier (Standard, Data-processing, or Algorithm)
2. Identify the most important gap or ambiguity
3. Ask **one question** about that gap
4. Wait for the user's answer
5. **Standard tier:** If the answer resolves the key gap, move on. One follow-up at most.
6. **Data-processing tier:** After initial answer, probe specifically for:
   - Input variations (format differences, optional fields, encoding)
   - Edge cases discovered during real data examination (section 2c)
   - Precision rules for extraction or transformation
   - Continue until input space is adequately covered
7. **Algorithm tier:** After initial answer, probe specifically for:
   - Exact calculation steps or formula
   - Precision and rounding method
   - Boundary conditions (zero, negative, overflow, empty)
   - Failure modes and fallback behavior
   - Continue until the algorithm is reproducible from the FR alone
8. When the FR is sufficiently specified for its tier, move to the next FR

**Real data grounding:** For Data-processing and Algorithm tier FRs, reference specific patterns from the real data examination (section 2c) in your questions. Ask about real patterns observed, not hypothetical scenarios.

**Efficient absorption:** If the user provides comprehensive detail that fully addresses the FR's gaps, acknowledge it, confirm understanding, and move to the next FR. Do not ask additional questions just to fill an expected exchange count.

**Early exit:** If the user says "skip remaining" (or equivalent), stop deepening immediately. FRs already deepened keep their enriched state; remaining FRs keep their draft state. Proceed to Write to Document.

#### Failure-Mode Probing

After the constructive deepening pass, run a dedicated failure-mode pass **per capability area** (not per-FR — this avoids question fatigue while still covering the full surface).

For each capability area that contains Data-processing or Algorithm tier FRs, ask **one question** covering:
- "What are the most common failure modes or edge cases you've seen with real data in {area}?"
- "What causes the most manual rework today in {area}?"
- "What assumptions about input format or data quality have broken in the past?"

Pick the most relevant question for the area. Wait for the user's answer before moving to the next area.

**Processing findings:**
- If the answer reveals a missing error case → add it to the relevant FR's Error field
- If the answer reveals a new behavior or handling requirement → create a new FR (apply coverage checks)
- If the answer reveals an edge case → add it to FR Rules or capture as Section 7 Examples & Edge Cases
- If the answer is "nothing comes to mind" → move on, do not press further

For areas containing only Standard tier FRs, skip failure-mode probing for that area.

**Cross-FR field consistency:** After failure-mode probing, identify fields or data structures that are produced by one FR and consumed by another (e.g., extracted values fed into validation or allocation). For each such handoff, verify that the producer and consumer agree on:
- Data representation (same precision, same handling of empty/null/zero)
- Edge case semantics (what does empty mean — missing data, continuation, merged artifact?)
- Error propagation (if producer marks a value as provisional, does consumer know?)

If inconsistencies are found, add explicit rules to the relevant FRs or note them in Section 7. This prevents cross-module bugs that only surface during integration testing.

#### Section 7 Discovery Capture

During deepening, the user's answers often reveal implementation-level detail that belongs in Section 7 (Implementation Reference) rather than in the FR body. Capture these proactively.

##### What stays in the FR vs. goes to Section 7

| Stays in FR (Rules/Error) | Goes to Section 7 |
|---------------------------|-------------------|
| Business logic conditions (IF/THEN/ELSE) | Multi-step algorithms or calculation formulas |
| Input validation constraints (min/max, format) | Configuration file schemas (YAML/JSON structure with defaults) |
| Error trigger → handling (one-liner) | Error/status code catalogs (full code lists with meanings) |
| State transitions (status A → B) | Output format specifications (exact templates, field layouts) |
| Data flow direction (who sends what) | Concrete input/output examples showing edge cases |

**Rule of thumb:** If the detail defines *what* the system does, it stays in the FR. If it defines *how precisely* to do it (exact algorithm, exact format, exact codes), it goes to Section 7 with a cross-reference from the FR.

##### Capture categories

Match the 5 sub-sections from prd-purpose.md:

```markdown
## _Section 7 Notes (Temporary)

### Configuration Schema
- **{topic} ({FR-ID}):** {schema details, types, defaults, valid ranges}

### Output Formats
- **{topic} ({FR-ID}):** {exact format template or structure}

### Error/Status Code Catalog
- **{code} ({FR-ID}):** {meaning, trigger condition}

### Algorithm Details
- **{topic} ({FR-ID}):** {ordered steps, formula, processing logic}

### Examples & Edge Cases
- **{topic} ({FR-ID}):** {input → expected output, boundary cases}
```

##### Proactive discovery

Don't wait for the user to volunteer implementation detail. During deepening, probe for Section 7 content when you detect these signals:

| Signal in FR | Probe for |
|-------------|-----------|
| Rules mention a calculation or formula | Algorithm Details — ask for exact steps |
| FR involves user-editable settings | Configuration Schema — ask for fields, types, defaults |
| Error field lists coded errors (ERR_xxx) | Error Code Catalog — ask for the full code list |
| Output describes structured data | Output Formats — ask for exact field layout |
| Rules have complex branching logic | Examples & Edge Cases — ask for concrete scenarios |
| FR processes external files with variable format | Algorithm Details + Examples — probe for format variations, encoding, structural edge cases |
| FR involves numeric calculations on external data | Algorithm Details — probe for precision rules, rounding method, floating-point handling |
| FR extracts data from structured documents | Algorithm Details + Examples — probe for multi-row structures, merged regions, embedded values |
| FR describes a multi-step processing pipeline | Algorithm Details — probe for exact processing order and constraints between steps |

**Domain-aware probing:** For projects with defined processing pipelines (data extraction, transformation, validation), proactively ask about exact algorithms, processing orders, and precision rules — don't wait for the user to mention them. These details are critical for AI-agent implementation and are frequently omitted in initial answers.

When captured, add a cross-reference in the FR: `See Section 7: {topic}` in the relevant field.

Step 5 consumes and replaces this temporary section with the final Section 7. Do not write Section 7 proper yet.

### 3b. Post-Deepening Granularity Re-Check

After deepening, re-evaluate FRs that grew significantly. For each FR where deepening added substantial new rules (2+ new bullet points in Rules, or new sub-behaviors like fallback handling, continuation logic, or multi-strategy detection):

1. Re-apply the quantitative splitting signals from section 2b
2. If an FR now exceeds the thresholds, recommend splitting to the user
3. Apply the same splitting convention (keep first half as FR-NNN, second half gets next sequential ID)

This catch prevents single FRs from becoming implementation-blocking monoliths. Skip if no FRs grew significantly during deepening.

### 4. Write to Document

**Now write all gathered content to the PRD at once:**
1. Write Section 3 (Functional Requirements) with all deepened FRs
2. If any Section 7 notes were captured during deepening, write `_Section 7 Notes (Temporary)` after the last populated section in the PRD

This batch write ensures Section 3 is never left in a partial state and Section 7 discovery notes are preserved for step 5.

### 5. Report & Menu

Show the user:
1. Summary: "Generated X FRs across Y capability areas"
2. Coverage summary (gaps or complete)
3. Key dependencies identified
4. Any assumptions made

**Menu:**

**[C] Continue** - Proceed to Specifications (Step 5)
**[R] Revise** - Modify requirements

**On [R]:** Make requested changes. New FRs get the next sequential ID (never insert in the middle). If deleting a FR, update its dependents. Re-verify coverage after changes, return to menu.
