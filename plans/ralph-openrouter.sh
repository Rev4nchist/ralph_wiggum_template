#!/bin/bash
# Ralph Wiggum with OpenRouter via Claude Code Router
# Uses tiered models: Opus for planning, GLM/Minimax for execution

set -e

MAX_ITERATIONS=${1:-20}
COMPLETION_PROMISE="<PROMISE>COMPLETE</PROMISE>"
BLOCKED_PROMISE="<PROMISE>BLOCKED</PROMISE>"
PRD_FILE="plans/prd.json"
PROGRESS_FILE="plans/progress.txt"
LOG_FILE="plans/ralph-openrouter.log"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[$(date '+%H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }

notify() {
    if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$TELEGRAM_CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
            --data-urlencode "text=$1" > /dev/null 2>&1
    fi
}

build_prompt() {
    local iteration=$1
    cat << EOF
# RALPH WIGGUM ITERATION $iteration of $MAX_ITERATIONS
# Using OpenRouter with tiered models

## Your Mission
Work through the PRD tasks autonomously. You have access to multiple models:
- Use extended thinking for complex architectural decisions
- Default model handles standard coding tasks efficiently

## Context Files
- PRD: $PRD_FILE
- Progress: $PROGRESS_FILE

## Instructions
1. Read PRD, find highest-priority incomplete task
2. Implement the task with clean, tested code
3. Run: npm run build && npm test
4. If passes: Update PRD ("passes": true), update progress.txt, git commit
5. If ALL tasks pass: Output $COMPLETION_PROMISE
6. If blocked: Output $BLOCKED_PROMISE

## Current PRD
$(cat "$PRD_FILE")

## Recent Progress
$(tail -30 "$PROGRESS_FILE")

Begin.
EOF
}

# Check for ccr (Claude Code Router)
if ! command -v ccr &> /dev/null; then
    warn "Claude Code Router not found. Install with: npm install -g @musistudio/claude-code-router"
    warn "Falling back to standard claude command..."
    CCR_CMD="claude"
else
    CCR_CMD="ccr code"
fi

log "Starting Ralph Wiggum (OpenRouter)"
log "Max iterations: $MAX_ITERATIONS"
log "Using: $CCR_CMD"
notify "🚀 Ralph starting (OpenRouter mode, $MAX_ITERATIONS iterations)"

for ((i=1; i<=MAX_ITERATIONS; i++)); do
    log "=== ITERATION $i ==="

    PROMPT=$(build_prompt $i)

    # Run with Claude Code Router (or fallback)
    OUTPUT=$($CCR_CMD --dangerously-skip-permissions -p "$PROMPT" 2>&1) || true

    echo "$OUTPUT" >> "$LOG_FILE"

    if echo "$OUTPUT" | grep -q "$COMPLETION_PROMISE"; then
        success "ALL TASKS COMPLETE!"
        notify "✅ Ralph COMPLETE after $i iterations!"
        exit 0
    fi

    if echo "$OUTPUT" | grep -q "$BLOCKED_PROMISE"; then
        warn "BLOCKED - needs human input"
        notify "🚫 Ralph BLOCKED at iteration $i. Check progress.txt"
        exit 1
    fi

    # Progress notification every 5 iterations
    if [ $((i % 5)) -eq 0 ]; then
        DONE=$(jq '[.[] | select(.passes==true)] | length' "$PRD_FILE" 2>/dev/null || echo "?")
        TOTAL=$(jq 'length' "$PRD_FILE" 2>/dev/null || echo "?")
        notify "📊 Progress: $DONE/$TOTAL tasks (iteration $i)"
    fi

    sleep 2
done

warn "Max iterations reached"
notify "⚠️ Ralph hit max iterations ($MAX_ITERATIONS)"
exit 1
