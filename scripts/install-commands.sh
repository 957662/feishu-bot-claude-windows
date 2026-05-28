#!/usr/bin/env bash
set -euo pipefail

# Copy feishu-bot-claude's slash commands into ~/.claude/commands/.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/commands"
TARGET_DIR="${CLAUDE_COMMANDS_DIR:-$HOME/.claude/commands}"

if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: $SOURCE_DIR does not exist" >&2
    exit 1
fi

mkdir -p "$TARGET_DIR"

installed=0
for src in "$SOURCE_DIR"/*.md; do
    dest="$TARGET_DIR/$(basename "$src")"
    cp -f "$src" "$dest"
    installed=$((installed + 1))
done

echo "Installed $installed slash command(s) into $TARGET_DIR"
echo "Try them in Claude Code: /bot-new, /bot-list, /bot-start, etc."

# ---- Skills (user-level): lark-cli (lets Claude use Feishu API directly) ----
SKILL_SRC_DIR="$PROJECT_ROOT/claude-skill"
SKILL_TARGET_DIR="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
if [ -d "$SKILL_SRC_DIR" ]; then
    mkdir -p "$SKILL_TARGET_DIR"
    skill_count=0
    for skill_dir in "$SKILL_SRC_DIR"/*/; do
        [ -d "$skill_dir" ] || continue
        name="$(basename "$skill_dir")"
        mkdir -p "$SKILL_TARGET_DIR/$name"
        cp -f "$skill_dir"/*.md "$SKILL_TARGET_DIR/$name/" 2>/dev/null || true
        skill_count=$((skill_count + 1))
    done
    echo "Installed $skill_count skill(s) into $SKILL_TARGET_DIR"
    echo "Skills give Claude/Codex access to the full lark-cli surface (im/calendar/drive/...)"
fi
