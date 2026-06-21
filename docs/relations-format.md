# SKILL.md Relations Format

The skill graph plugin reads a `relations` field from the `metadata.hermes` section of any SKILL.md YAML frontmatter. This document is the full specification.

---

## Location

In the YAML frontmatter of `SKILL.md`:

```yaml
---
name: my-skill
description: What it does
metadata:
  hermes:
    tags: [relevant, keywords]
    relations:
      - type: complemented_by
        target: another-skill
        properties:
          reason: "why they work together"
          strength: strong
---
```

---

## Schema

Each entry in the `relations` array has three fields:

### `type` (required)

One of the predefined relation types:

| Type | Direction | Semantics |
|------|-----------|-----------|
| `depends_on` | Directed | This skill needs another to function. Generates reverse edge `supported_by`. |
| `supported_by` | Directed | Another skill supports this one. Generates reverse edge `depends_on`. |
| `complemented_by` | Undirected | Works well with another skill. No reverse edge (symmetric). |
| `alternative_to` | Undirected | Alternative approach for the same task. No reverse edge. |
| `similar_to` | Undirected | Semantically similar. No reverse edge. Auto-generated from legacy `related_skills`. |
| `supersedes` | Directed | Replaces an older skill. Generates reverse edge `superseded_by`. |
| `used_in_workflow` | Undirected | Part of a larger workflow. No reverse edge. |

### `target` (required)

The name of the other skill. Must match the skill's `name:` field exactly.

### `properties` (optional)

A dict of key-value pairs. Common properties:

| Key | Type | Description |
|-----|------|-------------|
| `reason` | string | Human-readable explanation of the relationship |
| `strength` | string | `strong`, `medium`, or `weak` |
| `level` | string | `full` or `partial` (for capability relationships) |
| `source` | string | Origin of the relationship (e.g., `manual`, `legacy_related_skills`) |

You can add any custom properties — they're stored as JSON and returned in search results.

---

## Examples

```yaml
# Directed: depends_on → auto-generates supported_by
metadata:
  hermes:
    relations:
      - type: depends_on
        target: systematic-debugging
        properties:
          reason: "必须先定位根因再修复"
          strength: strong
      - type: complemented_by
        target: github-pr-workflow
        properties:
          reason: "review 完直接开 PR"
```

```yaml
# Legacy compat: related_skills auto-converts to similar_to
metadata:
  hermes:
    related_skills: [test-driven-development, github-code-review]
# ↑ Equivalent to:
#   relations:
#     - type: similar_to
#       target: test-driven-development
#       properties: {source: legacy_related_skills}
#     - type: similar_to
#       target: github-code-review
#       properties: {source: legacy_related_skills}
```

---

## How Relations Affect Search

1. **Direct FTS5 match** — skill name/description/tags match the query
2. **Graph expansion** — from matched skills, follow `complemented_by`, `depends_on`, `supported_by` edges to find more
3. **Multi-hop** — the graph traverses up to 3 hops from any match
4. **Scoring** — direct matches score highest, then tag matches, then graph expansion results

Results include a `relationship_chain` showing the path:

```json
{
  "name": "systematic-debugging",
  "relevance": "expansion",
  "relationship_chain": [
    "github-code-review --(complemented_by)--> systematic-debugging"
  ]
}
```

And `edges_between_results` shows how the result set connects to each other.
