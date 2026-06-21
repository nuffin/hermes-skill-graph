"""
Skill Graph plugin — knowledge graph for skills discovery.

Builds a SQLite graph from SKILL.md relations, exposes a custom tool
``skill_graph_search`` that the agent can call to find skills by intent,
and maintains the graph incrementally across sessions.

SKILL.md relations format (frontmatter):
    metadata:
      hermes:
        relations:
          - type: depends_on
            target: another-skill
            properties:
              reason: "why"
              strength: strong|medium|weak
"""

from __future__ import annotations
import json
import logging
import os
import re
import sqlite3
import threading
import time
import yaml
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Constants ───────────────────────────────────────────────────────────────

DEFAULT_RELATION_TYPES = {
    "depends_on", "supported_by", "alternative_to", "complemented_by",
    "similar_to", "belongs_to_domain", "used_in_workflow", "supersedes",
}

GRAPH_DB_FILENAME = "skill-graph.db"
GRAPH_LOCK = threading.Lock()
_initialized = False

# ── SQLite schema ──────────────────────────────────────────────────────────

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS skill_nodes (
    name        TEXT PRIMARY KEY,
    category    TEXT DEFAULT '',
    description TEXT DEFAULT '',
    tags        TEXT DEFAULT '[]',      -- JSON array
    file_path   TEXT DEFAULT '',
    content_hash TEXT DEFAULT '',
    last_parsed REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS skill_edges (
    source      TEXT NOT NULL REFERENCES skill_nodes(name),
    target      TEXT NOT NULL REFERENCES skill_nodes(name),
    rel_type    TEXT NOT NULL,
    properties  TEXT DEFAULT '{}',       -- JSON dict
    PRIMARY KEY (source, target, rel_type)
);

CREATE INDEX IF NOT EXISTS idx_edges_source ON skill_edges(source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON skill_edges(target);
CREATE INDEX IF NOT EXISTS idx_edges_type   ON skill_edges(rel_type);

CREATE VIRTUAL TABLE IF NOT EXISTS skill_fts USING fts5(
    name, category, description, tags,
    tokenize='porter unicode61',
    content=''
);
"""

# ── Database helpers ────────────────────────────────────────────────────────


def _db_path() -> Path:
    """Return path to graph DB under the active Hermes home."""
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    return hermes_home / "personal" / GRAPH_DB_FILENAME


def _get_conn() -> sqlite3.Connection:
    """Get a thread-safe connection (one per thread via check_same_thread=False)."""
    db_path = _db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    """Ensure schema exists."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


# ── SKILL.md parser ────────────────────────────────────────────────────────


def _find_all_skills_dirs() -> list[Path]:
    """Return all directories that might contain SKILL.md files."""
    hermes_home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    dirs = []

    # Primary skills directory
    primary = hermes_home / "skills"
    if primary.exists():
        dirs.append(primary)

    # Profile-specific skills
    profiles_dir = hermes_home / "profiles"
    if profiles_dir.exists():
        for pdir in profiles_dir.iterdir():
            sdir = pdir / "skills"
            if sdir.exists():
                dirs.append(sdir)

    # External skill directories from config
    try:
        from hermes_cli.config import load_config
        config = load_config()
        ext_dirs = config.get("skills", {}).get("external_dirs", [])
        for ed in ext_dirs:
            p = Path(os.path.expandvars(os.path.expanduser(str(ed))))
            if p.exists():
                dirs.append(p)
    except Exception:
        pass

    return dirs


def _scan_skill_mds(skill_dirs: list[Path]) -> list[tuple[str, Path]]:
    """Scan all skill directories for SKILL.md files.
    
    Returns list of (skill_name, skill_md_path).
    """
    results: list[tuple[str, Path]] = []
    seen_names: set[str] = set()

    for base_dir in skill_dirs:
        if not base_dir.exists():
            continue
        # Category-first layout: <cat>/<name>/SKILL.md
        for cat_dir in base_dir.iterdir():
            if not cat_dir.is_dir() or cat_dir.name.startswith("."):
                continue
            # Either flat layout: <name>/SKILL.md
            skill_md = cat_dir / "SKILL.md"
            if skill_md.exists():
                name = cat_dir.name
                if name not in seen_names:
                    seen_names.add(name)
                    results.append((name, skill_md))
                continue
            # Or nested (Hermes style): <cat>/<name>/SKILL.md
            for name_dir in cat_dir.iterdir():
                if not name_dir.is_dir() or name_dir.name.startswith("."):
                    continue
                skill_md = name_dir / "SKILL.md"
                if skill_md.exists():
                    name = name_dir.name
                    if name not in seen_names:
                        seen_names.add(name)
                        results.append((name, skill_md))
    return results


def _parse_skill_md(path: Path) -> dict[str, Any]:
    """Parse SKILL.md and extract metadata for the graph.
    
    Returns dict with keys: name, category, description, tags, relations, content_hash
    """
    result: dict[str, Any] = {
        "name": path.parent.name,
        "category": "",
        "description": "",
        "tags": [],
        "relations": [],
        "content_hash": "",
    }

    try:
        content = path.read_text(encoding="utf-8", errors="replace")

        # Quick hash for change detection
        result["content_hash"] = str(hash(content))

        # Parse YAML frontmatter
        content_str = content.lstrip("\ufeff")  # strip BOM
        if content_str.startswith("---"):
            end = content_str.find("---", 3)
            if end != -1:
                frontmatter = content_str[3:end].strip()
                try:
                    meta = yaml.safe_load(frontmatter) or {}
                except yaml.YAMLError:
                    meta = {}

                result["name"] = meta.get("name", result["name"])
                result["category"] = meta.get("category", "") or \
                    meta.get("metadata", {}).get("hermes", {}).get("category", "")
                result["description"] = meta.get("description", "")

                # Tags
                tags = meta.get("metadata", {}).get("hermes", {}).get("tags", [])
                if isinstance(tags, str):
                    tags = [t.strip() for t in tags.split(",") if t.strip()]
                result["tags"] = list(tags) if isinstance(tags, list) else []

                # Relations (our extension)
                relations = meta.get("metadata", {}).get("hermes", {}).get("relations", [])
                if isinstance(relations, list):
                    result["relations"] = relations

                # Also read legacy related_skills
                related = meta.get("metadata", {}).get("hermes", {}).get("related_skills", [])
                if isinstance(related, str):
                    related = [t.strip() for t in related.split(",") if t.strip()]
                if isinstance(related, list):
                    for rs in related:
                        # Convert legacy related_skills to similar_to relations
                        if not any(r.get("target") == rs for r in result["relations"]):
                            result["relations"].append({
                                "type": "similar_to",
                                "target": rs,
                                "properties": {"source": "legacy_related_skills"},
                            })
    except Exception as e:
        logger.debug("Failed to parse %s: %s", path, e)

    return result


def _update_graph(conn: sqlite3.Connection) -> int:
    """Full refresh: scan all skills dirs, update graph, return count of skills."""
    skill_dirs = _find_all_skills_dirs()
    skills = _scan_skill_mds(skill_dirs)

    # Deduplicate: when same skill name appears in multiple dirs,
    # prefer the one from the primary ~/.hermes/skills/ dir, then first seen
    deduped: dict[str, Path] = {}
    primary_hint = str(Path.home() / ".hermes" / "skills")
    for name, path in skills:
        if name not in deduped:
            deduped[name] = path
        else:
            # If current is in primary and existing is not, replace
            if str(path).startswith(primary_hint) and \
               not str(deduped[name]).startswith(primary_hint):
                deduped[name] = path

    now = time.time()

    # Get existing nodes
    existing = set()
    for row in conn.execute("SELECT name, content_hash FROM skill_nodes"):
        existing.add(row["name"])

    # Upsert skills
    parsed_count = 0
    for name, path in deduped.items():
        info = _parse_skill_md(path)
        tags_json = json.dumps(info["tags"], ensure_ascii=False)
        desc = info["description"]
        cat = info["category"]

        conn.execute(
            """INSERT OR REPLACE INTO skill_nodes
               (name, category, description, tags, file_path, content_hash, last_parsed)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, cat, desc, tags_json, str(path), info["content_hash"], now),
        )
        parsed_count += 1

        # Remove old edges for this skill
        conn.execute("DELETE FROM skill_edges WHERE source = ?", (name,))

        # Insert edges from relations
        for rel in info.get("relations", []):
            rel_type = rel.get("type", "similar_to")
            target = rel.get("target", "")
            props = rel.get("properties", {})
            if not target:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO skill_edges (source, target, rel_type, properties) VALUES (?, ?, ?, ?)",
                (name, target, rel_type, json.dumps(props, ensure_ascii=False)),
            )
            # Auto-generate reverse edge for directed relations
            reverse_type = _reverse_type(rel_type)
            if reverse_type:
                reverse_props = {"inferred": True, "reason": f"reverse of {rel_type}"}
                conn.execute(
                    "INSERT OR IGNORE INTO skill_edges (source, target, rel_type, properties) VALUES (?, ?, ?, ?)",
                    (target, name, reverse_type, json.dumps(reverse_props)),
                )

    # Remove stale nodes (skills that no longer exist)
    current_names = set(deduped.keys())
    stale = existing - current_names
    for name in stale:
        conn.execute("DELETE FROM skill_edges WHERE source = ? OR target = ?", (name, name))
        conn.execute("DELETE FROM skill_nodes WHERE name = ?", (name,))
        conn.execute("DELETE FROM skill_fts WHERE name = ?", (name,))

    conn.commit()
    logger.info(
        "Skill graph refreshed: %d skills parsed, %d removed, %d total",
        parsed_count, len(stale), len(deduped),
    )

    # Rebuild FTS index
    conn.execute("DELETE FROM skill_fts")
    for row in conn.execute(
        "SELECT name, category, description, tags FROM skill_nodes"
    ):
        tags_text = " ".join(json.loads(row["tags"])) if row["tags"] else ""
        conn.execute(
            "INSERT INTO skill_fts (name, category, description, tags) VALUES (?, ?, ?, ?)",
            (row["name"], row["category"], row["description"], tags_text),
        )
    conn.commit()

    return len(deduped)


def _update_single_skill(conn: sqlite3.Connection, skill_name: str) -> bool:
    """Re-parse a single skill and update its node + edges in the graph.
    
    Returns True if the skill was found and updated.
    """
    skill_dirs = _find_all_skills_dirs()
    skills = _scan_skill_mds(skill_dirs)

    # Find the skill by name (prefer primary dir)
    skill_path: Path | None = None
    for name, path in skills:
        if name == skill_name:
            if skill_path is None:
                skill_path = path
            else:
                if str(path).startswith(str(Path.home() / ".hermes" / "skills")):
                    skill_path = path
                    break

    if skill_path is None:
        logger.debug("skill-graph: skill '%s' not found on disk, skipping", skill_name)
        return False

    info = _parse_skill_md(skill_path)
    now = time.time()
    tags_json = json.dumps(info["tags"], ensure_ascii=False)

    conn.execute(
        """INSERT OR REPLACE INTO skill_nodes
           (name, category, description, tags, file_path, content_hash, last_parsed)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (skill_name, info["category"], info["description"],
         tags_json, str(skill_path), info["content_hash"], now),
    )

    conn.execute("DELETE FROM skill_edges WHERE source = ?", (skill_name,))

    for rel in info.get("relations", []):
        rel_type = rel.get("type", "similar_to")
        target = rel.get("target", "")
        props = rel.get("properties", {})
        if not target:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO skill_edges (source, target, rel_type, properties) VALUES (?, ?, ?, ?)",
            (skill_name, target, rel_type, json.dumps(props, ensure_ascii=False)),
        )
        reverse_type = _reverse_type(rel_type)
        if reverse_type:
            reverse_props = {"inferred": True, "reason": f"reverse of {rel_type}"}
            conn.execute(
                "INSERT OR IGNORE INTO skill_edges (source, target, rel_type, properties) VALUES (?, ?, ?, ?)",
                (target, skill_name, reverse_type, json.dumps(reverse_props)),
            )

    # Update FTS for this skill
    tags_text = " ".join(info.get("tags", []))
    conn.execute("DELETE FROM skill_fts WHERE name = ?", (skill_name,))
    conn.execute(
        "INSERT INTO skill_fts (name, category, description, tags) VALUES (?, ?, ?, ?)",
        (skill_name, info.get("category", ""), info.get("description", ""), tags_text),
    )

    conn.commit()
    logger.debug("skill-graph: updated single skill '%s' (%s)", skill_name, skill_path)
    return True


def _reverse_type(rel_type: str) -> str | None:
    """Return the reverse relation type, or None if symmetric."""
    mapping = {
        "depends_on": "supported_by",
        "supported_by": "depends_on",
        "supersedes": "superseded_by",
        "superseded_by": "supersedes",
    }
    return mapping.get(rel_type)


# ── Graph search ────────────────────────────────────────────────────────────


def _search_graph(query: str, conn: sqlite3.Connection, limit: int = 10) -> list[dict[str, Any]]:
    """Search the skill graph by intent query.
    
    Strategy:
    1. FTS5 full-text search on name, description, tags
    2. Entity extraction from query → expand via graph edges
    3. Combine + rank results
    """
    results: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()

    # Phase 1: FTS5 direct search
    fts_query = _fts_query(query)
    if fts_query:
        cursor = conn.execute(
            """SELECT n.name, n.category, n.description, n.tags, n.file_path
               FROM skill_fts f
               JOIN skill_nodes n ON f.name = n.name
               WHERE skill_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (fts_query, limit * 2),
        )
        for row in cursor:
            name = row["name"]
            seen.add(name)
            tags = json.loads(row["tags"]) if row["tags"] else []
            results[name] = {
                "name": name,
                "category": row["category"],
                "description": row["description"],
                "tags": tags,
                "file_path": row["file_path"],
                "relevance": "direct",
                "relationship_chain": [],
                "score": 1.0,
            }

    # Phase 2: Graph expansion — follow edges from matched skills
    expansion_queue = list(seen)
    while expansion_queue and len(results) < limit * 3:
        current = expansion_queue.pop(0)
        cursor = conn.execute(
            """SELECT e.target, e.rel_type, e.properties, n.category, n.description
               FROM skill_edges e
               JOIN skill_nodes n ON e.target = n.name
               WHERE e.source = ?
               ORDER BY e.rel_type
               LIMIT 5""",
            (current,),
        )
        for row in cursor:
            target = row["target"]
            if target in seen:
                continue
            seen.add(target)
            props = json.loads(row["properties"]) if row["properties"] else {}
            rel_type = row["rel_type"]
            reason = props.get("reason", f"via {rel_type}")

            results[target] = {
                "name": target,
                "category": row["category"] or "",
                "description": row["description"] or "",
                "tags": [],
                "file_path": "",
                "relevance": "expansion",
                "relationship_chain": [f"{current} --({rel_type})--> {target}: {reason}"],
                "score": 0.5,  # lower score than direct matches
            }
            expansion_queue.append(target)

    # Also search by tag matches
    terms = _extract_terms(query)
    for term in terms:
        cursor = conn.execute(
            """SELECT name FROM skill_nodes WHERE instr(tags, ?) > 0""",
            (json.dumps(term),),
        )
        for row in cursor:
            if row["name"] not in seen:
                seen.add(row["name"])
                # Fetch full info
                info = _get_node_info(conn, row["name"])
                if info:
                    info["relevance"] = "tag_match"
                    info["score"] = 0.7
                    results[info["name"]] = info

    # Sort: direct matches first, then tag matches, then graph expansion
    sorted_results = sorted(results.values(), key=lambda r: -r["score"])

    return sorted_results[:limit]


def _fts_query(query: str) -> str:
    """Convert a natural language query to an FTS5 query string."""
    # Strip punctuation, keep meaningful terms
    terms = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff_-]+", query.lower())
    # FTS5 supports AND as default, but for Chinese we need OR for broader recall
    # For English, AND works better
    has_ascii = any(t.isascii() for t in terms)
    if has_ascii:
        return " AND ".join(t for t in terms if len(t) > 1)
    return " OR ".join(t for t in terms if len(t) > 1) if terms else ""


def _extract_terms(query: str) -> list[str]:
    """Extract meaningful search terms from a query string."""
    terms = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff_-]+", query.lower())
    return [t for t in terms if len(t) > 1]


def _get_node_info(conn: sqlite3.Connection, name: str) -> dict[str, Any] | None:
    """Fetch full node info from the database."""
    cursor = conn.execute(
        "SELECT name, category, description, tags, file_path FROM skill_nodes WHERE name = ?",
        (name,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {
        "name": row["name"],
        "category": row["category"],
        "description": row["description"],
        "tags": json.loads(row["tags"]) if row["tags"] else [],
        "file_path": row["file_path"],
    }


# ── Plugin hooks ────────────────────────────────────────────────────────────

_graph_lock = threading.Lock()
_global_conn: sqlite3.Connection | None = None
_global_initialized = False


def _ensure_graph() -> sqlite3.Connection:
    """Lazy-init the graph DB and refresh if stale."""
    global _global_conn, _global_initialized

    if _global_conn is None:
        conn = _get_conn()
        _init_db(conn)
        _global_conn = conn

    # Always refresh on first access per session
    if not _global_initialized:
        with _graph_lock:
            if not _global_initialized:
                _update_graph(_global_conn)
                _global_initialized = True

    return _global_conn


# ── Tool handler ────────────────────────────────────────────────────────────


def _handle_skill_graph_search(**kw) -> str:
    """Handle skill_graph_search tool call."""
    args = kw.get("args", kw)
    if isinstance(args, dict):
        query = args.get("query", "")
        limit = int(args.get("limit", 10))
    else:
        query = ""
        limit = 10

    if not query:
        return json.dumps({
            "success": False,
            "error": "query is required",
            "hint": "Pass a query string describing what you want to do",
        })

    try:
        conn = _ensure_graph()

        with _graph_lock:
            results = _search_graph(query, conn, limit=limit)

            # Get total skill count
            total = conn.execute("SELECT COUNT(*) FROM skill_nodes").fetchone()[0]

            # Get any edges connecting the results
            result_names = [r["name"] for r in results]
            edges_between = []
            if len(result_names) > 1:
                placeholders = ",".join("?" for _ in result_names)
                cursor = conn.execute(
                    f"""SELECT source, target, rel_type, properties
                       FROM skill_edges
                       WHERE source IN ({placeholders})
                         AND target IN ({placeholders})
                       ORDER BY rel_type""",
                    result_names + result_names,
                )
                for row in cursor:
                    edges_between.append({
                        "source": row["source"],
                        "target": row["target"],
                        "type": row["rel_type"],
                        "properties": json.loads(row["properties"]) if row["properties"] else {},
                    })

        return json.dumps({
            "success": True,
            "query": query,
            "results": results,
            "edges_between_results": edges_between,
            "total_skills_in_graph": total,
            "result_count": len(results),
            "hint": "Use skill_view(name) to load full skill content. "
                    "Edges_between_results shows relationships connecting the results.",
        }, ensure_ascii=False)

    except Exception as e:
        logger.exception("skill_graph_search failed")
        return json.dumps({
            "success": False,
            "error": str(e),
        })


# ── Plugin entry point ──────────────────────────────────────────────────────


def register(ctx):
    """Register the skill-graph plugin."""

    # Register custom tool
    ctx.register_tool(
        name="skill_graph_search",
        toolset="skills",
        schema={
            "name": "skill_graph_search",
            "description": (
                "Search the skill knowledge graph by intent. "
                "Parses SKILL.md relations (depends_on, complemented_by, "
                "alternative_to, etc.) and uses full-text + graph traversal "
                "to find the most relevant skills. Returns relationship chains "
                "showing how skills connect."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of what you want to do "
                                       "(e.g. 'Python code review', 'deploy kubernetes', "
                                       "'database performance tuning')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        handler=_handle_skill_graph_search,
        description="Knowledge-graph skill search by intent",
        check_fn=None,
    )

    # Register on_session_start hook to refresh the graph
    def _on_session_start(**kw):
        global _global_initialized
        try:
            conn = _ensure_graph()
            # Full refresh every session start
            with _graph_lock:
                count = _update_graph(conn)
                _global_initialized = True
            logger.info("Skill graph ready: %d skills", count)
        except Exception:
            logger.exception("skill-graph: on_session_start failed")

    ctx.register_hook("on_session_start", _on_session_start)

    # Register post_tool_call hook to catch skill_manage create/edit/patch
    def _on_post_tool_call(**kw):
        """Detect skill_manage calls and update the graph incrementally."""
        tool_name = kw.get("tool_name", "")
        if tool_name != "skill_manage":
            return

        args = kw.get("args", {})
        if not isinstance(args, dict):
            return

        action = args.get("action", "")
        if action not in ("create", "edit", "patch"):
            return

        skill_name = args.get("name", "")
        if not skill_name:
            return

        # Incremental update: re-parse just this one skill
        try:
            conn = _ensure_graph()
            with _graph_lock:
                updated = _update_single_skill(conn, skill_name)
            if updated:
                logger.info("skill-graph: updated skill '%s' after %s", skill_name, action)
        except Exception:
            logger.exception("skill-graph: post_tool_call failed for skill '%s'", skill_name)

    ctx.register_hook("post_tool_call", _on_post_tool_call)

    logger.info(
        "skill-graph plugin registered: tool=skill_graph_search, "
        "hooks=on_session_start + post_tool_call"
    )
