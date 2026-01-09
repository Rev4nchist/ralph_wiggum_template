#!/bin/bash
# Run Critical Stress Tests (P0)
# These tests must pass before any production deployment

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "=========================================="
echo "RALPH WIGGUM CRITICAL STRESS TESTS (P0)"
echo "=========================================="
echo ""
echo "Prerequisites:"
echo "  - Redis server running on localhost:6379"
echo "  - Python 3.9+ with pytest installed"
echo ""

# Check Redis connection
if ! redis-cli ping > /dev/null 2>&1; then
    echo "ERROR: Redis not available. Start Redis first:"
    echo "  docker run -d -p 6379:6379 redis:7"
    exit 1
fi

echo "Redis: Connected"
echo ""

# Run critical tests
echo "Running P0 Critical Tests..."
echo ""

cd "$PROJECT_ROOT"

pytest tests/stress/scenarios/st001_memory_coherence.py \
       tests/stress/scenarios/st002_lock_contention.py \
       tests/stress/scenarios/st003_handoff_ttl.py \
       tests/stress/scenarios/st004_cascade_failure.py \
       tests/stress/scenarios/st011_full_orchestration_flow.py \
       -v \
       --tb=short \
       -x \
       "$@"

echo ""
echo "=========================================="
echo "CRITICAL TESTS COMPLETE"
echo "=========================================="
