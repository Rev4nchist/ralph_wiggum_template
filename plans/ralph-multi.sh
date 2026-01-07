#!/bin/bash
set -e

# =============================================================================
# RALPH WIGGUM MULTI-AGENT ORCHESTRATOR
# Enhanced with model selection and multi-agent coordination
# =============================================================================

if [ -f ".env" ]; then
    source .env
fi

# =============================================================================
# Configuration
# =============================================================================
AGENT_ID=${RALPH_AGENT_ID:-agent-default}
AGENT_TYPE=${RALPH_AGENT_TYPE:-general}
SPECIALIST_MODES=${RALPH_SPECIALIST_MODES:-implement}
MAX_ITERATIONS=${1:-20}
REDIS_URL=${REDIS_URL:-redis://localhost:6379}

COMPLETION_PROMISE="<PROMISE>COMPLETE</PROMISE>"
BLOCKED_PROMISE="<PROMISE>BLOCKED</PROMISE>"
WAITING_PROMISE="<PROMISE>WAITING</PROMISE>"

PRD_FILE="plans/prd.json"
PROGRESS_FILE="plans/progress.txt"
LOG_FILE="plans/ralph.log"

# =============================================================================
# Model Configuration
# =============================================================================
MODEL_OPUS="anthropic/claude-opus-4.5"
MODEL_GLM="z-ai/glm-4.7"
MODEL_MINIMAX="minimax/minimax-m2.1"

USE_OPENROUTER=${USE_OPENROUTER:-true}

if [ "$USE_OPENROUTER" = "true" ] && [ -n "$OPENROUTER_API_KEY" ]; then
    export ANTHROPIC_BASE_URL="https://openrouter.ai/api/v1"
    export ANTHROPIC_AUTH_TOKEN="$OPENROUTER_API_KEY"
    export ANTHROPIC_API_KEY=""
    export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-$MODEL_GLM}"
    export ANTHROPIC_SMALL_FAST_MODEL="${ANTHROPIC_SMALL_FAST_MODEL:-$MODEL_MINIMAX}"
    ROUTER_MODE="OpenRouter"
else
    ROUTER_MODE="Direct Anthropic API"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Logging
# =============================================================================
log() { echo -e "${BLUE}[$AGENT_ID $(date '+%H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
error() { echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }

# =============================================================================
# Redis Operations
# =============================================================================
redis_cmd() {
    redis-cli -u "$REDIS_URL" "$@" 2>/dev/null
}

register_agent() {
    local data=$(cat << EOF
{
  "agent_id": "$AGENT_ID",
  "agent_type": "$AGENT_TYPE",
  "specialist_modes": ["${SPECIALIST_MODES//,/\",\"}"],
  "status": "active",
  "registered_at": "$(date -Iseconds)",
  "workspace": "$(pwd)"
}
EOF
)
    redis_cmd HSET "ralph:agents" "$AGENT_ID" "$data" > /dev/null
    redis_cmd SETEX "ralph:heartbeats:$AGENT_ID" 30 "$(date -Iseconds)" > /dev/null
    log "Registered as $AGENT_ID ($AGENT_TYPE)"
}

heartbeat() {
    redis_cmd SETEX "ralph:heartbeats:$AGENT_ID" 30 "$(date -Iseconds)" > /dev/null
}

update_status() {
    local status=$1
    local details=$2
    local current=$(redis_cmd HGET "ralph:agents" "$AGENT_ID")
    if [ -n "$current" ]; then
        local updated=$(echo "$current" | jq --arg s "$status" --arg d "$details" '.status = $s | .status_details = $d')
        redis_cmd HSET "ralph:agents" "$AGENT_ID" "$updated" > /dev/null
    fi
}

publish_event() {
    local event=$1
    local data=$2
    local msg=$(cat << EOF
{
  "event": "$event",
  "agent_id": "$AGENT_ID",
  "data": $data,
  "timestamp": "$(date -Iseconds)"
}
EOF
)
    redis_cmd PUBLISH "ralph:events" "$msg" > /dev/null
}

# =============================================================================
# File Locking
# =============================================================================
acquire_lock() {
    local file_path=$1
    local ttl=${2:-300}
    local lock_key="ralph:locks:file:${file_path//\//:}"
    local lock_data="{\"agent_id\":\"$AGENT_ID\",\"file_path\":\"$file_path\",\"acquired_at\":\"$(date -Iseconds)\"}"
    if redis_cmd SET "$lock_key" "$lock_data" NX EX "$ttl" > /dev/null; then
        return 0
    fi
    return 1
}

release_lock() {
    local file_path=$1
    local lock_key="ralph:locks:file:${file_path//\//:}"
    redis_cmd DEL "$lock_key" > /dev/null
}

# =============================================================================
# Hooks
# =============================================================================
run_hooks() {
    local trigger=$1
    if command -v python3 &> /dev/null && [ -f "lib/hooks/runner.py" ]; then
        python3 -c "
from lib.hooks import HookRunner, HookTrigger
runner = HookRunner('hooks.json', '$AGENT_ID')
results = runner.run_hooks(HookTrigger.$trigger, {})
for r in results:
    if not r.success and not r.skipped:
        exit(1)
" 2>/dev/null
        return $?
    fi
    return 0
}

# =============================================================================
# Prerequisites
# =============================================================================
check_prerequisites() {
    log "Checking prerequisites..."

    if command -v ccr &> /dev/null; then
        CLAUDE_CMD="ccr code"
        log "Using Claude Code Router (ccr)"
    elif command -v claude &> /dev/null; then
        CLAUDE_CMD="claude"
        log "Using Claude Code directly"
    else
        error "Claude Code not found"
        exit 1
    fi

    if ! redis_cmd PING > /dev/null 2>&1; then
        warn "Redis not available - running in standalone mode"
        REDIS_ENABLED=false
    else
        REDIS_ENABLED=true
        register_agent
    fi

    [ ! -f "$PRD_FILE" ] && error "PRD not found: $PRD_FILE" && exit 1
    [ ! -f "$PROGRESS_FILE" ] && echo "# Progress Log - $AGENT_ID" > "$PROGRESS_FILE"

    success "Prerequisites verified"
}

# =============================================================================
# Build Prompt with Model Selection Guidance
# =============================================================================
build_prompt() {
    local iteration=$1

    cat << 'PROMPT_START'
# RALPH WIGGUM AUTONOMOUS AGENT

## Agent Identity
PROMPT_START

    cat << EOF
- **Agent ID**: $AGENT_ID
- **Agent Type**: $AGENT_TYPE
- **Specialist Modes**: $SPECIALIST_MODES
- **Iteration**: $iteration of $MAX_ITERATIONS
EOF

    cat << 'PROMPT_MIDDLE'

## MODEL SELECTION [CRITICAL - READ THIS]

You MUST use the appropriate model for each task phase. Signal your model choice.

### Model Routing Rules

| Phase | Model | Signal | Use For |
|-------|-------|--------|---------|
| **PLANNING** | `anthropic/claude-opus-4.5` | `[MODEL: opus]` | Architecture, design, breaking down tasks, trade-offs |
| **IMPLEMENTATION** | `z-ai/glm-4.7` | `[MODEL: glm]` | Writing code, features, bug fixes, refactoring |
| **TESTING** | `minimax/minimax-m2.1` | `[MODEL: minimax]` | Running tests, linting, formatting, validation |
| **REVIEW** | `anthropic/claude-opus-4.5` | `[MODEL: opus]` | Code review, security audit, quality assessment |
| **DEBUGGING** | `z-ai/glm-4.7` | `[MODEL: glm]` | Investigating bugs, reading logs, tracing |
| **DOCUMENTATION** | `minimax/minimax-m2.1` | `[MODEL: minimax]` | Writing docs, README, comments |

### Decision Process

Before starting ANY task, ask yourself:
1. Is this PLANNING what to build? → Use Opus
2. Is this IMPLEMENTING code? → Use GLM
3. Is this TESTING or VERIFYING? → Use Minimax
4. Is this REVIEWING for quality? → Use Opus

**Default**: If unsure, use GLM (workhorse implementation model)

## Workflow

### Phase 1: ANALYZE [MODEL: opus if complex, glm if simple]

Read the PRD file. Find the highest-priority task where `"passes": false`.
- Check dependencies - don't start if dependencies incomplete
- Consider if this needs planning (opus) or direct implementation (glm)

### Phase 2: PLAN [MODEL: opus]

For non-trivial tasks, plan your approach:
- Break down into steps
- Identify files to modify
- Consider edge cases
- Document in progress.txt

### Phase 3: IMPLEMENT [MODEL: glm]

Write clean, tested code:
- Follow existing patterns
- No unnecessary comments
- Commit frequently

### Phase 4: VERIFY [MODEL: minimax]

Run verification:
```bash
npm run build 2>&1 || echo "Build check"
npm test 2>&1 || echo "Test check"
```

### Phase 5: UPDATE [MODEL: minimax]

If task passes:
- Set `"passes": true` in PRD
- Add notes to task
- Append to progress.txt
- Commit changes

### Phase 6: COMMIT [MODEL: minimax]
```bash
git add -A
PROMPT_MIDDLE

    cat << EOF
git commit -m "feat($AGENT_ID): <description>"
EOF

    cat << 'PROMPT_END'
```

## Multi-Agent Awareness

You are part of a multi-agent system. Other agents may be working concurrently.

- **File Locks**: Before editing shared files, locks are checked automatically
- **Task Queue**: You may receive tasks from external sources via Redis
- **Artifacts**: Store outputs in `/shared/artifacts/` for other agents

## Completion Signals

When ALL PRD items have `"passes": true`:
```
<PROMISE>COMPLETE</PROMISE>
```

If BLOCKED and need human input:
```
<PROMISE>BLOCKED</PROMISE>
```

If waiting for another agent's task:
```
<PROMISE>WAITING</PROMISE>
```

## Current State
PROMPT_END

    echo ""
    echo "### PRD (Task Backlog)"
    echo '```json'
    cat "$PRD_FILE"
    echo '```'
    echo ""
    echo "### Recent Progress"
    echo '```'
    tail -30 "$PROGRESS_FILE"
    echo '```'
    echo ""
    echo "---"
    echo "Begin working. Start by selecting the appropriate model for analysis."
}

# =============================================================================
# Main Loop
# =============================================================================
main() {
    check_prerequisites

    log "=========================================="
    log "Starting Ralph Wiggum Multi-Agent Loop"
    log "Agent: $AGENT_ID | Type: $AGENT_TYPE"
    log "Models: Opus=$MODEL_OPUS | GLM=$MODEL_GLM | Minimax=$MODEL_MINIMAX"
    log "=========================================="

    for ((i=1; i<=MAX_ITERATIONS; i++)); do
        log "--- Iteration $i of $MAX_ITERATIONS ---"

        [ "$REDIS_ENABLED" = true ] && heartbeat
        [ "$REDIS_ENABLED" = true ] && update_status "working" "Iteration $i"

        START_TIME=$(date +%s)
        PROMPT=$(build_prompt $i)

        # Run pre-task hooks
        run_hooks "PRE_TASK" || warn "Pre-task hooks failed"

        OUTPUT=$($CLAUDE_CMD --dangerously-skip-permissions -p "$PROMPT" 2>&1) || true

        END_TIME=$(date +%s)
        DURATION=$((END_TIME - START_TIME))

        echo "$OUTPUT" >> "$LOG_FILE"

        # Extract model signals from output
        if echo "$OUTPUT" | grep -q "\[MODEL: opus\]"; then
            log "Agent requested Opus model for planning/review"
        fi
        if echo "$OUTPUT" | grep -q "\[MODEL: glm\]"; then
            log "Agent using GLM model for implementation"
        fi
        if echo "$OUTPUT" | grep -q "\[MODEL: minimax\]"; then
            log "Agent using Minimax model for testing/docs"
        fi

        # Check completion
        if echo "$OUTPUT" | grep -q "$COMPLETION_PROMISE"; then
            success "ALL TASKS COMPLETE!"
            [ "$REDIS_ENABLED" = true ] && update_status "completed" "All tasks done"
            run_hooks "TASK_COMPLETE" || true
            exit 0
        fi

        # Check blocked
        if echo "$OUTPUT" | grep -q "$BLOCKED_PROMISE"; then
            warn "BLOCKED - Need human input"
            [ "$REDIS_ENABLED" = true ] && update_status "blocked" "Needs human input"

            if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
                ./plans/notify.sh question "[$AGENT_ID] Blocked - need input" 2>/dev/null || true
                ./plans/wait-response.sh 300 || true
            fi
            continue
        fi

        # Check waiting
        if echo "$OUTPUT" | grep -q "$WAITING_PROMISE"; then
            warn "WAITING - Dependency not ready"
            [ "$REDIS_ENABLED" = true ] && update_status "waiting" "Waiting for dependency"
            sleep 30
            continue
        fi

        log "Iteration $i complete (${DURATION}s)"
        sleep 2
    done

    warn "MAX ITERATIONS REACHED"
    [ "$REDIS_ENABLED" = true ] && update_status "max_iterations" "Reached $MAX_ITERATIONS"
    exit 1
}

# =============================================================================
# CLI Options
# =============================================================================

# Single iteration mode
if [ "$1" = "--once" ]; then
    check_prerequisites
    PROMPT=$(build_prompt 1)
    $CLAUDE_CMD --dangerously-skip-permissions -p "$PROMPT"
    exit $?
fi

# Dry run - show prompt only
if [ "$1" = "--dry-run" ]; then
    PROMPT=$(build_prompt 1)
    echo "$PROMPT"
    exit 0
fi

# Show model config
if [ "$1" = "--models" ]; then
    echo "Model Configuration:"
    echo "  Planning/Review: $MODEL_OPUS"
    echo "  Implementation:  $MODEL_GLM"
    echo "  Testing/Docs:    $MODEL_MINIMAX"
    exit 0
fi

main
