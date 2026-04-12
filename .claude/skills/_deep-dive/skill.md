---
name: _deep-dive
description: Apply advanced elicitation methods iteratively to enhance specific content using a repository of 50 specialized techniques.
---

# Deep Dive Skill

**Goal:** Enhance content using specialized elicitation methods (personas, creative techniques, rigorous analysis).

**Your Role:** Methods facilitator - analyze context, recommend techniques, execute rigorously, track insights for return.

---

## INPUT/OUTPUT CONTRACT

**When Invoked by Another Skill:**
- Input: `content` (what to enhance), `focus_area` (optional), `content_type` (optional)
- Output: `enhanced_content`, `insights`, `methods_applied`, `changes_made`

**Standalone Mode:** Operate on current conversation context or ask user for content.

---

## WORKFLOW

### 1. Initialize

1. **Detect Mode:** Check if invoked with context from another skill (embedded) or directly (standalone)
2. **Load Methods:** Read `./methods.csv` - fail gracefully if missing
3. **Analyze Context:** Match content signals to method categories:

| Content Type | Recommended Categories |
|--------------|----------------------|
| Requirements, specs | `core`, `risk`, `technical` |
| Vision, strategy | `creative`, `collaboration` |
| Architecture, design | `technical`, `advanced`, `competitive` |
| User research | `collaboration`, `research` |
| Edge cases, errors | `risk`, `competitive` |
| Business rules | `core`, `advanced`, `risk` |

4. **Select 5 Methods:** 3 from recommended categories, 2 from others

### 2. Interaction Loop

**Natural Conversation (Preferred):**
Allow user to direct the session conversationally:
- "Try the pre-mortem analysis" → Execute that method
- "What methods would help with security?" → Recommend relevant methods
- "I think we're done" → Proceed to completion
- "Show me what we've found" → Present insights summary

**Menu (Fallback for Structure):**
If user prefers structured navigation, present:
```
Deep Dive: {focus_area}

Recommended Methods:
1. {Method} - {benefit}
2. {Method} - {benefit}
3. {Method} - {benefit}
4. {Method} - {benefit}
5. {Method} - {benefit}

[1-5] Apply method | [R] Reshuffle | [A] All methods | [S] Summary | [X] Exit
```

**Handle Input:**

- **Method request:** Execute method → Show results → Ask if they want to apply → Track insight
- **[1-5] or number:** Execute that method → Show results → Ask "Apply? [Y/N/M]" → Track insight
- **[R] or "show different methods":** Select 5 new methods (exclude used)
- **[A] or "show all methods":** Show all methods by category → Allow selection
- **[S] or "summary":** Show insights gathered so far
- **[X] or "done/exit/finish":** Proceed to completion

**Method Execution:**
1. Follow the method's `description` and `output_pattern` from CSV
2. Be creative but rigorous
3. Present: Results → Key Insight → Proposed Enhancement
4. On **Y**: Update content, record change
5. On **N**: Record insight only (not applied)
6. On **M**: Discuss modification, then apply

### 3. Complete

**Compile Output:**
- `enhanced_content`: Modified content (or original if no changes)
- `insights`: All discoveries (mark applied vs. considered)
- `methods_applied`: List of methods used
- `changes_made`: Specific modifications

**Present Summary:**
```
Deep Dive Complete

Methods Applied: {count}
Key Insights: {bulleted list}
Changes Made: {list}

Enhanced Content:
{show content}
```

**Return:**
- Embedded mode: Return output data to calling skill
- Standalone mode: Offer [N] New focus or [X] Exit

---

## METHOD EXECUTION TIPS

| Category | Approach |
|----------|----------|
| Collaboration | Create distinct personas, have them interact, synthesize |
| Advanced | Show reasoning paths explicitly, explain selection |
| Competitive | Be genuinely adversarial, find real weaknesses |
| Technical | Precise language, implementable recommendations |
| Risk | Think pessimistically, specific mitigations |

---

## SUCCESS CRITERIA

- Mode detected correctly
- Methods matched to context
- User can accept/reject each enhancement
- All insights tracked (applied and not applied)
- Clean return to caller with structured output
