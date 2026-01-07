#!/bin/bash
set -e

# =============================================================================
# Ralph Wiggum Multi-Agent Integration Test
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() { echo -e "${BLUE}[TEST]${NC} $1"; }
pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

TESTS_PASSED=0
TESTS_FAILED=0

assert() {
    local description=$1
    local command=$2

    if eval "$command" > /dev/null 2>&1; then
        pass "$description"
        ((TESTS_PASSED++))
    else
        fail "$description"
        ((TESTS_FAILED++))
    fi
}

# =============================================================================
# Phase 1: Infrastructure
# =============================================================================
phase1_infrastructure() {
    log "=========================================="
    log "Phase 1: Infrastructure Validation"
    log "=========================================="

    # Start Redis if not running
    log "Starting Redis..."
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" up -d redis
    sleep 3

    # Test Redis connection
    assert "Redis responds to ping" \
        "docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli ping | grep -q PONG"

    # Clear any stale data
    log "Clearing stale data..."
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis redis-cli FLUSHDB > /dev/null

    # Check MCP server
    if [ -f "$PROJECT_ROOT/mcp-server/dist/index.js" ]; then
        pass "MCP server built"
        ((TESTS_PASSED++))
    else
        warn "MCP server not built, building now..."
        cd "$PROJECT_ROOT/mcp-server"
        npm install > /dev/null 2>&1
        npm run build > /dev/null 2>&1

        if [ -f "$PROJECT_ROOT/mcp-server/dist/index.js" ]; then
            pass "MCP server built successfully"
            ((TESTS_PASSED++))
        else
            fail "MCP server build failed"
            ((TESTS_FAILED++))
        fi
        cd "$SCRIPT_DIR"
    fi
}

# =============================================================================
# Phase 2: Single Agent Test
# =============================================================================
phase2_single_agent() {
    log "=========================================="
    log "Phase 2: Single Agent Test"
    log "=========================================="

    local WORKSPACE="$SCRIPT_DIR/single-agent-test"

    # Setup workspace
    log "Setting up single agent workspace..."
    rm -rf "$WORKSPACE"
    mkdir -p "$WORKSPACE/plans" "$WORKSPACE/.claude" "$WORKSPACE/src"

    # Create minimal CLAUDE.md
    cat > "$WORKSPACE/.claude/CLAUDE.md" << 'EOF'
# Test Agent
You are a test agent. Complete the tasks in plans/prd.json.
EOF

    # Create simple PRD
    cat > "$WORKSPACE/plans/prd.json" << 'EOF'
[
  {
    "id": "task-001",
    "category": "test",
    "priority": 1,
    "description": "Create a file src/hello.ts that exports a function hello() returning 'world'",
    "acceptance_criteria": [
      "src/hello.ts exists",
      "Exports hello function",
      "Function returns 'world'"
    ],
    "dependencies": [],
    "passes": false
  }
]
EOF

    # Create progress file
    echo "# Test Progress" > "$WORKSPACE/plans/progress.txt"

    # Initialize package.json
    cat > "$WORKSPACE/package.json" << 'EOF'
{
  "name": "single-agent-test",
  "version": "1.0.0",
  "scripts": {
    "build": "echo 'build ok'",
    "test": "echo 'test ok'"
  }
}
EOF

    # Test agent registration with Redis
    log "Testing agent registration..."

    local AGENT_DATA='{"agent_id":"test-agent","agent_type":"test","status":"active"}'
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis \
        redis-cli HSET ralph:agents test-agent "$AGENT_DATA" > /dev/null

    assert "Agent registered in Redis" \
        "docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli HGET ralph:agents test-agent | grep -q test-agent"

    # Test heartbeat
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis \
        redis-cli SETEX ralph:heartbeats:test-agent 30 "$(date -Iseconds)" > /dev/null

    assert "Heartbeat registered" \
        "docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli EXISTS ralph:heartbeats:test-agent | grep -q 1"

    # Clean up registration
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis redis-cli HDEL ralph:agents test-agent > /dev/null
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis redis-cli DEL ralph:heartbeats:test-agent > /dev/null

    # Cleanup
    rm -rf "$WORKSPACE"
}

# =============================================================================
# Phase 3: Task Queue Test
# =============================================================================
phase3_task_queue() {
    log "=========================================="
    log "Phase 3: Task Queue Test"
    log "=========================================="

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Create test task
    local TASK_DATA='{"id":"test-task-001","title":"Test Task","status":"pending","priority":5}'
    eval "$REDIS_CMD SET ralph:tasks:data:test-task-001 '$TASK_DATA'" > /dev/null
    eval "$REDIS_CMD ZADD ralph:tasks:queue 5000000 test-task-001" > /dev/null

    assert "Task added to queue" \
        "eval \"$REDIS_CMD ZRANGE ralph:tasks:queue 0 -1\" | grep -q test-task-001"

    assert "Task data stored" \
        "eval \"$REDIS_CMD GET ralph:tasks:data:test-task-001\" | grep -q 'Test Task'"

    # Test claim
    eval "$REDIS_CMD SETNX ralph:tasks:claimed:test-task-001 test-agent" > /dev/null

    assert "Task claim works" \
        "eval \"$REDIS_CMD GET ralph:tasks:claimed:test-task-001\" | grep -q test-agent"

    # Cleanup
    eval "$REDIS_CMD DEL ralph:tasks:data:test-task-001" > /dev/null
    eval "$REDIS_CMD ZREM ralph:tasks:queue test-task-001" > /dev/null
    eval "$REDIS_CMD DEL ralph:tasks:claimed:test-task-001" > /dev/null
}

# =============================================================================
# Phase 4: File Locking Test
# =============================================================================
phase4_file_locking() {
    log "=========================================="
    log "Phase 4: File Locking Test"
    log "=========================================="

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Acquire lock
    local LOCK_DATA='{"agent_id":"agent-1","file_path":"shared/types.ts"}'
    eval "$REDIS_CMD SET ralph:locks:file:shared:types.ts '$LOCK_DATA' NX EX 60" > /dev/null

    assert "Lock acquired by first agent" \
        "eval \"$REDIS_CMD GET ralph:locks:file:shared:types.ts\" | grep -q agent-1"

    # Try to acquire same lock (should fail)
    local RESULT=$(eval "$REDIS_CMD SET ralph:locks:file:shared:types.ts '{\"agent_id\":\"agent-2\"}' NX")

    if [ -z "$RESULT" ] || [ "$RESULT" = "(nil)" ]; then
        pass "Second agent correctly blocked"
        ((TESTS_PASSED++))
    else
        fail "Second agent should not acquire lock"
        ((TESTS_FAILED++))
    fi

    # Release lock
    eval "$REDIS_CMD DEL ralph:locks:file:shared:types.ts" > /dev/null

    assert "Lock released" \
        "! eval \"$REDIS_CMD EXISTS ralph:locks:file:shared:types.ts\" | grep -q 1"
}

# =============================================================================
# Phase 5: Memory Test
# =============================================================================
phase5_memory() {
    log "=========================================="
    log "Phase 5: Memory Test"
    log "=========================================="

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Store memory
    local MEM_DATA='{"id":"mem-001","category":"architecture","content":"Using Repository pattern"}'
    eval "$REDIS_CMD HSET ralph:memory:test-project mem-001 '$MEM_DATA'" > /dev/null

    assert "Memory stored" \
        "eval \"$REDIS_CMD HGET ralph:memory:test-project mem-001\" | grep -q 'Repository pattern'"

    # Cleanup
    eval "$REDIS_CMD DEL ralph:memory:test-project" > /dev/null
}

# =============================================================================
# Phase 6: Pub/Sub Test
# =============================================================================
phase6_pubsub() {
    log "=========================================="
    log "Phase 6: Pub/Sub Events Test"
    log "=========================================="

    local REDIS_CMD="docker-compose -f '$PROJECT_ROOT/docker-compose.yml' exec -T redis redis-cli"

    # Test publish (just verify it doesn't error)
    eval "$REDIS_CMD PUBLISH ralph:events '{\"event\":\"test\"}'" > /dev/null

    pass "Pub/Sub publish works"
    ((TESTS_PASSED++))

    # Test agent message channel
    eval "$REDIS_CMD PUBLISH ralph:messages:test-agent '{\"type\":\"ping\"}'" > /dev/null

    pass "Agent message channel works"
    ((TESTS_PASSED++))
}

# =============================================================================
# Cleanup
# =============================================================================
cleanup() {
    log "=========================================="
    log "Cleanup"
    log "=========================================="

    # Clear test data
    docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis redis-cli FLUSHDB > /dev/null 2>&1 || true

    pass "Test data cleared"
}

# =============================================================================
# Results
# =============================================================================
print_results() {
    echo ""
    log "=========================================="
    log "Test Results"
    log "=========================================="
    echo ""
    echo -e "  ${GREEN}Passed: $TESTS_PASSED${NC}"
    echo -e "  ${RED}Failed: $TESTS_FAILED${NC}"
    echo ""

    if [ $TESTS_FAILED -eq 0 ]; then
        echo -e "${GREEN}All tests passed! ✓${NC}"
        return 0
    else
        echo -e "${RED}Some tests failed ✗${NC}"
        return 1
    fi
}

# =============================================================================
# Main
# =============================================================================
main() {
    echo ""
    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║     Ralph Wiggum Multi-Agent Integration Test Suite           ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo ""

    cd "$PROJECT_ROOT"

    phase1_infrastructure
    phase2_single_agent
    phase3_task_queue
    phase4_file_locking
    phase5_memory
    phase6_pubsub
    cleanup

    print_results
}

main "$@"
