# Changelog

## 1.0.0 — 2026-06-21

Initial release.

- **Plugin:** SQLite + FTS5 knowledge graph engine with `skill_graph_search()` tool
- **Plugin:** `on_session_start` hook for full graph rebuild
- **Plugin:** `post_tool_call` hook for incremental update on `skill_manage` create/edit/patch
- **Plugin:** 8 relation types, auto-reverse edges for directed relations
- **Plugin:** Legacy `related_skills` auto-conversion to `similar_to` edges
- **Skill:** Companion skill teaching agent when/how to use graph search
- **Install:** Standalone `install.sh` with `--uninstall` support
- **Docs:** Full `relations-format.md` specification
