# hermes-skill-graph

**Knowledge graph for Hermes Agent skill discovery.**  
Replace flat name/tag matching with typed relationship traversal.

> **Plugin** — parses SKILL.md relations, builds a SQLite graph, registers `skill_graph_search()` tool  
> **Skill** — teaches the agent when and how to use graph-based discovery

---

## Why

Hermes Agent loads skills by name, description, and tags. This works when you know what to ask for, but falls short when:

- A skill's name doesn't match your intent ("Python review" → needs `github-code-review`)
- Related skills are scattered across categories
- You want to discover complementary skills you didn't know existed

The skill graph solves this by letting skill authors declare **typed relationships** between skills:

```yaml
# In any SKILL.md frontmatter:
metadata:
  hermes:
    relations:
      - type: complemented_by
        target: systematic-debugging
        properties:
          reason: "review after finding the root cause"
          strength: strong
```

When you search with `skill_graph_search("Python code review")`, the plugin:
1. FTS5 full-text search on name/description/tags
2. Graph traversal along `supports_language`, `complemented_by`, `depends_on` edges
3. Returns skills with relationship chains showing **why** each was found

Results include `relationship_chain` arrays like:
```
github-code-review --(supports_language)--> python
systematic-debugging --(complemented_by)--> github-code-review
```

---

## Quick Install

```bash
git clone https://github.com/nuffin/hermes-skill-graph.git
cd hermes-skill-graph
bash install.sh
```

Restart Hermes (`/reset` in a session, or exit+relaunch) to activate the plugin.

### Uninstall

```bash
bash install.sh --uninstall
```

Removes the symlinks but keeps the graph database (`~/.hermes/personal/skill-graph.db`). Remove the DB manually if you want a clean slate.

---

## What Gets Installed

| Component | Target Path | Purpose |
|-----------|-------------|---------|
| Plugin | `~/.hermes/plugins/skill-graph/` | Graph engine, search tool, lifecycle hooks |
| Skill | `~/.hermes/skills/skill-graph/` | Agent guidance on using the graph |
| Database | `~/.hermes/skill-graph.db` (default profile) or `~/.hermes/profiles/<name>/skill-graph.db` | SQLite + FTS5 graph (auto-created at runtime) |

---

## Usage

### From a chat session

Once installed, the `skill_graph_search()` tool is available to the agent automatically. Run a query:

```
# The agent will call skill_graph_search internally when it needs to
# find relevant skills. You can also invoke it explicitly:
/skill-graph search "Python code review"
```

The companion skill (`/skill-graph`) loads guidance for the agent on when to use graph search vs. flat skill listing.

### From the CLI

```bash
hermes chat --toolsets skills -q "Use skill-graph to find skills for database performance tuning"
```

### Adding your own relations

Add a `relations` field to any SKILL.md to seed the graph:

```yaml
---
name: my-deploy-workflow
metadata:
  hermes:
    relations:
      - type: depends_on
        target: docker-compose-review
        properties:
          reason: "must validate compose files before deploying"
          strength: strong
      - type: complemented_by
        target: deployment-verification
        properties:
          reason: "verify deployment health after deploy"
---
```

See [docs/relations-format.md](docs/relations-format.md) for the full spec.

---

## Relation Types

| Type | Meaning | Auto-Reverse | Example |
|------|---------|-------------|---------|
| `depends_on` | Needs another skill to work | → `supported_by` | `deploy` → `config-validate` |
| `supported_by` | Another skill enables this | → `depends_on` | (auto-generated) |
| `complemented_by` | Works well together | Symmetric | `review` ↔ `debug` |
| `alternative_to` | Alternative approach | Symmetric | `docker` ↔ `k8s` |
| `similar_to` | Semantically similar | Symmetric | (auto from legacy `related_skills`) |
| `supersedes` | Replaces an older skill | → `superseded_by` | `v2-deploy` → `v1-deploy` |

Properties (optional, in `properties` dict):
- `reason`: Human-readable explanation
- `strength`: `strong` / `medium` / `weak`
- `level`: `full` / `partial` (for capability relationships)

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  on_session_start hook                               │
│    └─ Full refresh: scan all SKILL.md, rebuild graph  │
├─────────────────────────────────────────────────────┤
│  post_tool_call hook                                  │
│    └─ Detect skill_manage create/edit/patch           │
│       └─ Incremental: update just that skill          │
├─────────────────────────────────────────────────────┤
│  skill_graph_search(query) tool                       │
│    └─ FTS5 → Tag match → Graph traversal → Ranked    │
└─────────────────────────────────────────────────────┘
```

### Storage

- **SQLite** with WAL mode at `~/.hermes/skill-graph.db` (default profile)
- **Per-profile**: `~/.hermes/profiles/<name>/skill-graph.db`
- **FTS5** for full-text search on name, category, description, tags
- Relational model (3 tables: `skill_nodes`, `skill_edges`, `skill_fts`)
- Ready for future vector embedding extension (add a `embedding BLOB` column)

---

## Project Layout

```
hermes-skill-graph/
├── README.md                          # This file
├── LICENSE
├── CHANGELOG.md
├── install.sh                         # Standalone install script
├── plugin/
│   └── skill-graph/
│       ├── plugin.yaml                # Plugin manifest
│       └── __init__.py                # ~730-line plugin implementation
├── skill/
│   └── skill-graph/
│       └── SKILL.md                   # Agent companion skill
└── docs/
    └── relations-format.md            # Full relations field spec
```

---

## License

MIT — see [LICENSE](LICENSE).
