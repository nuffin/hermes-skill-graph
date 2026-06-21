#!/usr/bin/env bash
#
# install.sh — Install hermes-skill-graph plugin + skill for Hermes Agent
#
# Usage:
#   bash install.sh              # Symlink from project dir into Hermes
#   bash install.sh --uninstall  # Remove symlinks
#   bash install.sh --help       # Show help
#
# What it does:
#   plugin/  →  ~/.hermes/plugins/skill-graph/
#   skill/   →  ~/.hermes/skills/skill-graph/
#   db at    ~/.hermes/personal/skill-graph.db  (created at runtime)

set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────────────
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'
C_CYAN='\033[0;36m'
C_GRAY='\033[0;90m'
C_RED='\033[0;31m'

info()  { echo -e "  ${C_CYAN}→${C_RESET} $1"; }
ok()    { echo -e "  ${C_GREEN}✓${C_RESET} $1"; }
warn()  { echo -e "  ${C_YELLOW}⚠${C_RESET} $1"; }
error() { echo -e "  ${C_RED}✗${C_RESET} $1"; }

# ── Paths ───────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"

PLUGIN_SRC="$SCRIPT_DIR/plugin/skill-graph"
SKILL_SRC="$SCRIPT_DIR/skill/skill-graph"

PLUGIN_TARGET="$HERMES_HOME/plugins/skill-graph"
SKILL_TARGET="$HERMES_HOME/skills/skill-graph"

# ── Help ────────────────────────────────────────────────────────────────────
show_help() {
    cat <<EOF
${C_BOLD}hermes-skill-graph${C_RESET} — Install knowledge-graph skill discovery for Hermes Agent

${C_BOLD}USAGE${C_RESET}
    bash install.sh              Install (symlink) plugin + skill
    bash install.sh --uninstall  Remove symlinks (keep DB)
    bash install.sh --help       This message

${C_BOLD}WHAT IT DOES${C_RESET}
    Links plugin/skill-graph/  →  \$HERMES_HOME/plugins/skill-graph/
    Links skill/skill-graph/   →  \$HERMES_HOME/skills/skill-graph/

    After install, restart Hermes (/reset or exit+relaunch).
    The plugin builds the graph on session start and keeps it updated
    incrementally when Hermes creates/edits skills.

${C_BOLD}FILES ON DISK${C_RESET}
    $HERMES_HOME/skill-graph.db                       — SQLite graph database (auto-created)
    $HERMES_HOME/profiles/<name>/skill-graph.db        — per-profile DB (auto-created)
EOF
}

# ── Install ─────────────────────────────────────────────────────────────────
do_install() {
    echo ""
    echo -e "  ${C_BOLD}hermes-skill-graph installer${C_RESET}"
    echo ""

    # Validate source dirs
    local errors=0
    for d in "$PLUGIN_SRC" "$SKILL_SRC"; do
        if [ ! -d "$d" ]; then
            error "Source directory not found: $d"
            errors=$((errors + 1))
        fi
    done
    if [ ! -f "$PLUGIN_SRC/plugin.yaml" ]; then
        error "Missing plugin.yaml in $PLUGIN_SRC"
        errors=$((errors + 1))
    fi
    if [ ! -f "$PLUGIN_SRC/__init__.py" ]; then
        error "Missing __init__.py in $PLUGIN_SRC"
        errors=$((errors + 1))
    fi
    if [ ! -f "$SKILL_SRC/SKILL.md" ]; then
        error "Missing SKILL.md in $SKILL_SRC"
        errors=$((errors + 1))
    fi
    [ "$errors" -gt 0 ] && exit 1

    # Create target directories
    mkdir -p "$HERMES_HOME/plugins" "$HERMES_HOME/skills"

    # Remove stale symlinks / dirs
    for target in "$PLUGIN_TARGET" "$SKILL_TARGET"; do
        if [ -e "$target" ] || [ -L "$target" ]; then
            rm -rf "$target"
            ok "Removed existing: $target"
        fi
    done

    # Symlink plugin
    ln -sfn "$PLUGIN_SRC" "$PLUGIN_TARGET"
    ok "Plugin linked: $PLUGIN_TARGET → $PLUGIN_SRC"

    # Symlink skill
    ln -sfn "$SKILL_SRC" "$SKILL_TARGET"
    ok "Skill linked:  $SKILL_TARGET → $SKILL_SRC"

    echo ""
    echo -e "  ${C_BOLD}${C_GREEN}Install complete!${C_RESET}"
    echo ""
    echo -e "  ${C_GRAY}Next steps:${C_RESET}"
    echo -e "  ${C_GRAY}  1. Restart Hermes (/reset or exit+relaunch)${C_RESET}"
    echo -e "  ${C_GRAY}  2. The skill_graph_search() tool is now available${C_RESET}"
    echo -e "  ${C_GRAY}  3. Add 'relations' to your SKILL.md frontmatter to seed data${C_RESET}"
    echo -e "  ${C_GRAY}     See docs/relations-format.md for the full spec${C_RESET}"
    echo ""
}

# ── Uninstall ───────────────────────────────────────────────────────────────
do_uninstall() {
    echo ""
    echo -e "  ${C_BOLD}hermes-skill-graph uninstaller${C_RESET}"
    echo ""

    local removed=0
    for target in "$PLUGIN_TARGET" "$SKILL_TARGET"; do
        if [ -L "$target" ]; then
            rm "$target"
            ok "Removed symlink: $target"
            removed=$((removed + 1))
        elif [ -e "$target" ]; then
            warn "Not a symlink — skipping: $target (remove manually)"
        else
            info "Not installed: $target"
        fi
    done

    # Clean DB
    local db_path="$HERMES_HOME/skill-graph.db"
    if [ -f "$db_path" ]; then
        warn "Database left in place: $db_path"
        warn "  Remove manually: rm $db_path"
    fi

    if [ "$removed" -eq 0 ]; then
        echo ""
        info "Nothing to uninstall."
    else
        echo ""
        ok "Uninstalled $removed component(s). Restart Hermes to finalize."
    fi
    echo ""
}

# ── Main ────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --uninstall|-u) do_uninstall ;;
    --help|-h)      show_help ;;
    *)              do_install ;;
esac
