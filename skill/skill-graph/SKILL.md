---
name: skill-graph
description: Skill knowledge graph — find the right skill by intent. Uses relationship
  traversal (depends_on, complemented_by, alternative_to) instead of flat name/tag
  matching. Call skill_graph_search() tool directly.
version: 1.0.0
author: Hauzer S. Lee
license: MIT
metadata:
  hermes:
    tags:
    - hermes
    - skills
    - discovery
    - graph
    - plugin
    related_skills:
    - intent-router
category: hermes
---


# Skill Graph

The **skill-graph** plugin maintains a knowledge graph of all installed skills
and their typed relationships. When you can't find the right skill by name or
description, or when you suspect a flat search would miss relevant skills, use
``skill_graph_search()`` instead of ``skills_list()``.

## When to Use

- You have a vague intent but don't know the skill name
- Flat skill lists would miss implicit relationships (e.g. "python" → github-code-review via supports_language edge)
- You want to discover skills that complement each other
- The user's request involves multiple domains (e.g. "deploy and monitor a Python API")
- You're choosing between alternatives and want to see how they relate

## Slash Commands

The plugin registers ``/skill-graph`` with subcommands:

- ``/skill-graph search <query>``  Search skills by intent
- ``/skill-graph list``            List all skills in graph (name + description)
- ``/skill-graph status``          Show graph stats (counts, DB size)
- ``/skill-graph config``          Show configuration (paths, scanned dirs)
- ``/skill-graph rebuild``         Force full graph rebuild

## Tools

- ``skill_graph_search(query)`` — Find skills by intent (PREFERRED over skills_list())
- ``skill_load(name)`` — Load a skill's full content (alternative to skill_view())

## Configuration

Add extra skill directories in ``config.yaml``:

```yaml
skills:
  config:
    skill-graph:
      source_dirs:
        - ~/path/to/extra/skills
```

The default ``~/.hermes/skills/`` is always scanned.

## How to Use

```python
# Basic intent search
skill_graph_search(query="Python code review", limit=10)
# Returns: [{name, category, description, relevance, relationship_chain, ...}]

# Multi-domain
skill_graph_search(query="deploy kubernetes with monitoring")
# Expands via graph edges to find related skills

# Iterative refinement
skill_graph_search(query="database performance")
# Then drill into specific results with skill_view()
```

## Understanding Results

Each result has a ``relevance`` field:

| Value | Meaning |
|-------|---------|
| ``direct`` | FTS5 match in name/description/tags |
| ``tag_match`` | Tag-based match |
| ``expansion`` | Graph traversal from another matched skill |

The ``relationship_chain`` array shows *why* a skill was found:

```
  github-code-review --(supports_language)--> python: full support
  systematic-debugging --(complemented_by)--> github-code-review
```

The ``edges_between_results`` array shows how the returned skills relate to
each other, helping you choose which to load together.

## Adding Relations to Skills

To make the graph smarter, add a ``relations`` field to any SKILL.md:

```yaml
metadata:
  hermes:
    relations:
      - type: depends_on
        target: systematic-debugging
        properties:
          reason: "必须先定位根因再修"
          strength: strong
      - type: complemented_by
        target: github-pr-workflow
        properties:
          reason: "review 完直接开 PR"
```

### Relation Types

| Type | Meaning | Auto-reverse? |
|------|---------|---------------|
| ``depends_on`` | This skill needs another to work | → ``supported_by`` |
| ``supported_by`` | Another skill supports this one | → ``depends_on`` |
| ``complemented_by`` | Works well with another skill | Symmetric (no reverse) |
| ``alternative_to`` | Alternative approach for same task | Symmetric |
| ``similar_to`` | Semantically similar | Symmetric |
| ``supersedes`` | Replaces an older skill | → ``superseded_by`` |
| ``used_in_workflow`` | Part of a larger workflow | Symmetric |
| ``belongs_to_domain`` | Domain category relationship | Symmetric |

### Properties

The ``properties`` field supports any attributes. Common ones:

- ``reason``: Human-readable explanation of the relationship
- ``strength``: ``strong`` / ``medium`` / ``weak``
- ``level``: ``full`` / ``partial`` for capability relationships
- ``source``: ``legacy_related_skills`` (auto-converted), ``manual``

## Fallback Behavior

If the plugin is not installed or ``skill_graph_search`` is unavailable,
fall back to the standard progressive disclosure:

1. ``skills_list()`` → browse by category
2. ``skill_view(name)`` → load full content
3. Manual judgment

## Pitfalls

- The graph is rebuilt on every session start — changes to SKILL.md take
  effect after restarting Hermes (``/reset`` or exit+relaunch).
- Legacy ``related_skills`` fields are auto-converted to ``similar_to``
  relations. Ensure they're accurate.
- Chinese text is indexed by FTS5 but doesn't benefit from porter stemming.
  Use explicit tags and relations for Chinese-dominated skills.

## Creating Skills

When creating a new skill with `skill_manage(action='create', ...)`,
Hermes writes it to `~/.hermes/skills/<name>/`.

For PS users: after creating a skill, use `personal-suite-skills-manager`
to move it into the PS repo (git-tracked, graph-indexed, no symlink).
