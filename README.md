# SolidWorks Design Assistant — Claude Code Plugin

A Claude Code plugin that brings AI-assisted SolidWorks CAD design directly into your workflow, powered by a curated knowledge base of SolidWorks documentation, macros, standards, and design patterns.

## Installation

> **Prerequisites:** [Claude Code](https://docs.claude.com/en/docs/claude-code) v1.0.0 or newer.

### Step 1 — Add the marketplace

In an open Claude Code session, register this repo as a plugin marketplace:

```
/plugin marketplace add Erfouni/solidworks-claude-plugin
```

Claude Code reads `.claude-plugin/marketplace.json` from the repo and registers a marketplace named `solidworks-claude-plugin`.

### Step 2 — Install the plugin

```
/plugin install solidworks-claude-plugin@solidworks-claude-plugin
```

The format is `<plugin-name>@<marketplace-name>` — both happen to be `solidworks-claude-plugin` here. Confirm the install when prompted, then restart Claude Code (or run `/plugin` and reload) so the skills, agents, and hooks activate.

> **Tip:** You can also browse and install interactively by running `/plugin` and selecting the marketplace from the menu.

### Step 3 — Point at your own knowledge base (optional)

The plugin reads the knowledge base over plain HTTPS using `curl`. It is **public — no API key or login required** — and defaults to `https://sw-plugin.ideep.org`, so the plugin works out of the box.

If you host the knowledge base yourself, set the base URL in the plugin's configuration:

| Setting | Default |
|---|---|
| `SW_KB_HOST` | `https://sw-plugin.ideep.org` |

Every skill, agent, and the SessionStart hook read that one value, so changing it redirects all
knowledge lookups and feedback submissions to your server. Verify it with
`bash tests/test-session-start-host.sh`, which fails if anything falls back to the public host.

### Step 4 — Verify

Run `/plugin` and confirm **SolidWorks Design Assistant** is listed and enabled. Start a SolidWorks task — the `pre-start` skill loads conventions and design rules before the first action, which confirms the plugin and knowledge base are wired up.

### Updating & removing

```
# pull the latest plugin version
/plugin marketplace update solidworks-claude-plugin

# uninstall
/plugin uninstall solidworks-claude-plugin@solidworks-claude-plugin
```

## How it works

Four skills run in order around a SolidWorks session:

| Skill | When | What it does |
|---|---|---|
| `pre-start` | before any modelling | Loads conventions, all active design rules, and task-relevant knowledge documents; runs the design-rule checker against your parameters |
| `kb-api` | after pre-start | Looks up the catalog — category → part → its instructions, macros and known errors — so an existing design is reused rather than rebuilt |
| `learner` | throughout | Tracks instructions, every code block, errors and lessons as they happen |
| `session-reporter` | at the end | Asks consent, then submits the session to the knowledge base for review |

### The feedback loop

A session produces macros, instructions, known errors and lessons. Those are submitted as **drafts** and are not visible to anyone else until a reviewer approves them in the admin console, scopes them to a part (or to general knowledge), and publishes them. Published knowledge is then served back through this plugin, so the next session starts from it.

`session-reporter` also sends what it believes it built:

```json
{
  "suggestedCategory":   "Yokes",
  "suggestedPartName":   "Cardan yoke, 30mm bore",
  "suggestedPartNumber": "YK-030"
}
```

These are hints for the reviewer, never decisions — nothing is published on their strength. The agent that built the component knows what it was asked for, so passing that forward saves the reviewer working it out from code and renders.

## Knowledge base contents

| | |
|---|---|
| Knowledge documents | conventions, playbooks, API references, strategies |
| Lessons | real failures and their prevention rules, from past sessions |
| Design rules | enforceable checks with severities (fastener, DFM, tolerance, assembly clearance) |
| Standards tables | materials, fasteners, fits, clearance holes, ISO 2768 tolerances, preferred numbers, sheet-metal gauges, GD&T symbols, surface finish |
| Catalog | parts and categories, with their published macros and instructions |

Documents are in English and Persian; both carry the same engineering content.

## Directory Structure

```
solidworks-claude-plugin/
├── .claude-plugin/
│   ├── plugin.json        # plugin metadata + SW_KB_HOST config
│   └── marketplace.json   # marketplace catalog
├── commands/              # slash commands (none yet)
├── agents/                # subagents
├── skills/                # the four skills above
├── hooks/                 # lifecycle hooks
├── docs/openapi.json      # knowledge base API reference
└── README.md
```

## Not yet built

- Slash commands for common SolidWorks tasks (sketches, features, assemblies, drawings)
- An MCP server for the knowledge base. The plugin does **not** use MCP today — every skill calls the REST API with `curl`, and `plugin.json` declares `"mcp": false`. An MCP transport would be an addition, not a replacement.

## License

MIT
