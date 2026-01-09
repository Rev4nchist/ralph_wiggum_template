#!/bin/bash
# Run Production Stress Tests (P0 + P1)
# These tests validate production readiness

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "=========================================="
echo "RALPH WIGGUM PRODUCTION STRESS TESTS"
echo "(P0 Critical + P1 High Priority)"
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

cd "$PROJECT_ROOT"

echo "=== P0 CRITICAL TESTS ==="
pytest tests/stress/scenarios/st001_memory_coherence.py \
       tests/stress/scenarios/st002_lock_contention.py \
       tests/stress/scenarios/st003_handoff_ttl.py \
       tests/stress/scenarios/st004_cascade_failure.py \
       tests/stress/scenarios/st011_full_orchestration_flow.py \
       -v \
       --tb=short \
       "$@"

echo ""
echo "=== P1 HIGH PRIORITY TESTS ==="
pytest tests/stress/scenarios/st005_large_dag.py \
       tests/stress/scenarios/st006_queue_backpressure.py \
       tests/stress/scenarios/st007_memory_recall.py \
       -v \
       --tb=short \
       "$@"

echo ""
echo "=========================================="
echo "PRODUCTION TESTS COMPLETE"
echo "=========================================="
