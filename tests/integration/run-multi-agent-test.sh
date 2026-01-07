#!/bin/bash
# =============================================================================
# Ralph Wiggum Multi-Agent Integration Test Runner
# =============================================================================
# This script sets up and runs the full multi-agent test scenario:
# - Backend agent builds Todo API
# - Frontend agent builds React UI
# - Both coordinate via Redis
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log() { echo -e "${BLUE}[ORCHESTRATOR]${NC} $1"; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }
header() { echo -e "\n${CYAN}═══════════════════════════════════════════════════════════════${NC}"; echo -e "${CYAN}  $1${NC}"; echo -e "${CYAN}═══════════════════════════════════════════════════════════════${NC}\n"; }

# =============================================================================
# Phase 0: Prerequisites Check
# =============================================================================
check_prerequisites() {
    header "Phase 0: Prerequisites Check"

    # Check Docker
    if ! command -v docker &> /dev/null; then
        error "Docker not found. Please install Docker."
        exit 1
    fi
    success "Docker found"

    # Check docker-compose
    if ! command -v docker-compose &> /dev/null; then
        error "docker-compose not found. Please install docker-compose."
        exit 1
    fi
    success "docker-compose found"

    # Check Claude Code (optional but warn)
    if ! command -v claude &> /dev/null; then
        warn "Claude Code CLI not found. Manual agent startup required."
    else
        success "Claude Code CLI found"
    fi
}

# =============================================================================
# Phase 1: Infrastructure Setup
# =============================================================================
setup_infrastructure() {
    header "Phase 1: Infrastructure Setup"

    cd "$PROJECT_ROOT"

    # Start Redis
    log "Starting Redis..."
    docker-compose up -d redis
    sleep 3

    # Verify Redis
    if docker-compose exec -T redis redis-cli ping | grep -q PONG; then
        success "Redis is running"
    else
        error "Redis failed to start"
        exit 1
    fi

    # Clear any stale data
    log "Clearing stale data..."
    docker-compose exec -T redis redis-cli FLUSHDB > /dev/null
    success "Redis data cleared"

    # Build MCP server if needed
    if [ ! -f "$PROJECT_ROOT/mcp-server/dist/index.js" ]; then
        log "Building MCP server..."
        cd "$PROJECT_ROOT/mcp-server"
        npm install > /dev/null 2>&1
        npm run build > /dev/null 2>&1
        success "MCP server built"
        cd "$PROJECT_ROOT"
    else
        success "MCP server already built"
    fi
}

# =============================================================================
# Phase 2: Setup Agent Workspaces
# =============================================================================
setup_workspaces() {
    header "Phase 2: Setup Agent Workspaces"

    cd "$PROJECT_ROOT"

    # Setup backend workspace
    log "Setting up backend agent workspace..."
    ./scripts/setup-agent-workspace.sh \
        "$SCRIPT_DIR/todo-backend" \
        agent-backend \
        backend \
        "implement,test"
    success "Backend workspace ready"

    # Setup frontend workspace
    log "Setting up frontend agent workspace..."
    ./scripts/setup-agent-workspace.sh \
        "$SCRIPT_DIR/todo-frontend" \
        agent-frontend \
        frontend \
        "implement,test"
    success "Frontend workspace ready"

    # Create symlink for shared types (frontend reads from backend)
    if [ ! -L "$SCRIPT_DIR/todo-frontend/shared" ]; then
        ln -sf "$SCRIPT_DIR/todo-backend/shared" "$SCRIPT_DIR/todo-frontend/shared" 2>/dev/null || true
        success "Shared types symlink created"
    fi
}

# =============================================================================
# Phase 3: Register Agents
# =============================================================================
register_agents() {
    header "Phase 3: Register Agents in Redis"

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Register backend agent
    local BACKEND_DATA='{"agent_id":"agent-backend","agent_type":"backend","status":"ready","workspace":"tests/integration/todo-backend","capabilities":["express","typescript","api"]}'
    eval "$REDIS_CMD HSET ralph:agents agent-backend '$BACKEND_DATA'" > /dev/null
    success "Backend agent registered"

    # Register frontend agent
    local FRONTEND_DATA='{"agent_id":"agent-frontend","agent_type":"frontend","status":"ready","workspace":"tests/integration/todo-frontend","capabilities":["react","typescript","ui"]}'
    eval "$REDIS_CMD HSET ralph:agents agent-frontend '$FRONTEND_DATA'" > /dev/null
    success "Frontend agent registered"

    # Verify registration
    log "Registered agents:"
    eval "$REDIS_CMD HGETALL ralph:agents" | head -20
}

# =============================================================================
# Phase 4: Queue Tasks
# =============================================================================
queue_tasks() {
    header "Phase 4: Queue Tasks"

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Read and queue backend tasks
    log "Queueing backend tasks..."
    local BACKEND_PRD="$SCRIPT_DIR/todo-backend/plans/prd.json"
    if [ -f "$BACKEND_PRD" ]; then
        # Queue each task with priority score
        # Score format: priority * 1000000 + timestamp for ordering
        local BASE_SCORE=1000000

        for task_id in be-001 be-002 be-003 be-004 be-005; do
            local priority=$(echo "$task_id" | sed 's/be-00//')
            local score=$((priority * BASE_SCORE))
            eval "$REDIS_CMD ZADD ralph:tasks:queue $score $task_id" > /dev/null
            echo "  - Queued $task_id (priority: $priority)"
        done
        success "Backend tasks queued"
    fi

    # Read and queue frontend tasks
    log "Queueing frontend tasks..."
    local FRONTEND_PRD="$SCRIPT_DIR/todo-frontend/plans/prd.json"
    if [ -f "$FRONTEND_PRD" ]; then
        local BASE_SCORE=1000000

        for task_id in fe-001 fe-002 fe-003 fe-004 fe-005 fe-006 fe-007; do
            local priority=$(echo "$task_id" | sed 's/fe-00//')
            local score=$((priority * BASE_SCORE))
            eval "$REDIS_CMD ZADD ralph:tasks:queue $score $task_id" > /dev/null
            echo "  - Queued $task_id (priority: $priority)"
        done
        success "Frontend tasks queued"
    fi

    # Show queue
    log "Task queue:"
    eval "$REDIS_CMD ZRANGE ralph:tasks:queue 0 -1 WITHSCORES"
}

# =============================================================================
# Phase 5: Display Instructions
# =============================================================================
display_instructions() {
    header "Phase 5: Ready to Run"

    echo ""
    echo "Multi-agent test environment is ready!"
    echo ""
    echo "To run the agents, open two terminals:"
    echo ""
    echo -e "${CYAN}Terminal 1 - Backend Agent:${NC}"
    echo "  cd $SCRIPT_DIR/todo-backend"
    echo "  RALPH_AGENT_ID=agent-backend \\"
    echo "  RALPH_AGENT_TYPE=backend \\"
    echo "  REDIS_URL=redis://localhost:6379 \\"
    echo "  ../../plans/ralph-multi.sh 10"
    echo ""
    echo -e "${CYAN}Terminal 2 - Frontend Agent:${NC}"
    echo "  cd $SCRIPT_DIR/todo-frontend"
    echo "  RALPH_AGENT_ID=agent-frontend \\"
    echo "  RALPH_AGENT_TYPE=frontend \\"
    echo "  REDIS_URL=redis://localhost:6379 \\"
    echo "  ../../plans/ralph-multi.sh 10"
    echo ""
    echo -e "${CYAN}Monitor coordination:${NC}"
    echo "  # Watch events"
    echo "  redis-cli SUBSCRIBE ralph:events"
    echo ""
    echo "  # Check task queue"
    echo "  redis-cli ZRANGE ralph:tasks:queue 0 -1"
    echo ""
    echo "  # Check agent status"
    echo "  redis-cli HGETALL ralph:agents"
    echo ""
    echo -e "${CYAN}Cleanup after test:${NC}"
    echo "  docker-compose -f $PROJECT_ROOT/docker-compose.yml exec redis redis-cli FLUSHDB"
    echo "  rm -rf $SCRIPT_DIR/todo-backend $SCRIPT_DIR/todo-frontend"
    echo ""
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║     Ralph Wiggum Multi-Agent Integration Test Setup           ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    check_prerequisites
    setup_infrastructure
    setup_workspaces
    register_agents
    queue_tasks
    display_instructions

    success "Setup complete! Follow the instructions above to run the test."
}

main "$@"
