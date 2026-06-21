---
name: skill-graph
description: "Skill knowledge graph — intent classification, routing, and discovery. Load this skill first to classify user intent and find the right skill via skill_graph_search()."
version: 2.0.0
author: Hauzer S. Lee
license: MIT
category: hermes
metadata:
  hermes:
    tags:
      - hermes
      - skills
      - discovery
      - graph
      - intent-router
      - 意图路由器
      - routing
      - classification
---

# Skill Graph — Intent Routing + Discovery

Load this skill FIRST for every user input. It classifies the intent and
tells you which skill to search for via the knowledge graph.

## Protocol

```
1. skill_load("skill-graph") → read the routing tables below
2. Classify the input using Phase 1
3. Find the matching entry in Phase 4 routing table
4. Call skill_graph_search() with the query from that entry
5. skill_load("result-name") → execute
6. skill_load("quality-gate") → final validation

Never use find/ls/cat before step 4.
Never plan from scratch — the graph has the skills you need.
```

## Phase 1: Input Classification

| Type | Description | Initial route |
|------|-------------|---------------|
| 1A Task mgmt | Task name/path/hash mentioned | `skill_graph_search("task workflow")` |
| 1B Execute | "run"/"do it"/"commit" | → Phase 2, then Phase 4 |
| 1C Design discussion | Suggestion / proposal / question | Discuss only, don't execute |
| 1D Info query | "What is"/"show me"/"check project" | **Search for a skill first** |
| 1E Meta | Change config/skill/memory | Handle directly |

**Key: 1D info queries must not just "answer directly"**. Many info
queries ("show the project", "explain the architecture") have a matching
domain skill. Search the graph first, then answer following its guidance.

## Phase 2: Intent Resolution (1B only)

| Signal | Action |
|--------|--------|
| "commit" | Git workflow (commit, no push) |
| "push" | Allow push |
| "stop" / "wait" | Stop immediately, wait silently |
| All done | `skill_load("quality-gate")` |

## Phase 3: Pre-flight Check

| Target | Tool | Check |
|--------|------|-------|
| Task directory | task-framework tools | Read TASK_MEMORY.md first |
| Git repo | Git commands | Pre-change sync |
| Skill file | skill_manage | — |
| Rule file | read_file / write_file | — |

## Phase 4: Routing

After classification, search with intent keywords — NOT the user's
exact words:

| User said | Don't search | Search instead |
|-----------|-------------|----------------|
| "show the eir project" | "show the eir project" | `skill_graph_search("project management framework overview")` |
| "what's wrong with this bug" | "what's wrong" | `skill_graph_search("debug python systematic")` |
| "help design the database" | "help design the database" | `skill_graph_search("data model design naming conventions")` |

### Routing table

| User intent | Search query |
|------------|--------------|
| View / understand project structure | `skill_graph_search("project management framework overview")` |
| Create / manage tasks | `skill_graph_search("task management and workflow")` |
| Git operations | `skill_graph_search("git commit and push workflow")` |
| Code review | `skill_graph_search("code review pull request")` |
| Write PRD / requirements | `skill_graph_search("product requirements document writing")` |
| Debug a program | `skill_graph_search("debug python systematic")` |
| Design / prototype | `skill_graph_search("design prototype mockup")` |
| Architecture analysis | `skill_graph_search("architecture discovery reverse engineering")` |
| Domain research | `skill_graph_search("domain analysis market research")` |
| Deploy a service | `skill_graph_search("deploy service docker")` |
| Video production | `skill_graph_search("video production screen recording")` |
| Database design | `skill_graph_search("data model design naming conventions")` |

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

## Understanding Results

Each search result has a ``relevance`` field:

| Value | Meaning |
|-------|---------|
| ``direct`` | FTS5 match in name/description/tags |
| ``tag_match`` | Tag-based match |
| ``expansion`` | Graph traversal from another matched skill |
| ``term_match`` | Auto-extracted keyword match (English + Chinese) |

## Adding Relations to Skills

To make the graph smarter, add a ``relations`` field to any SKILL.md:

```yaml
metadata:
  hermes:
    relations:
      - type: depends_on
        target: systematic-debugging
        properties:
          reason: "must find root cause before fixing"
          strength: strong
```

### Relation Types

| Type | Meaning | Auto-reverse? |
|------|---------|---------------|
| ``depends_on`` | This skill needs another to work | → ``supported_by`` |
| ``supported_by`` | Another skill supports this one | → ``depends_on`` |
| ``complemented_by`` | Works well with another skill | Symmetric |
| ``alternative_to`` | Alternative approach for same task | Symmetric |
| ``similar_to`` | Semantically similar | Symmetric |
| ``supersedes`` | Replaces an older skill | → ``superseded_by`` |
| ``used_in_workflow`` | Part of a larger workflow | Symmetric |
| ``belongs_to_domain`` | Domain category relationship | Symmetric |

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

For standalone project users: after creating, move the skill to
`$HERMES_HOME/skill-graph/agent-created/` and run
`/skill-graph rebuild` to index it without bloating the system prompt.
