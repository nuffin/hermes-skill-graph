# Skill Graph — Knowledge Graph Skill Discovery

The skill-graph plugin replaces flat name/tag skill matching with typed
relationship traversal.  It is the recommended way to discover and load
skills in Hermes, replacing the legacy approach of symlinking every skill
into ``~/.hermes/skills/``.

## Architecture

```
Plugin (skill-graph)                Companion Skill (skill-graph)
  ┌──────────────────────┐          ┌──────────────────────────┐
  │ skill_graph_search() │          │ /skill-graph rebuild     │
  │ skill_load()         │          │ /skill-graph status      │
  │ /skill-graph status  │          │ Usage guidance (fallback) │
  │ /skill-graph rebuild │          └──────────────────────────┘
  └──────────────────────┘
            │
            ▼
  SQLite + FTS5 Graph
  ~/.hermes/personal/skill-graph.db
```

The plugin registers two tools available to the agent:

- **``skill_graph_search(query)``** — Find skills by intent using
  FTS5 + typed-relationship traversal.  **Preferred over ``skills_list()``.**
- **``skill_load(name)``** — Load a skill's full SKILL.md content by name.
  Alternative to ``skill_view()`` that works with skills in any configured
  directory.

## Installation

Only the plugin needs to be installed.  Skills are discovered dynamically
through the graph — they do **not** need to be symlinked into
``~/.hermes/skills/``.

### For new worker profiles

``role-admin.sh create <profile> <role>`` handles this automatically:

1. Links the ``skill-graph`` plugin (along with other universal plugins)
   into the profile's ``plugins/`` directory
2. Writes a ``source_dirs`` config entry pointing to the PS repo's ``skills/``
   directory into the profile's ``config.yaml``
3. Does **not** symlink individual skills

### For the default profile

If you want the graph to index PS skills from the default profile, add this
to your ``~/.hermes/config.yaml``:

```yaml
skills:
  config:
    skill-graph:
      source_dirs:
        - ~/studio/hermes/projects/hermes-personal-suite/skills
```

### Manual install (any profile)

```bash
# 1. Ensure the plugin is linked
ln -sfn ~/studio/hermes/projects/hermes-personal-suite/plugins/skill-graph \
  ~/.hermes/plugins/skill-graph

# 2. Add source_dirs to the profile's config.yaml (see above)
```

## Configuration

| Key | Type | Description |
|-----|------|-------------|
| ``skills.config.skill-graph.source_dirs`` | List of paths | Extra directories to scan for SKILL.md files |

The default ``~/.hermes/skills/`` is always scanned.  ``source_dirs`` adds
additional directories like the PS repo's ``skills/`` folder.

## Usage

### In a chat session

```
# The agent automatically uses skill_graph_search to find skills.
# You can also invoke the slash command:

/skill-graph status     → Show graph stats
/skill-graph rebuild    → Force full rebuild
```

### Agent behaviour

On session start, the plugin injects a discovery protocol message telling
the agent to prefer ``skill_graph_search()`` over ``skills_list()``.  The
companion skill (``/skill-graph``) is available as a fallback if the
plugin's injection doesn't work.

### Adding relations to skills

To make the graph smarter, add typed relationships to any SKILL.md:

```yaml
metadata:
  hermes:
    relations:
      - type: complemented_by
        target: another-skill
        properties:
          reason: "why they work together"
          strength: strong
```

See ``docs/relations-format.md`` in the standalone project for the full spec.

## Comparison: Old vs New

| Aspect | Old (symlink) | New (skill-graph) |
|--------|---------------|-------------------|
| Installation | ``install.sh --link`` copies 177 symlinks | Plugin only; skills discovered dynamically |
| System prompt | 177 skill names + descriptions | ~20 Hermes built-in skills only |
| Discovery | ``skills_list()`` — flat list | ``skill_graph_search()`` — graph traversal |
| Loading | ``skill_view(name)`` | ``skill_load(name)`` |
| Relations | ``related_skills: [...]`` (flat) | Typed: ``depends_on``, ``complemented_by``, etc. |
| Cross-profile | Each profile gets its own symlinks | Single shared ``source_dirs`` config |
| DB location | N/A | ``~/.hermes/personal/skill-graph.db`` |

## Troubleshooting

**Q: graph shows 0 skills**

Run ``/skill-graph status`` to trigger an initial sync.  If still 0, check:
- ``source_dirs`` is correctly configured
- The specified directory exists and contains ``<skill-name>/SKILL.md`` files
- ``~/.hermes/skills/`` exists (Hermes always places built-in skills here)

**Q: agent still uses skills_list() instead of skill_graph_search()**

The discovery protocol is injected on session start.  If it didn't fire
(e.g. resumed session), load the companion skill manually:
``/skill-graph search "what you need"``

**Q: need to force a full rebuild after changing SKILL.md files**

``/skill-graph rebuild`` — or delete the DB:
``rm ~/.hermes/personal/skill-graph.db``

## Files

| File | Purpose |
|------|---------|
| ``plugins/skill-graph/plugin.yaml`` | Plugin manifest |
| ``plugins/skill-graph/__init__.py`` | Full implementation (~870 lines) |
| ``skills/skill-graph/SKILL.md`` | Companion skill (fallback guidance) |
| ``scripts/patch-skill-frontmatter.py`` | Auto-fix missing frontmatter tags |

## Standalone Project

The same plugin is available as a standalone project at
``~/studio/hermes/projects/hermes-skill-graph/`` — can be used without PS.
See its ``README.md`` for full docs.
