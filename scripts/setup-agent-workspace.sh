#!/bin/bash
# Setup agent workspace with proper CLAUDE.md and configuration
# Usage: ./scripts/setup-agent-workspace.sh <workspace_path> <agent_id> <agent_type> <modes>

set -e

WORKSPACE=${1:-.}
AGENT_ID=${2:-agent-default}
AGENT_TYPE=${3:-general}
SPECIALIST_MODES=${4:-implement}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_ROOT/templates/agent-CLAUDE.md"

echo "Setting up workspace: $WORKSPACE"
echo "  Agent ID: $AGENT_ID"
echo "  Agent Type: $AGENT_TYPE"
echo "  Modes: $SPECIALIST_MODES"

# Create workspace directories
mkdir -p "$WORKSPACE/.claude"
mkdir -p "$WORKSPACE/plans"

# Copy and customize CLAUDE.md template
if [ -f "$TEMPLATE" ]; then
    sed -e "s|\${RALPH_AGENT_ID}|$AGENT_ID|g" \
        -e "s|\${RALPH_AGENT_TYPE}|$AGENT_TYPE|g" \
        -e "s|\${RALPH_SPECIALIST_MODES}|$SPECIALIST_MODES|g" \
        -e "s|\${WORKSPACE}|$WORKSPACE|g" \
        -e "s|\${REDIS_URL}|${REDIS_URL:-redis://localhost:6379}|g" \
        "$TEMPLATE" > "$WORKSPACE/.claude/CLAUDE.md"
    echo "Created .claude/CLAUDE.md"
else
    echo "Warning: Template not found at $TEMPLATE"
fi

# Copy hooks.json if not exists
if [ ! -f "$WORKSPACE/hooks.json" ] && [ -f "$PROJECT_ROOT/hooks.json" ]; then
    cp "$PROJECT_ROOT/hooks.json" "$WORKSPACE/"
    echo "Copied hooks.json"
fi

# Copy lib directory if not exists
if [ ! -d "$WORKSPACE/lib" ] && [ -d "$PROJECT_ROOT/lib" ]; then
    cp -r "$PROJECT_ROOT/lib" "$WORKSPACE/"
    echo "Copied lib/ (ralph-client, hooks, memory)"
fi

# Setup Librarian sources if not exists
if [ ! -d "$WORKSPACE/.librarian" ]; then
    mkdir -p "$WORKSPACE/.librarian"
    cat > "$WORKSPACE/.librarian/libraries.yml" << 'LIBS_EOF'
# Project Documentation Sources
# Add libraries relevant to your project
sources:
  # Core documentation
  - url: https://github.com/anthropics/claude-code
    docs: docs
    ref: main

  # TypeScript/Node ecosystem
  - url: https://github.com/microsoft/TypeScript
    docs: doc
    ref: main

  # Add your framework docs here (uncomment as needed)
  # - url: https://github.com/vercel/next.js
  #   docs: docs
  #   ref: canary
  # - url: https://github.com/facebook/react
  #   docs: docs
  #   ref: main
LIBS_EOF
    echo "Created .librarian/libraries.yml"
fi

# Create default PRD if not exists
if [ ! -f "$WORKSPACE/plans/prd.json" ]; then
    cat > "$WORKSPACE/plans/prd.json" << 'EOF'
[
  {
    "id": "task-001",
    "category": "setup",
    "priority": 1,
    "description": "Initialize project structure",
    "acceptance_criteria": [
      "Project builds successfully",
      "Basic tests pass"
    ],
    "dependencies": [],
    "passes": false,
    "notes": ""
  }
]
EOF
    echo "Created plans/prd.json"
fi

# Create progress.txt if not exists
if [ ! -f "$WORKSPACE/plans/progress.txt" ]; then
    echo "# Progress Log - $AGENT_ID" > "$WORKSPACE/plans/progress.txt"
    echo "" >> "$WORKSPACE/plans/progress.txt"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$WORKSPACE/plans/progress.txt"
    echo "Created plans/progress.txt"
fi

# Copy ralph-multi.sh
if [ -f "$PROJECT_ROOT/plans/ralph-multi.sh" ]; then
    cp "$PROJECT_ROOT/plans/ralph-multi.sh" "$WORKSPACE/plans/"
    chmod +x "$WORKSPACE/plans/ralph-multi.sh"
    echo "Copied plans/ralph-multi.sh"
fi

# Create .env template
if [ ! -f "$WORKSPACE/.env" ]; then
    cat > "$WORKSPACE/.env" << EOF
# Ralph Wiggum Agent Environment
RALPH_AGENT_ID=$AGENT_ID
RALPH_AGENT_TYPE=$AGENT_TYPE
RALPH_SPECIALIST_MODES=$SPECIALIST_MODES

# Redis
REDIS_URL=${REDIS_URL:-redis://localhost:6379}

# OpenRouter (copy from main .env)
OPENROUTER_API_KEY=
USE_OPENROUTER=true
ANTHROPIC_MODEL=z-ai/glm-4.7
ANTHROPIC_SMALL_FAST_MODEL=minimax/minimax-m2.1

# Telegram (optional)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF
    echo "Created .env template"
fi

echo ""
echo "Workspace setup complete!"
echo ""
echo "Next steps:"
echo "  1. Update $WORKSPACE/.env with your API keys"
echo "  2. Update $WORKSPACE/plans/prd.json with your tasks"
echo "  3. Run: cd $WORKSPACE && ./plans/ralph-multi.sh"
