#!/bin/bash
set -e

# =============================================================================
# RALPH WIGGUM ORCHESTRATOR - Enhanced with Telegram Notifications
# Integrates: PRD tracking, Claude-Mem context, Librarian docs, Telegram comms
# =============================================================================

# Load environment variables from .env if present
if [ -f ".env" ]; then
    source .env
fi

# =============================================================================
# OpenRouter Model Configuration
# =============================================================================
# Set these to use OpenRouter instead of direct Anthropic API
# Models: z-ai/glm-4.7 (workhorse), minimax/minimax-m2.1 (fast), anthropic/claude-opus-4.5 (planning)

USE_OPENROUTER=${USE_OPENROUTER:-true}

if [ "$USE_OPENROUTER" = "true" ] && [ -n "$OPENROUTER_API_KEY" ]; then
    export ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"
    export ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY"
    export ANTHROPIC_API_KEY=""
    # Workhorse model for most execution tasks
    export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-z-ai/glm-4.7}"
    # Fast model for quick operations
    export ANTHROPIC_SMALL_FAST_MODEL="${ANTHROPIC_SMALL_FAST_MODEL:-minimax/minimax-m2.1}"
    ROUTER_MODE="OpenRouter ($ANTHROPIC_MODEL)"
else
    ROUTER_MODE="Direct Anthropic API"
fi

# Configuration
MAX_ITERATIONS=${1:-20}
COMPLETION_PROMISE="<PROMISE>COMPLETE</PROMISE>"
BLOCKED_PROMISE="<PROMISE>BLOCKED</PROMISE>"
WAITING_PROMISE="<PROMISE>WAITING</PROMISE>"
PRD_FILE="plans/prd.json"
PROGRESS_FILE="plans/progress.txt"
LOG_FILE="plans/ralph.log"
METRICS_FILE="plans/metrics.csv"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# Logging functions
log() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

notify() {
    echo -e "${PURPLE}[NOTIFY]${NC} $1" | tee -a "$LOG_FILE"
    if [ -f "./plans/notify.sh" ]; then
        ./plans/notify.sh "status" "$1" 2>/dev/null || true
    fi
}

# Initialize metrics file
init_metrics() {
    if [ ! -f "$METRICS_FILE" ]; then
        echo "timestamp,iteration,task_id,status,duration_seconds" > "$METRICS_FILE"
    fi
}

# Log metrics
log_metric() {
    local iteration=$1
    local task_id=$2
    local status=$3
    local duration=$4
    echo "$(date -Iseconds),$iteration,$task_id,$status,$duration" >> "$METRICS_FILE"
}

# Verify prerequisites
check_prerequisites() {
    log "Checking prerequisites..."

    # Prefer ccr (Claude Code Router) for model routing, fallback to claude
    if command -v ccr &> /dev/null; then
        CLAUDE_CMD="ccr code"
        log "Using Claude Code Router (ccr) for model routing"
    elif command -v claude &> /dev/null; then
        CLAUDE_CMD="claude"
        log "Using Claude Code directly (ccr not found)"
    else
        error "Claude Code not found. Install with: npm install -g @anthropic-ai/claude-code"
        exit 1
    fi

    if [ ! -f "$PRD_FILE" ]; then
        error "PRD file not found: $PRD_FILE"
        exit 1
    fi

    if [ ! -f "$PROGRESS_FILE" ]; then
        warn "Progress file not found. Creating..."
        echo "# Project Progress Log" > "$PROGRESS_FILE"
        echo "" >> "$PROGRESS_FILE"
        echo "Started: $(date '+%Y-%m-%d %H:%M:%S')" >> "$PROGRESS_FILE"
        echo "" >> "$PROGRESS_FILE"
    fi

    # Check Librarian
    if command -v librarian &> /dev/null || [ -f "$HOME/.librarian-cli/librarian" ]; then
        log "Librarian available - documentation search enabled"
        LIBRARIAN_ENABLED=true
    else
        warn "Librarian not found - documentation search disabled"
        LIBRARIAN_ENABLED=false
    fi

    # Check Telegram config
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        log "Telegram notifications enabled"
        TELEGRAM_ENABLED=true
    else
        warn "Telegram not configured - notifications disabled"
        TELEGRAM_ENABLED=false
    fi

    init_metrics
    success "Prerequisites verified"
}

# Build the prompt
build_prompt() {
    local iteration=$1

    cat << EOF
# RALPH WIGGUM ITERATION $iteration of $MAX_ITERATIONS

## Your Mission
You are in an autonomous development loop. Work methodically through the PRD until all tasks pass.

## Context Files
- **PRD (Task Backlog):** $PRD_FILE
- **Progress Log:** $PROGRESS_FILE

## Instructions

### 1. ANALYZE
Read the PRD file. Identify the highest-priority task where "passes": false.
Consider dependencies - don't start a task if its dependencies aren't complete.

### 2. RESEARCH (If Needed)
Before coding, search documentation for relevant APIs if uncertain:
\`\`\`bash
# If Librarian available:
librarian search --library <name> "<your question>"
\`\`\`

### 3. IMPLEMENT
Work on ONLY that single task. Write clean, tested code.

### 4. VERIFY
Run the project's test suite and type checks:
\`\`\`bash
npm run build 2>&1 || echo "Build check complete"
npm test 2>&1 || echo "Test check complete"
\`\`\`

Tests MUST pass before marking the task complete.

### 5. UPDATE STATE
If the task passes:
a) Update $PRD_FILE - set "passes": true for the completed task
b) Add notes to the task's "notes" field
c) Append a summary to $PROGRESS_FILE

### 6. COMMIT
Create a git commit with descriptive message:
\`\`\`bash
git add -A
git commit -m "feat(task-XXX): <description>"
\`\`\`

### 7. CHECK COMPLETION
If ALL items in the PRD have "passes": true, output:
$COMPLETION_PROMISE

If you are BLOCKED and need human input, output:
$BLOCKED_PROMISE

Otherwise, exit normally for the next iteration.

## Current PRD State
$(cat "$PRD_FILE")

## Recent Progress
$(tail -50 "$PROGRESS_FILE")

Begin working on the next task.
EOF
}

# Main loop
main() {
    check_prerequisites

    log "=========================================="
    log "Starting Ralph Wiggum Loop"
    log "Max iterations: $MAX_ITERATIONS"
    log "Model: $ROUTER_MODE"
    if [ "$USE_OPENROUTER" = "true" ]; then
        log "Main model: $ANTHROPIC_MODEL"
        log "Fast model: $ANTHROPIC_SMALL_FAST_MODEL"
    fi
    log "=========================================="

    notify "🚀 Ralph starting ($ROUTER_MODE, $MAX_ITERATIONS iterations)"

    for ((i=1; i<=MAX_ITERATIONS; i++)); do
        log "=========================================="
        log "ITERATION $i of $MAX_ITERATIONS"
        log "=========================================="

        START_TIME=$(date +%s)

        # Build prompt
        PROMPT=$(build_prompt $i)

        # Run Claude with the prompt
        # Using --dangerously-skip-permissions for unattended operation
        # Uses ccr (Claude Code Router) if available for model routing
        OUTPUT=$($CLAUDE_CMD --dangerously-skip-permissions -p "$PROMPT" 2>&1) || true

        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))

        # Log output
        echo "$OUTPUT" >> "$LOG_FILE"

        # Extract current task for metrics (basic parsing)
        CURRENT_TASK=$(echo "$OUTPUT" | grep -oP 'task-\d+' | head -1 || echo "unknown")

        # Check for completion
        if echo "$OUTPUT" | grep -q "$COMPLETION_PROMISE"; then
            success "=========================================="
            success "ALL TASKS COMPLETE!"
            success "=========================================="
            success "Total iterations: $i"
            log_metric "$i" "$CURRENT_TASK" "COMPLETE" "$DURATION"
            notify "✅ ALL TASKS COMPLETE after $i iterations!"
            exit 0
        fi

        # Check for blocked state
        if echo "$OUTPUT" | grep -q "$BLOCKED_PROMISE"; then
            warn "Task is BLOCKED. Human input needed."
            log_metric "$i" "$CURRENT_TASK" "BLOCKED" "$DURATION"
            notify "🚫 BLOCKED: Human input needed. Check progress.txt"

            if [ "$TELEGRAM_ENABLED" = true ]; then
                # Wait for human response
                log "Waiting for human response via Telegram..."
                ./plans/wait-response.sh 300 || true
            fi

            continue
        fi

        # Check for waiting state
        if echo "$OUTPUT" | grep -q "$WAITING_PROMISE"; then
            warn "Waiting for human response..."
            log_metric "$i" "$CURRENT_TASK" "WAITING" "$DURATION"
            notify "⏳ Waiting for your response..."
            sleep 30
            continue
        fi

        # Normal iteration complete
        log_metric "$i" "$CURRENT_TASK" "ITERATION" "$DURATION"
        log "Iteration $i complete (${DURATION}s). Continuing..."

        # Notify every 5 iterations
        if [ $((i % 5)) -eq 0 ]; then
            COMPLETED=$(jq '[.[] | select(.passes == true)] | length' "$PRD_FILE")
            TOTAL=$(jq 'length' "$PRD_FILE")
            notify "📊 Progress: $COMPLETED/$TOTAL tasks complete (iteration $i)"
        fi

        # Rate limiting delay
        sleep 2
    done

    warn "=========================================="
    warn "MAX ITERATIONS REACHED ($MAX_ITERATIONS)"
    warn "=========================================="
    notify "⚠️ Max iterations reached. Review progress.txt"
    exit 1
}

# Single iteration mode (for debugging)
if [ "$1" = "--once" ]; then
    check_prerequisites
    PROMPT=$(build_prompt 1)
    $CLAUDE_CMD --dangerously-skip-permissions -p "$PROMPT"
    exit $?
fi

# Dry run mode (show prompt only)
if [ "$1" = "--dry-run" ]; then
    PROMPT=$(build_prompt 1)
    echo "$PROMPT"
    exit 0
fi

# Run main loop
main
