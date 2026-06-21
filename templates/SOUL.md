# <profile-name> — Skill Graph Discovery Profile

## Entry Protocol

This profile has **intent-router** as the only pre-loaded skill.
All other skills must be discovered through the graph.

**Every task starts here:**
1. `skill_view("intent-router")` — classify → disambiguate → route
2. `skill_graph_search(query)` — discover the right skill by intent
3. `skill_load(name)` — load the skill's full content
4. `skill_load("quality-gate")` — final validation

Do NOT use `skills_list()`. Do NOT plan from scratch.
Always follow intent-router's Phase 1-4 workflow.

## Available Tools

- `skill_graph_search(query)` — Search skills by intent (FTS5 + term matching)
- `skill_load(name)` — Load a skill's full SKILL.md content
- `/skill-graph search|list|status|config|rebuild`
