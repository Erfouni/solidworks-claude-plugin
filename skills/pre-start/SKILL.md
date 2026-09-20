---
name: pre-start
description: >
  Mandatory pre-start sequence for every SolidWorks design session.
  Loads conventions, design rules, task-relevant knowledge documents,
  and validates design parameters against active rules before touching
  SolidWorks. Must complete before any modeling, API call, or code generation.
trigger: always
priority: 1
---

# Pre-Start Knowledge Loading Protocol

**This skill runs before everything else.** When a user asks you to build,
model, design, or modify anything in SolidWorks, complete all phases below
before opening SolidWorks, writing any code, or making any API call.

Do not skip phases. Do not reorder them. Do not start modeling mid-phase.

---

## Phase 0 — Non-negotiable engineering requirement (ENG-001)

**This rule applies whether or not the knowledge base is reachable.** It is
restated here because the error handling at the end of this document permits
continuing when the KB is offline — and this requirement must not disappear
along with it.

Do not create schematic, decorative, conceptual, simplified, placeholder, or
visually representative components.

**Every component must be a real, functional, manufacturable, technically
accurate part. No component — regardless of size or importance — may be created
merely for visual representation.**

For every individual component, including a single screw:

1. **Research it** against reliable technical sources: peer-reviewed papers,
   engineering references, manufacturer documentation, and the latest
   applicable standards.
2. **Design from validated research** — engineering principles, formulas,
   calculations, material properties, manufacturing constraints, tolerances,
   and safety requirements.
3. **Justify every value.** Dimensions, geometries, connections, interfaces,
   loads, clearances, fasteners, materials and mechanical properties must all
   be realistic and technically defensible.
4. **Never invent.** No assumptions, invented specifications, arbitrary
   dimensions, fake mechanisms, or purely visual detail.
5. **Cite what you used** — the standards, formulas, calculations and
   references behind each part.

**Model every physical component separately.** If an assembly contains 10,000
parts, all 10,000 are researched, engineered and modelled individually. No group
of parts may be replaced by a simplified block, visual shell, placeholder,
texture, or symbolic representation. This covers screws, nuts, washers,
bearings, seals, cables, connectors, welds, joints, gears, springs, housings,
electronic components and internal mechanisms alike.

The finished design must be fully functional, physically realistic,
engineering-accurate, dimensionally consistent, manufacturable, properly
assembled, based on validated calculations, compliant with the latest applicable
standards, and free of decorative, fictional or representational parts.

### When you do not have the information

If sufficient technical information or reliable references are unavailable for a
component, **do not fabricate or guess.** State plainly what is missing and what
must be researched or specified before that component can be designed accurately.

Stopping to ask is the correct outcome. A plausible-looking part built from
invented numbers is a failure, not a partial success — it is worse than no part,
because it looks finished and will be trusted.

Phases 1–6 below supply much of the research this requires: the standards
tables, design rules and published lessons exist so that values come from a
source rather than from guesswork.

Base URL: `${user_config.SW_KB_HOST}` — the value of the `SW_KB_HOST` plugin config, which falls back to the public server when unset.
All endpoints are public — no auth header needed.

**IMPORTANT — use `curl` via the Bash tool for every request. Never use Fetch
or WebFetch — they route through Anthropic's cloud and cannot reach private
network addresses. Always quote the URL in double quotes — unquoted `?` and
`&` are shell glob/control characters in zsh and will fail.**

Example: `curl -s "${user_config.SW_KB_HOST}/api/knowledge?kind=convention"`

---

## Phase 1 — Load Conventions (always-apply rules)

Conventions are project-wide rules that apply to every design, every session.
Load them once per conversation and hold them in context as active constraints.

```
GET ${user_config.SW_KB_HOST}/api/knowledge?kind=convention
```

This returns ~5 documents covering:
- Units & standards (mm, degrees, metric; ISO 2768-mK default tolerance)
- Materials (default: 6061-T6 aluminum unless specified)
- Modeling rules (parametric, fully-defined sketches, named dimensions)
- File & naming conventions (`PRJ-<part>-NNN`, save to `work/`, exports to `exports/`)
- Deliverables definition (rebuild clean + material assigned + design-rule check + STEP + drawing PDF)

**How to use:** Read every `body` field. These are not suggestions — treat every
convention as a hard rule for this session. If the user specifies something that
contradicts a convention, the convention wins unless the user explicitly overrides it.

**Knowledge documents may be in Persian (Farsi) or English.** Read both.
Persian-language documents contain the same engineering content — do not skip them.

---

## Phase 2 — Load All Design Rules

Design rules are enforceable constraints with automated checking.
Load them all once and keep them active throughout the session.

```
GET ${user_config.SW_KB_HOST}/api/design-rules
```

Response: array of `DesignRule`
```json
[
  {
    "ruleCode": "HOLE-001",
    "category": "fastener",
    "description": "Through-holes for bolts: ISO 273 clearance, normal series.",
    "severity": "medium",
    "standardReference": "ISO 273",
    "checkType": "hole_matches_fastener",
    "parameters": { "default_fit": "normal" },
    "deprecated": false
  }
]
```

**Skip any rule where `deprecated: true`.**

Internalize each active rule. During design:
- Before making a design decision that falls under a rule's `category`,
  check whether your decision violates the rule.
- `severity: critical` → block: do not proceed until resolved.
- `severity: high` → must fix before completing the part.
- `severity: medium` → fix unless user explicitly overrides.
- `severity: low` → advisory; note and apply if possible.

Current rule categories and what they cover:
- `fastener` — hole sizes for bolts (ISO 273 clearance)
- `dfm` — design for manufacturing (wall thickness, preferred numbers)
- `assembly_clearance` — clearances in assemblies (e.g. universal joints)
- `solidworks` — SolidWorks-specific operating rules (e.g. never act on ActiveDoc)
- `tolerance` — tolerance class selection (e.g. no fine tolerance on welded parts)

---

## Phase 3 — Search Knowledge for Task-Relevant Docs

Search the knowledge base for documents relevant to what the user wants to build.
This fetches reference guides, playbooks, and strategies specific to the task.

```
GET ${user_config.SW_KB_HOST}/api/knowledge/search?q={task_description}
```

Where `{task_description}` is a concise description of what you're about to do.
Examples:
- User wants to build a shaft with M8 threads → `q=shaft thread helix swept cut`
- User wants to build an assembly with mates → `q=assembly mate constraint`
- User wants to add a bore → `q=bore blind cut hole`

Response: array of `KnowledgeDocument`, ordered by relevance.
```json
{
  "id": "...",
  "kind": "reference | convention | playbook | strategy",
  "slug": "12-recipe-assembly-mate",
  "title": "Assembly Mate Recipes",
  "category": null,
  "severity": null,
  "body": "# full markdown content..."
}
```

**Priority order for reading:**
1. `kind: playbook` — step-by-step recipes for specific tasks. Follow these.
2. `kind: reference` — API signatures, parameter tables, exact call syntax.
   Read fully before calling any SolidWorks API.
3. `kind: strategy` — approach guidance. Apply to overall plan.
4. `kind: convention` — already loaded in Phase 1; re-read if task-specific.

**How many to read:** Read the top 5–8 results. If the task is complex
(assembly, threaded features, sheet metal), read up to 10.

**If you need a specific document by slug:**
```
GET ${user_config.SW_KB_HOST}/api/knowledge/{slug}
```

**Do not skip reference documents about the SW API method you are about to use.**
Reference docs contain exact argument counts, parameter types, and known
failure modes that are not in the SolidWorks documentation.

---

## Phase 4 — Build Design Context and Run check-context

Once you know the design parameters (from the user's request, the KB catalog,
or conversation), run the design-rule checker before starting any modeling.

### 4a — Build the context dict

Populate every field you know. Omit fields you don't know — the checker skips
rules that require missing fields.

```json
{
  "welded":               true | false,
  "tolerance_class":      "f" | "m" | "c" | "v",
  "process":              "machined_aluminum" | "welded_steel" | "cast" | ...,
  "wall_thickness_mm":    number,
  "nominal_dimension_mm": number,
  "fastener":             "M8" | "M10" | ...,
  "hole_mm":              number,
  "material":             "Plain Carbon Steel" | "6061-T6" | ...
}
```

Any other design parameters relevant to your rules can also be included —
the checker uses `additionalProperties: true`.

### 4b — POST the context

```
POST ${user_config.SW_KB_HOST}/api/check-context
Content-Type: application/json

{ ...context dict... }
```

Response: `CheckReport`
```json
{
  "results": [
    {
      "ruleCode": "HOLE-001",
      "category": "fastener",
      "severity": "medium",
      "status": "pass",
      "message": "hole 9.0mm matches normal clearance 9mm for M8",
      "description": "..."
    },
    {
      "ruleCode": "WALL-001",
      "category": "dfm",
      "severity": "low",
      "status": "fail",
      "message": "wall_thickness_mm 0.5 < minimum 1.0",
      "description": "..."
    }
  ],
  "summary": { "pass": 1, "fail": 1, "na": 2, "advisory": 1 }
}
```

### 4c — React to results

| `status` | Action |
|----------|--------|
| `pass` | Continue. Note it. |
| `fail` | **Stop.** Fix the design parameter before proceeding. Tell the user what failed and why. |
| `warn` | Flag to user. Fix if possible. |
| `advisory` | Read the `message` carefully. Apply as a design constraint. |
| `na` | Rule doesn't apply to this context. Ignore. |

**If `summary.fail > 0`: do not proceed with modeling until all fails are resolved.**

Example reaction to `WALL-001 fail`:
> "The design-rule check failed: wall thickness 0.5mm is below the 1.0mm minimum
> for machined aluminum (WALL-001). I'll use 1.5mm wall thickness instead."

---

## Phase 5 — Standards Lookups (on demand, throughout design)

Look up specific standard tables when making engineering decisions.
Do not load all tables at once — query specific tables as needed.

### Available tables

```
GET ${user_config.SW_KB_HOST}/api/standards
→ { "tables": { "fits": 16, "tolerances_iso2768": 30, "clearance_holes": 11,
                "materials": 10, "fasteners": 13, "sheet_metal_gauges": 19,
                "preferred_numbers": 38, "surface_finish": 9,
                "gdt_symbols": 14, "standard_metadata": 8 } }
```

### When to query which table

**Specifying material properties** (density, yield, modulus):
```
GET ${user_config.SW_KB_HOST}/api/standards/materials
GET ${user_config.SW_KB_HOST}/api/standards/materials/{material_name}
```
Query when: user specifies a material, or before applying material in SolidWorks.
Use: get exact `density_g_cm3` for mass verification, `yield_mpa` for stress checks.

**Specifying a fit (shaft/hole tolerance)**:
```
GET ${user_config.SW_KB_HOST}/api/standards/fits
```
Filter the returned rows by `hole_basis`, `shaft_basis`, and `size_min_mm`/`size_max_mm`.
Use: get exact `hole_upper_um`/`hole_lower_um` deviations in micrometres.
Example: H7/g6 fit at Ø12mm → query fits, filter by hole_basis=H7, shaft_basis=g6, 10≤size≤18.

**Hole size for a bolt (clearance hole)**:
```
GET ${user_config.SW_KB_HOST}/api/standards/clearance_holes
GET ${user_config.SW_KB_HOST}/api/standards/clearance_holes/{designation}
```
Query when: adding a bolt hole. Key: `designation` = "M8", "M10", etc.
Returns: `close_mm`, `normal_mm`, `loose_mm` diameters (use `normal_mm` by default per HOLE-001).

**General tolerance for a dimension**:
```
GET ${user_config.SW_KB_HOST}/api/standards/tolerances_iso2768
```
Filter by `tol_class` (f/m/c/v) and `range_min_mm`/`range_max_mm`.
Use: get `tol_mm` (symmetric ±) for a given nominal dimension under the project's tolerance class.

**Fastener geometry**:
```
GET ${user_config.SW_KB_HOST}/api/standards/fasteners
GET ${user_config.SW_KB_HOST}/api/standards/fasteners/{designation}
```
Returns: `pitch_coarse_mm`, `head_width_mm`, `head_height_mm`, `strength_class`.

**Sheet metal gauge → thickness**:
```
GET ${user_config.SW_KB_HOST}/api/standards/sheet_metal_gauges
```
Filter by `gauge` and `material` (steel/aluminum/stainless).

**Preferred number check (R5/R10/R20)**:
```
GET ${user_config.SW_KB_HOST}/api/standards/preferred_numbers
```
Use: verify nominal dimension is on the R20 series per DFM-002.

**Specific row lookup**:
```
GET ${user_config.SW_KB_HOST}/api/standards/{table}/{key}
```
Use when you know the exact identifier (e.g. material name, fastener designation).

---

## Phase 6 — Post-Design Validation

After completing the geometry (before exporting/saving as done), run check-context
again with the FINAL design parameters.

```
POST ${user_config.SW_KB_HOST}/api/check-context
{ final design context — more complete than Phase 4 }
```

This catches any rule violations introduced during modeling.
All `fail` results must be resolved. All `advisory` results must be documented
in the session `issues` field when submitting feedback.

---

## Full Pre-Start Sequence (summary)

```
User asks to build X
        │
        ▼
[Phase 0] ENG-001 — real, manufacturable parts only. No placeholders,
          no invented dimensions. Applies even when the KB is unreachable.
        │
        ▼
[Phase 1] GET /api/knowledge?kind=convention
          → load all conventions as active session rules
        │
        ▼
[Phase 2] GET /api/design-rules
          → load all active rules, internalize by category
        │
        ▼
[Phase 3] GET /api/knowledge/search?q={task}
          → read top 5-8 docs (playbooks first, then references)
          → pay special attention to reference docs for SW API methods you'll use
        │
        ▼
[Phase 4] POST /api/check-context  { initial design parameters }
          → fix all 'fail' results before proceeding
        │
        ▼
[Continue to kb-api skill for catalog lookup]
[Build the model]
        │
        ▼
[Phase 6] POST /api/check-context  { final design parameters }
          → fix any new fails
          → document advisories in session feedback
```

After completing Phases 1–4, invoke Skill(solidworks-claude-plugin:kb-api) for catalog lookup.

---

## Error Handling

| Status | Action |
|--------|--------|
| Server unreachable | Log "KB offline — proceeding without pre-start checks." Continue. |
| 404 on knowledge search | No relevant docs found. Proceed with own knowledge. |
| 422 on check-context | Body malformed. Try with fewer fields. Do not block. |
| 5xx | Skip that phase. Note in session issues. Continue. |

**Phase 0 is exempt from all of the above.** ENG-001 is not a KB lookup and
does not degrade when the server is unreachable. Losing the standards tables
means you have *less* grounding for a dimension, not permission to invent one —
so an offline KB makes "state what is missing" more likely to be the right
answer, not less.

**Never block the user's task because of a KB failure.**
The KB is an accelerator, not a gatekeeper.
