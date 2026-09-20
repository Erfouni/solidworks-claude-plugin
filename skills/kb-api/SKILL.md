---
name: kb-api
description: >
  How to use the SolidWorks knowledge base before building any 3D model.
  Teaches Claude to navigate categories → parts → full detail before touching
  SolidWorks. Must be followed every time a user asks to create a model.
trigger: always
---

# SolidWorks Knowledge Base — Design Lookup Protocol

**Run order: `pre-start` skill first, then this skill.** Pre-start loads
conventions, design rules, and knowledge documents. This skill looks up the
specific part in the catalog. Complete both before modeling.

**This skill is mandatory.** Every time a user asks you to create, build, or
model anything in SolidWorks, you MUST follow the lookup sequence below before
writing a single line of code or opening SolidWorks.

The knowledge base contains published instructions, macros, known errors, and
lessons from real past sessions. Always use what exists before inventing.

Base URL: `${user_config.SW_KB_HOST}` — the value of the `SW_KB_HOST` plugin config, which falls back to the public server when unset.
All endpoints are **public — no auth header needed**.

**IMPORTANT — use `curl` via the Bash tool for every request. Never use Fetch
or WebFetch — they route through Anthropic's cloud and cannot reach private
network addresses. Always quote the URL in double quotes — unquoted `?` and
`&` are shell glob/control characters in zsh and will fail.**

---

## Mandatory Lookup Sequence

Follow these steps in order every time. Do not skip steps.

---

### Step 1 — Confirm the server is reachable

```
GET ${user_config.SW_KB_HOST}/health
```

Expected: `{ "status": "ok" }`

- If reachable: continue to Step 2.
- If unreachable: tell the user "Knowledge base is offline — proceeding without
  KB lookup." Then build from your own knowledge. Do NOT abort the task.

---

### Step 2 — Load all categories

```
GET ${user_config.SW_KB_HOST}/api/categories
```

Response: flat array of categories
```json
[
  { "id": "uuid", "name": "Shaft",    "slug": "shaft",    "description": "...", "createdAt": "..." },
  { "id": "uuid", "name": "Housing",  "slug": "housing",  "description": "...", "createdAt": "..." },
  { "id": "uuid", "name": "Assembly", "slug": "assembly", "description": "...", "createdAt": "..." }
]
```

From the user's request, identify which category the part belongs to.
Match by `name` or `slug` — fuzzy match is fine (e.g. "shaft" → "Shaft").

- If a matching category is found: save its `id` as `categoryId`. Continue to Step 3.
- If no matching category: skip to Step 4 (free-text search fallback).

---

### Step 3 — List parts in that category

```
GET ${user_config.SW_KB_HOST}/api/parts?categoryId={categoryId}&pageSize=100
```

Optional — also filter by tags or search term to narrow results:
```
GET ${user_config.SW_KB_HOST}/api/parts?categoryId={categoryId}&q={part_number}&pageSize=100
```

Response: `PartListResponse`
```json
{
  "items": [
    {
      "id": "uuid",
      "partNumber": "Shaft-M-245",
      "name": "Drive Shaft M245",
      "categoryId": "uuid",
      "description": "...",
      "material": "Plain Carbon Steel",
      "tags": ["rotating", "transmission"],
      "status": "active"
    }
  ],
  "page": 1,
  "pageSize": 100,
  "total": 3
}
```

Scan the returned items for the part the user asked about.
Match by `partNumber` (exact or close match) or `name`.

- If a matching part is found: save its `id` as `partId`. Continue to Step 4.
- If no matching part in this category: continue to Step 4 (free-text fallback).

---

### Step 4 — Get full part detail

If you have a `partId` from Step 3:
```
GET ${user_config.SW_KB_HOST}/api/parts/{partId}
```

If you don't have a `partId` yet (no category match or no part match in Step 3):
```
GET ${user_config.SW_KB_HOST}/api/parts?q={part_number_or_name}&pageSize=20
```
Take the best match from the results (if any), then:
```
GET ${user_config.SW_KB_HOST}/api/parts/{partId}
```

Response: `PartDetail` — the part plus ALL its linked published knowledge:
```json
{
  "id": "uuid",
  "partNumber": "Shaft-M-245",
  "name": "Drive Shaft M245",
  "categoryId": "uuid",
  "description": "...",
  "material": "Plain Carbon Steel",
  "tags": ["rotating"],
  "status": "active",

  "instructions": [
    {
      "id": "uuid",
      "content": "## How to build Shaft-M-245\n\n**Material:** Plain Carbon Steel\n\n### Steps\n1. `new_part()`...",
      "partId": "uuid",
      "status": "published"
    }
  ],

  "macros": [
    {
      "id": "uuid",
      "name": "build_shaft_m245",
      "language": "python",
      "code": "# full source code...",
      "swFeaturesUsed": ["InsertHelix", "InsertCutSwept4"],
      "parameters": { "shaft_diameter_mm": 12, "thread_pitch_mm": 1.25 },
      "isTemplate": false,
      "status": "published"
    }
  ],

  "knownErrors": [
    {
      "id": "uuid",
      "title": "Blind cut returns None when sketch is on boundary face",
      "description": "...",
      "swFeature": "FeatureCut4",
      "resolution": "Offset sketch plane inside the material and cut outward.",
      "isResolved": true,
      "severity": "medium"
    }
  ],

  "lessons": [
    {
      "id": "uuid",
      "category": "modeling/API",
      "title": "InsertHelix: Helixdef=2 for height+pitch mode",
      "whatHappened": "...",
      "rootCause": "...",
      "prevention": "Always use Helixdef=2 when specifying both height and pitch.",
      "severity": "high"
    }
  ]
}
```

---

### Step 5 — Use what you found

**If the part exists with instructions:**
- Read every item in `instructions`, `macros`, `knownErrors`, and `lessons`.
- Follow the published instructions as your primary build guide.
- Use the published macro directly if one exists and is complete.
- Read all `knownErrors` BEFORE using any SW feature — if a known error exists
  for a feature you're about to call, apply the resolution proactively.
- Apply all lessons as rules throughout the build.
- Tell the user: *"Found existing knowledge for [part_number]. Using published
  instructions and [N] macros."*

**If the part exists but has no instructions/macros yet:**
- Read `knownErrors` and `lessons` — still apply them.
- Build from your own knowledge, informed by KB errors and lessons.
- Tell the user: *"[part_number] is in the catalog but has no published build
  instructions yet. Building from scratch."*

**If the part does not exist at all:**
- Still check global known errors and lessons (Step 6).
- Build from your own knowledge.
- Tell the user: *"[part_number] is not in the knowledge base yet. Building
  from scratch — this session's data will be submitted for review."*

---

### Step 6 — Always load global known errors and lessons

Do this regardless of whether the specific part was found.
These apply to ALL SolidWorks work.

```
GET ${user_config.SW_KB_HOST}/api/errors
GET ${user_config.SW_KB_HOST}/api/lessons
```

Scan the results. Before calling any SolidWorks API method, check `api/errors`
for a known error on that method. If one exists and `isResolved: true`,
apply the `resolution` before making the call — do not trigger the known error.

---

## Decision tree (summary)

```
User asks to build X
        │
        ▼
GET /health ──── offline ──────────────────────► build without KB
        │
        ▼ online
GET /api/categories
        │
        ├── found matching category ──► GET /api/parts?categoryId=...
        │                                       │
        │                                       ├── found part ──► GET /api/parts/{id} ──► Step 5
        │                                       │
        │                                       └── not found ──► Step 4 fallback
        │
        └── no matching category ──────────────► GET /api/parts?q=... ──► GET /api/parts/{id} ──► Step 5
                                                                    │
                                                                    └── nothing found ──► build from scratch
                                                                    (still run Step 6)
```

---

## How to use found data

### Instructions (`content` field)
The `content` field is a markdown string containing the full build process.
Read it top to bottom. Follow the numbered steps in order — SolidWorks rebuild
order is critical and the instructions encode the correct sequence.

### Macros (`code` field)
If `isTemplate: false` and `partNumber` matches: run the macro directly
(adjust `parameters` if the user specified different values).

If `isTemplate: true`: adapt the macro for this specific part's parameters.

`parameters` object shows which values are configurable:
```json
{ "shaft_diameter_mm": 12, "thread_pitch_mm": 1.25, "length_mm": 100 }
```
Override these with user-specified values before running.

### Known Errors (`knownErrors` array)
Each entry is a trap to avoid. The `resolution` is the fix.
Read ALL entries before calling any SW API. Cross-reference by `swFeature`.

Example pre-flight check:
```
About to call: FeatureCut4
Check errors: found "Blind cut returns None when sketch on boundary face"
              swFeature: "FeatureCut4", isResolved: true
Resolution: "Offset sketch plane inside material, cut outward"
→ Apply resolution BEFORE making the call.
```

### Lessons (`lessons` array)
Each lesson is a rule. Apply `prevention` as a constraint throughout the build.
Pay attention to `severity: critical` and `severity: high` first.

---

## Caching

Load categories and global errors/lessons ONCE per conversation.
Do not re-fetch on every user message — they don't change mid-session.

Part detail (`GET /api/parts/{id}`) can be fetched once and reused throughout
the build session.

---

## Error handling

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | OK | Use the data |
| 404 | Not found | Part/category doesn't exist — build from scratch |
| 422 | Bad request | Log query error, try fallback search |
| 5xx / timeout | Server error | Skip KB, build from own knowledge |

Never block the user's task on a KB failure. Mention it and continue.
