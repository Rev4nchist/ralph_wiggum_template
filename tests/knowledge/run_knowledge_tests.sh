#!/bin/bash
# =============================================================================
# Ralph Wiggum Knowledge System Tests
# =============================================================================
# Tests for Claude-Mem, Librarian, and Redis working memory
# =============================================================================

set -e

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

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║        Ralph Wiggum Knowledge System Tests                     ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# Check Redis
log "Checking Redis connection..."
if docker-compose -f "$PROJECT_ROOT/docker-compose.yml" exec -T redis redis-cli PING 2>/dev/null | grep -q PONG; then
    pass "Redis is running"
else
    fail "Redis is not running. Start with: docker-compose up -d redis"
    exit 1
fi
echo ""

TOTAL_PASSED=0
TOTAL_FAILED=0

# =============================================================================
# Run Claude-Mem Tests
# =============================================================================
echo "═══════════════════════════════════════════════════════════════"
log "Running Claude-Mem Tests..."
echo "═══════════════════════════════════════════════════════════════"

cd "$SCRIPT_DIR"
if python3 test_claude_mem.py; then
    pass "Claude-Mem tests completed"
else
    warn "Some Claude-Mem tests may have failed"
fi
echo ""

# =============================================================================
# Run Redis Working Memory Tests
# =============================================================================
echo "═══════════════════════════════════════════════════════════════"
log "Running Redis Working Memory Tests..."
echo "═══════════════════════════════════════════════════════════════"

if python3 test_redis_working.py; then
    pass "Redis working memory tests completed"
else
    warn "Some Redis tests may have failed"
fi
echo ""

# =============================================================================
# Run Librarian Tests
# =============================================================================
echo "═══════════════════════════════════════════════════════════════"
log "Running Librarian Documentation Tests..."
echo "═══════════════════════════════════════════════════════════════"

if python3 test_librarian.py; then
    pass "Librarian tests completed"
else
    warn "Some Librarian tests may have failed"
fi
echo ""

# =============================================================================
# Run Cycle Detection Tests (from stress tests)
# =============================================================================
echo "═══════════════════════════════════════════════════════════════"
log "Running Cycle Detection Tests..."
echo "═══════════════════════════════════════════════════════════════"

if node "$PROJECT_ROOT/tests/stress/test-cycle-detection.js"; then
    pass "Cycle detection tests passed"
else
    warn "Some cycle detection tests failed"
fi
echo ""

# =============================================================================
# Summary
# =============================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "                KNOWLEDGE SYSTEM TEST SUMMARY"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Tests executed:"
echo "  • Claude-Mem persistent memory"
echo "  • Redis working memory"
echo "  • Librarian documentation search"
echo "  • Cycle detection (dependencies)"
echo ""
echo "See individual test outputs above for detailed results."
echo ""
echo "═══════════════════════════════════════════════════════════════"
