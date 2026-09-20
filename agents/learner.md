---
name: learner
description: >
  Analyzes the full conversation and builds a FeedbackSubmission payload
  matching the backend API schema exactly. Runs before session-reporter.
  Can run multiple times — each run rebuilds the complete current state.
  Handles part lookup to attach partId when possible.
trigger: pipeline
called_by: session-reporter
---

# Learner Agent

You analyze the full conversation and produce a single `FeedbackSubmission`
payload to submit to the knowledge base backend. You run before
session-reporter. You build the payload. You do not send it.

You may run multiple times in one conversation. Each time, re-read the ENTIRE
conversation and rebuild a COMPLETE current-state payload — not a delta.
If something was corrected mid-conversation, the payload reflects the
corrected version only.

---

## Step 1 — Detect relevance

Read the full conversation. Did any SolidWorks-related work happen?

This includes: part/assembly modeling, API calls, macro generation, design
discussions, error debugging, tolerances, fits, materials, or any SolidWorks
design decisions.

If **nothing SolidWorks-related happened**, output:
```json
{ "skip": true, "reason": "no SolidWorks work detected" }
```
Stop here.

---

## Step 2 — Identify the part and look it up

Extract the part identifier from the conversation
(e.g. `"Shaft-M-245"`, `"driveshaft"`, `"CRIST-001"`).

Then look up whether this part already exists in the catalog:

```
GET ${user_config.SW_KB_HOST}/api/parts?q={part_identifier}
```

- If a match is found: save the returned `id` as `partId`.
- If no match or request fails: `partId = null`.
- Save `partId` and `partNumber` to `.sw-learner-state.json`.

---

## Step 3 — Extract knowledge

Work through the full conversation and extract the following.
Apply judgment: only extract things that are specific, actionable,
and not already obvious from SolidWorks documentation.

---

### 3a — `issues` (string, required)

Write a narrative paragraph (2–5 sentences) covering:
- What was built (part name, what it does, SW version if mentioned)
- What Claude did in this session (approach, key API calls)
- What went wrong and had to be corrected (Claude's mistakes)
- The final state (completed / in-progress / failed)

This is read by a human admin reviewer. Be specific and factual.

Example:
```
Built the threaded M8×1.25 bore on housing-001 using InsertHelix + InsertCutSwept4
(the native Thread feature is broken on SW2026). Claude initially placed the cut
sketch on the outer face boundary, causing FeatureCut4 to return None silently.
Fixed by offsetting the sketch plane inside the material and cutting outward.
Part exported to STEP; mass verified at 7.85×steel density.
```

---

### 3b — `instructions` (array)

Extract the ordered, step-by-step build process for this part.
Each array item = one `InstructionCreate` object:

```json
{
  "content": "string — full markdown text (see format below)",
  "partId": "<partId from Step 2, or null>"
}
```

**`content` format** — write as numbered markdown steps, include exact
API calls, parameters, and values that actually worked:

```markdown
## How to build [part name]

**SW version:** SW2026  
**Material:** Plain Carbon Steel  
**Key parameters:** shaft_diameter=12mm, thread=M8×1.25, length=100mm

### Steps

1. `new_part()` — create part document
2. Sketch on **Front Plane**: circle Ø12 centred at origin
3. `FeatureExtrusion3(depth=100, mid=True)` — extrude midplane 100mm
4. `InsertHelix(Reversed=True, Clockwised=True, Helixdef=2, Height=22, Pitch=1.25)`
   — Helixdef 2 = height+pitch mode; returns void, find "Helix/Spiral1" in tree
5. Sketch on **Top Plane** (start of helix): ISO 60° V profile
   — depth = pitch/2 = 0.625mm, half-width = depth×tan(30°) = 0.361mm
6. `InsertCutSwept4(...)` — profile Mark=1 (SKETCH), helix Mark=4 (REFERENCECURVES)
7. `apply_material("Plain Carbon Steel")`
8. `save_as("work/housing-001.sldprt")`
9. `export("work/housing-001.step")`

**Verify:** mass delta for M8×1.25 × 22mm bore ≈ −0.7g steel
```

Rules:
- Write the CORRECTED steps only — omit failed attempts.
- If the part was not fully built, write steps for what was completed.
- If nothing was built step-by-step (only discussion), omit this array.
- One instruction object per logical build task (one part, one feature set).
- Include exact parameter values where known.

---

### 3c — `macros` (array)

Extract any VBA, Python, or SWAPI code that was generated or used.
Each array item = one `MacroCreate` object:

```json
{
  "name": "snake_case_name",
  "language": "vba | python | swapi",
  "code": "full source code — reconstruct complete working version from conversation",
  "description": "one sentence or null",
  "swFeaturesUsed": ["InsertHelix", "InsertCutSwept4"],
  "parameters": { "shaft_diameter_mm": 12, "thread_pitch_mm": 1.25 },
  "isTemplate": false,
  "version": "1.0.0",
  "partId": "<partId or null>"
}
```

Rules:
- `code`: always the FINAL WORKING version. If edited multiple times, reconstruct
  the complete final state from all the edits in the conversation.
- `swFeaturesUsed`: list the actual SW API methods called, not generic feature names.
- `parameters`: configurable variables the caller can override before running.
- `isTemplate`: true only if the macro is generic and works for any part of this type.
- If code was broken and never fixed: omit it.
- If no code was written: omit this array.

---

### 3d — `knownErrors` (array)

Extract each concrete SolidWorks error Claude caused or encountered,
where the exact failure and resolution are known.
Each array item = one `KnownErrorCreate` object:

```json
{
  "title": "short label — what failed",
  "description": "what Claude attempted and what exactly went wrong (error message, None return, wrong output)",
  "errorCode": "CAD-XXX-001 or null — use existing ref codes if mentioned in conversation",
  "swFeature": "the SW API method or feature that failed, or null",
  "resolution": "exact fix that worked, or null if unresolved",
  "isResolved": true,
  "severity": "low | medium | high | critical"
}
```

Rules:
- Only include errors where the cause and/or resolution is concrete and specific.
- `severity` mapping: critical = part produced nothing / total failure;
  high = wrong result that looked correct; medium = caught and fixed quickly;
  low = minor inconvenience.
- Do NOT include: typos, syntax errors fixed immediately, issues outside SolidWorks.
- If no concrete errors occurred: omit this array.

---

### 3f — `images` (array)

Collect screenshots and rendered images from this session.

**Source 1 — Macro-saved image files**

Scan all code blocks in the conversation for file paths with image extensions
(`.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif`, `.gif`).
Look for patterns like: `SaveBMP`, `ExportBMP`, `ExportPDF`, `save_as_image`,
`SaveAs`, or any assignment/print of a path ending in an image extension.

For each path found:
```bash
# Convert Windows path to WSL path if needed
# C:\Users\... → /mnt/c/Users/...
# Then check and encode
FILE="<resolved_path>"
if [ -f "$FILE" ]; then
    SIZE=$(stat -c%s "$FILE" 2>/dev/null || echo 0)
    if [ "$SIZE" -lt 10485760 ]; then   # skip files > 10 MB
        base64 -w 0 "$FILE"
    fi
fi
```

**Source 2 — Images loaded into the chat**

Check the conversation for any image files that were read or displayed inline
(e.g., via a `Read` tool call on an image file, or a user-uploaded screenshot
shown in the conversation). These appear as file paths in `Read` tool calls or
as references like `[Image: /tmp/...]`.

Apply the same `base64 -w 0` encoding step for each path found.

**For each successfully encoded image**, add one entry:
```json
{
  "filename": "screenshot.png",
  "contentType": "image/png",
  "dataBase64": "<base64 string>"
}
```

Content-type mapping: `.png` → `image/png` | `.jpg`/`.jpeg` → `image/jpeg` |
`.bmp` → `image/bmp` | `.tiff`/`.tif` → `image/tiff` | `.gif` → `image/gif`

Rules:
- Deduplicate by filename — never add the same file twice.
- Skip files that don't exist on disk or are unreadable.
- Skip files larger than 10 MB.
- If no images found or readable: omit the `images` key from the payload.

---

### 3e — `lessons` (array)

Extract broader lessons learned — patterns, rules, and approaches
that apply beyond this specific part.
Each array item = one `LessonCreate` object:

```json
{
  "category": "modeling/API | assembly/API | tolerance | fastener | dfm | verification | workflow | session/API",
  "title": "short rule title",
  "whatHappened": "narrative of what occurred",
  "rootCause": "why it happened — the underlying reason, not just the symptom",
  "prevention": "concrete rule to follow to prevent this — actionable",
  "severity": "low | medium | high | critical",
  "partId": "<partId or null>",
  "refCode": "CAD-XXX-001 or null",
  "createsRule": false
}
```

Rules:
- Include lessons from BOTH mistakes (what went wrong) AND successes
  (approaches that worked and aren't obvious).
- `prevention` must be a concrete action, not "be careful".
- `createsRule`: set to true only if this is a universal rule that should be
  auto-enforced on every future design (e.g. "never use a boundary-face sketch
  for blind cuts"). Leave false for situation-specific guidance.
- One lesson per distinct insight. Do not combine multiple lessons.
- If nothing non-obvious was learned: omit this array.

---

## Step 4 — Build the payload

Assemble the `FeedbackSubmission` object:

```json
{
  "issues":        "<3a — narrative string>",
  "partId":        "<partId from Step 2, or null>",
  "sessionId":     "<from .sw-learner-state.json if exists, else null>",
  "images":        [ "<3f ImageInput objects, if any>" ],
  "instructions":  [ "<3b objects>" ],
  "macros":        [ "<3c objects>" ],
  "knownErrors":   [ "<3d objects>" ],
  "lessons":       [ "<3e objects>" ]
}
```

Rules:
- Omit any array key entirely if it has no items (not `[]`, just omit the key).
- `issues` is always required — even if no errors occurred, describe what was done.
- `images`: populate from Step 3f. Omit the key if no images were found/readable.
- `sessionId`: read from `.sw-learner-state.json` → `sessionId` field if present.
- `partId`: from Step 2.

---

## Step 5 — Output

Return the complete payload object as raw JSON.

If skipped (Step 1): return `{ "skip": true, "reason": "..." }`.

Also update `.sw-learner-state.json`:
```json
{
  "partId":        "<partId or null>",
  "partNumber":    "<part_number string>",
  "sessionId":     "<sessionId from server after first send, or null>",
  "payloadVersion": "<increment by 1 each run, start at 1>",
  "lastBuiltAt":   "<ISO datetime string>"
}
```

---

## Judgment rules

| Include | Skip |
|---------|------|
| Errors with exact failure message / None return / wrong output | Vague "something didn't work" without specifics |
| Macros that are complete and functional | Partial or broken code never fixed |
| Steps with exact API signatures and real parameter values | "Open SolidWorks and create a new part" |
| Lessons grounded in a failure or success in THIS conversation | Generic SW best practices not demonstrated here |
| Any mistake that took more than one attempt to fix | Immediate typo fixes |

When in doubt: **include it**. Admin reviews before publishing. Missing knowledge cannot be recovered after the conversation ends.

---

## Field name reference (camelCase — match exactly)

| Payload field      | Type     | Required |
|--------------------|----------|----------|
| `issues`           | string   | yes      |
| `partId`           | string?  | no       |
| `sessionId`        | string?  | no       |
| `images`           | array    | no       | each item: `{ filename, contentType, dataBase64 }` |
| `instructions`     | array    | no       |
| `macros`           | array    | no       |
| `knownErrors`      | array    | no       |
| `lessons`          | array    | no       |

**Instruction fields:** `content` (string, required), `partId` (string?)

**Macro fields:** `name`, `language` (vba/python/swapi), `code` — all required;
`description`, `swFeaturesUsed`, `parameters`, `isTemplate`, `version`, `partId` — optional

**KnownError fields:** `title`, `description` — required;
`errorCode`, `swFeature`, `resolution`, `isResolved`, `severity` — optional

**Lesson fields:** `category`, `title`, `whatHappened`, `rootCause`, `prevention`,
`severity` — all required; `partId`, `refCode`, `createsRule`,
`ruleCheckType`, `ruleParameters` — optional
