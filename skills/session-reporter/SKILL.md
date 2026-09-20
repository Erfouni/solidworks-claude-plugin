---
name: session-reporter
description: "Run at the end of every SolidWorks session. Collects all generated knowledge and code, checks the 'always-send' preference, then uses AskUserQuestion to present an interactive consent prompt — separate from and after the task output. POSTs to /api/feedback on approval."
---

# Session Reporter

## Step 1 — Detect relevance

Did any SolidWorks work happen in this session?
(modeling, API calls, macro/code generation, design decisions, error debugging)

If nothing SolidWorks-related happened → stop silently. Do not ask anything.

---

## Step 2 — Check "always send" preference

```bash
PREF=$(cat ~/.sw-feedback-pref 2>/dev/null || echo "")
echo "$PREF"
```

If output is `always` → skip Steps 3–5 (no consent question), jump to Step 6 (POST).

---

## Step 3 — Look up the part

Extract the part name/number from the conversation.

```bash
curl -s "${user_config.SW_KB_HOST}/api/parts?q={part_name}"
```

Save the matching `id` as `partId`. Use `null` if nothing found.

---

## Step 4 — Extract ALL knowledge and code from the conversation

### `issues` (required)
2–5 sentences: what was built, approach, what went wrong and was fixed, final state.

### `instructions`
Corrected steps only. Include exact SolidWorks API calls and real parameter values.
```json
{ "content": "## How to build [part]\n\n### Steps\n1. ...", "partId": "<uuid or null>" }
```

### `macros` — ALL code generated in this session

**Capture EVERY code block written or shared with the user:**
- Python scripts for SolidWorks COM automation
- VBA macros
- SWAPI call sequences
- Helper scripts, test code, any code shown in a code block
- Adapted templates

One entry per code artifact:
```json
{
  "name": "snake_case_name",
  "description": "one sentence: what this code does",
  "language": "python | vba | swapi",
  "code": "<FULL VERBATIM SOURCE — complete, never summarized or truncated>",
  "swFeaturesUsed": ["InsertHelix", "FeatureCut4"],
  "parameters": { "shaft_diameter_mm": 12 },
  "isTemplate": false,
  "partId": "<uuid or null>"
}
```

The `code` field MUST contain the complete source as shown to the user.
Never omit code because it's short or a snippet. Every code block goes here.

### `knownErrors`
```json
{
  "title": "short label",
  "description": "what failed exactly — include the return value or error message",
  "swFeature": "SW API method",
  "resolution": "exact fix that worked",
  "isResolved": true,
  "severity": "low | medium | high | critical"
}
```
Only include errors where cause AND resolution are both known.

### `lessons`
```json
{
  "category": "modeling/API | assembly/API | tolerance | fastener | dfm | workflow",
  "title": "short rule title",
  "whatHappened": "narrative",
  "rootCause": "underlying reason",
  "prevention": "concrete actionable rule",
  "severity": "low | medium | high | critical"
}
```

### `suggestedCategory`, `suggestedPartName`, `suggestedPartNumber` — classification hints

You know what you were asked to build. The reviewer only sees the resulting code
and renders, and has to work backwards from them to decide what the component is
and where it belongs. Pass your knowledge forward so they confirm rather than guess.

Fetch the current category list — never invent a category name:

```
GET {KB_HOST}/api/categories
```

Pick the single best match by `name`. If nothing fits, use `"Uncategorised"`
rather than proposing a new one; the reviewer creates categories, not you.

```json
{
  "suggestedCategory":   "Yokes",
  "suggestedPartName":   "Cardan yoke, 30mm bore",
  "suggestedPartNumber": "YK-030"
}
```

| Field | What to put in it |
|---|---|
| `suggestedCategory` | Exact `name` from `/api/categories`, or `"Uncategorised"` |
| `suggestedPartName` | Short descriptive name with the defining dimension |
| `suggestedPartNumber` | The part number if the user gave one, or Step 3 matched an existing part. **Omit it entirely if you are inventing one** — a made-up number is worse than none |

**These are hints, not decisions.** The server stores them and the console shows
them, but nothing publishes on their strength: a reviewer still sets the part
explicitly. So a wrong guess costs nothing, and omitting them costs only the
reviewer's time. Send your honest best guess.

Omit any field you genuinely cannot infer. Do not send empty strings.

---

## Step 5 — Ask consent via AskUserQuestion (interactive prompt)

Use the **AskUserQuestion tool** to present the consent prompt. This creates a
proper interactive UI element that is separate from and appears after the task
output — the user must click an option before you continue.

Call AskUserQuestion with:
```json
{
  "questions": [
    {
      "question": "Share this session's SolidWorks knowledge with the knowledge base?",
      "header": "KB Feedback",
      "multiSelect": false,
      "options": [
        {
          "label": "Yes, send now",
          "description": "Submit instructions, macros, errors, and lessons collected this session (pending admin review)"
        },
        {
          "label": "Always send",
          "description": "Send now and auto-submit in all future sessions without asking again"
        },
        {
          "label": "Skip this session",
          "description": "Do not submit feedback for this session"
        }
      ]
    }
  ]
}
```

Wait for the user's selection before proceeding.

- **"Yes, send now"** → continue to Step 6 (POST)
- **"Always send"** → continue to Step 6 (POST), then Step 7 (save preference)
- **"Skip this session"** → stop here, do not POST

---

## Step 6 — POST the payload

Use Python to handle multiline code and special characters safely.

**Before writing the script**, read the learner's output and check for an `images`
array. For each entry:
- If `dataBase64` is already present (learner encoded it): include as-is.
- If only a file path was provided (edge case): encode it now:
  ```python
  import base64
  with open(path, "rb") as f:
      data = base64.b64encode(f.read()).decode()
  ```

```bash
python3 << 'PYEOF'
import subprocess, json, sys, base64, os

SESSION_ID = "<SESSION_ID from session context>"
KB_HOST = "${user_config.SW_KB_HOST}"

# Helper: encode a file to base64 (used only if learner didn't pre-encode)
def encode_image(path):
    wsl_path = path.replace("\\", "/")
    if wsl_path[1:3] == ":/":  # Windows drive letter
        wsl_path = "/mnt/" + wsl_path[0].lower() + wsl_path[2:]
    try:
        if os.path.getsize(wsl_path) > 10 * 1024 * 1024:
            return None  # skip files > 10 MB
        with open(wsl_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return None

EXT_TO_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".bmp": "image/bmp", ".tiff": "image/tiff", ".tif": "image/tiff",
    ".gif": "image/gif",
}

# Images from learner output — fill this list with learner's images array
# Each entry: { "filename": "...", "contentType": "...", "dataBase64": "..." }
images_raw = [
    # <paste learner images entries here, one dict per image>
]

images = []
seen = set()
for img in images_raw:
    fname = img.get("filename", "")
    if fname in seen:
        continue
    seen.add(fname)
    b64 = img.get("dataBase64") or encode_image(img.get("path", ""))
    if b64:
        images.append({
            "filename": fname,
            "contentType": img.get("contentType") or EXT_TO_MIME.get(
                os.path.splitext(fname)[1].lower(), "image/png"),
            "dataBase64": b64,
        })

payload = {
    "issues": """<issues text>""",
    "sessionId": SESSION_ID,

    # Classification hints - see Step 4. Use an exact name from
    # GET /api/categories, or "Uncategorised". Drop any you cannot infer.
    "suggestedCategory": "<exact category name>",
    "suggestedPartName": "<short descriptive name>",
    "suggestedPartNumber": "<part number, or omit if you would be inventing one>",

    "instructions": [
        {"content": """<instruction content>""", "partId": None}
    ],
    "macros": [
        {
            "name": "script_name",
            "description": "what it does",
            "language": "python",
            "code": """<FULL SOURCE CODE>""",
            "swFeaturesUsed": ["FeatureExtrusion3"],
            "parameters": {},
            "isTemplate": False,
            "partId": None
        }
    ],
    "knownErrors": [
        {
            "title": "error title",
            "description": "what failed",
            "swFeature": "APIMethodName",
            "resolution": "fix applied",
            "isResolved": True,
            "severity": "medium"
        }
    ],
    "lessons": [
        {
            "category": "modeling/API",
            "title": "lesson title",
            "whatHappened": "...",
            "rootCause": "...",
            "prevention": "...",
            "severity": "medium"
        }
    ]
}

if images:
    payload["images"] = images

# Remove null partId at top level
if payload.get("partId") is None:
    payload.pop("partId", None)

# Remove empty arrays
for key in ["instructions", "macros", "knownErrors", "lessons"]:
    if not payload.get(key):
        payload.pop(key, None)

# Drop any classification hint left unfilled. The server treats absent and null
# alike, but sending the literal placeholder text would put "<exact category
# name>" in front of a reviewer as though it were a real suggestion.
for key in ["suggestedCategory", "suggestedPartName", "suggestedPartNumber"]:
    v = payload.get(key)
    if not v or (isinstance(v, str) and v.startswith("<")):
        payload.pop(key, None)

body = json.dumps(payload)

for attempt in range(3):
    result = subprocess.run(
        ["curl", "-s", "-w", "\n%{http_code}", "-X", "POST",
         f"{KB_HOST}/api/feedback",
         "-H", "Content-Type: application/json",
         "-d", body],
        capture_output=True, text=True
    )
    output = result.stdout.strip().split("\n")
    http_code = output[-1] if output else "0"
    body_out = "\n".join(output[:-1])
    
    if http_code.startswith("2"):
        print(f"Feedback submitted. ID: {json.loads(body_out).get('id', '?')}")
        break
    elif http_code.startswith("4"):
        print(f"Feedback rejected ({http_code}): {body_out}")
        break
    else:
        print(f"Attempt {attempt+1} failed ({http_code}). Retrying...")

PYEOF
```

---

## Step 7 — Save "always" preference (only if user chose "Always send")

```bash
echo "always" > ~/.sw-feedback-pref
echo "Auto-send preference saved."
```

---

## Judgment rules

| Include | Skip |
|---------|------|
| ALL code blocks written in this session | Nothing — every code artifact goes in |
| Errors with exact failure / return value / error message | Vague "something didn't work" |
| Steps with exact SW API calls and real parameter values | Generic "open SolidWorks and create a part" |
| Final corrected version of each code artifact | Earlier broken/intermediate versions |
| Non-obvious patterns and lessons from both success and failure | Common knowledge |
