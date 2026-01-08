#!/bin/bash
# =============================================================================
# Ralph Wiggum PRD Generator (Taskmaster Integration)
# =============================================================================
# Generates a PRD for Ralph Wiggum from Taskmaster output or high-level requirements
# Usage: ./scripts/generate-prd.sh <project_dir> [--from-taskmaster | --from-prompt "description"]
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

PROJECT_DIR=${1:-.}
MODE=${2:---interactive}

# Colors
BLUE='\033[0;34m'
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${BLUE}[PRD-GEN]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# =============================================================================
# From Taskmaster: Convert tasks.json to Ralph PRD format
# =============================================================================
from_taskmaster() {
    local TASKMASTER_FILE="$PROJECT_DIR/.taskmaster/tasks/tasks.json"
    local OUTPUT_FILE="$PROJECT_DIR/plans/prd.json"

    if [ ! -f "$TASKMASTER_FILE" ]; then
        echo "Error: Taskmaster tasks not found at $TASKMASTER_FILE"
        echo "Run 'npx task-master parse-prd' first to generate tasks"
        exit 1
    fi

    log "Converting Taskmaster tasks to Ralph PRD format..."

    # Use jq to transform Taskmaster format to Ralph format
    # Taskmaster: { tasks: [ { id, title, description, status, dependencies, priority, subtasks } ] }
    # Ralph: [ { id, category, priority, description, acceptance_criteria, dependencies, passes } ]

    mkdir -p "$PROJECT_DIR/plans"

    # Get project name from directory or taskmaster config
    local PROJECT_NAME=$(basename "$PROJECT_DIR")

    jq --arg proj "$PROJECT_NAME" '{
        project: $proj,
        created_at: (now | strftime("%Y-%m-%dT%H:%M:%SZ")),
        tasks: [.tasks[] | {
            id: (if (.id | type) == "number" then "TASK-\(.id | tostring | ("00" + .)[-3:])" else .id end),
            title: .title,
            description: (.description // .title),
            type: (if .title | test("(?i)security|audit|vulnerabilit|owasp|penetration") then "security"
                   elif .title | test("(?i)debug|\\berror\\b|\\bfix\\b|\\bbug\\b|failing") then "debugging"
                   elif .title | test("(?i)\\btest|\\bqa\\b|coverage") then "testing"
                   elif .title | test("(?i)refactor|cleanup|smell|debt|reorganize") then "refactoring"
                   elif .title | test("(?i)\\bdocs?\\b|readme|documentation|\\bdocument\\b|\\bguide\\b|api.doc|write.*doc|update.*doc") then "docs"
                   elif .title | test("(?i)review|\\bpr\\b|pull.?request|code.?review") then "review"
                   elif .title | test("(?i)\\bapi\\b|backend|database|docker|python|fastapi|server|endpoint") then "backend"
                   elif .title | test("(?i)\\bui\\b|frontend|component|react|\\bform\\b|\\bcss\\b|plasmo|style") then "frontend"
                   elif .title | test("(?i)setup|init|config|arch|design") then "architecture"
                   else "general" end),
            agent: (if .title | test("(?i)security|audit|vulnerabilit|owasp|penetration") then "security-auditor"
                    elif .title | test("(?i)debug|\\berror\\b|\\bfix\\b|\\bbug\\b|failing") then "debugger"
                    elif .title | test("(?i)\\btest|\\bqa\\b|coverage") then "test-architect"
                    elif .title | test("(?i)refactor|cleanup|smell|debt|reorganize") then "refactorer"
                    elif .title | test("(?i)\\bdocs?\\b|readme|documentation|\\bdocument\\b|\\bguide\\b|api.doc|write.*doc|update.*doc") then "docs-writer"
                    elif .title | test("(?i)review|\\bpr\\b|pull.?request|code.?review") then "code-reviewer"
                    elif .title | test("(?i)\\bapi\\b|backend|database|docker|python|fastapi|server|endpoint") then "backend"
                    elif .title | test("(?i)\\bui\\b|frontend|component|react|\\bform\\b|\\bcss\\b|plasmo|style") then "frontend"
                    else "general-purpose" end),
            priority: (if (.priority | type) == "string" then
                        (if .priority == "high" then 9
                         elif .priority == "medium" then 5
                         else 3 end)
                       else (.priority // 5) end),
            deps: (.dependencies // []),
            files: [],
            acceptance_criteria: (if .subtasks then [.subtasks[].title] else [.description // .title] end),
            passes: (.status == "done")
        }]
    }' "$TASKMASTER_FILE" > "$OUTPUT_FILE"

    success "PRD generated at $OUTPUT_FILE"
    echo "Tasks converted: $(jq 'length' "$OUTPUT_FILE")"
}

# =============================================================================
# Interactive: Use Claude Code to generate PRD from prompt
# =============================================================================
interactive_generate() {
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "  Ralph Wiggum PRD Generator - Interactive Mode"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "To generate a PRD, you have two options:"
    echo ""
    echo "Option 1: Use Taskmaster (Recommended)"
    echo "  1. Create a PRD document describing your project"
    echo "  2. Run: npx task-master parse-prd --input your-prd.md"
    echo "  3. Run: ./scripts/generate-prd.sh . --from-taskmaster"
    echo ""
    echo "Option 2: Use Claude Code directly"
    echo "  In a Claude Code session, say:"
    echo "  'Generate a Ralph Wiggum PRD for: <your project description>'"
    echo "  Then use /task to create and manage tasks"
    echo ""
    echo "Option 3: Manual creation"
    echo "  Copy plans/prd-template.json and edit manually"
    echo ""
}

# =============================================================================
# Create PRD template
# =============================================================================
create_template() {
    mkdir -p "$PROJECT_DIR/plans"

    cat > "$PROJECT_DIR/plans/prd-template.json" << 'EOF'
[
  {
    "id": "task-001",
    "category": "setup",
    "priority": 1,
    "description": "Initialize project with required dependencies",
    "acceptance_criteria": [
      "package.json created with dependencies",
      "TypeScript configured",
      "Project builds successfully"
    ],
    "dependencies": [],
    "passes": false,
    "model_hint": "implementation",
    "notes": ""
  },
  {
    "id": "task-002",
    "category": "feature",
    "priority": 2,
    "description": "Implement core feature",
    "acceptance_criteria": [
      "Feature works as specified",
      "Error handling in place",
      "Code follows project patterns"
    ],
    "dependencies": ["task-001"],
    "passes": false,
    "model_hint": "implementation",
    "notes": ""
  },
  {
    "id": "task-003",
    "category": "test",
    "priority": 3,
    "description": "Add tests for core feature",
    "acceptance_criteria": [
      "Unit tests cover main paths",
      "Tests pass",
      "Coverage > 80%"
    ],
    "dependencies": ["task-002"],
    "passes": false,
    "model_hint": "verification",
    "notes": ""
  }
]
EOF

    success "Template created at $PROJECT_DIR/plans/prd-template.json"
}

# =============================================================================
# Main
# =============================================================================
case "$MODE" in
    --from-taskmaster)
        from_taskmaster
        ;;
    --template)
        create_template
        ;;
    *)
        interactive_generate
        create_template
        ;;
esac
