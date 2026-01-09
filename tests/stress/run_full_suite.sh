#!/bin/bash
# Run Full Stress Test Suite (All 11 Tests)
# Complete validation of the multi-agent orchestration system

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

echo "=========================================="
echo "RALPH WIGGUM FULL STRESS TEST SUITE"
echo "=========================================="
echo ""
echo "Test Suite Overview:"
echo "  P0 Critical (Must Pass):"
echo "    ST-001: Memory Coherence Under Load"
echo "    ST-002: Lock Contention Stampede"
echo "    ST-003: Handoff Chain TTL Expiry"
echo "    ST-004: Cascade Agent Failures"
echo "    ST-011: Full Orchestration Flow"
echo ""
echo "  P1 High Priority:"
echo "    ST-005: Large DAG Stress"
echo "    ST-006: Queue Backpressure"
echo "    ST-007: Memory Recall Scalability"
echo ""
echo "  P2 Edge Cases:"
echo "    ST-008: Wave Timing Race Conditions"
echo "    ST-009: Byzantine Agent (Malformed Data)"
echo "    ST-010: Memory Conflict Resolution"
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

START_TIME=$(date +%s)

echo "=========================================="
echo "PHASE 1: P0 CRITICAL TESTS"
echo "=========================================="
pytest tests/stress/scenarios/st001_memory_coherence.py -v --tb=short "$@"
pytest tests/stress/scenarios/st002_lock_contention.py -v --tb=short "$@"
pytest tests/stress/scenarios/st003_handoff_ttl.py -v --tb=short "$@"
pytest tests/stress/scenarios/st004_cascade_failure.py -v --tb=short "$@"
pytest tests/stress/scenarios/st011_full_orchestration_flow.py -v --tb=short "$@"

echo ""
echo "=========================================="
echo "PHASE 2: P1 HIGH PRIORITY TESTS"
echo "=========================================="
pytest tests/stress/scenarios/st005_large_dag.py -v --tb=short "$@"
pytest tests/stress/scenarios/st006_queue_backpressure.py -v --tb=short "$@"
pytest tests/stress/scenarios/st007_memory_recall.py -v --tb=short "$@"

echo ""
echo "=========================================="
echo "PHASE 3: P2 EDGE CASE TESTS"
echo "=========================================="
pytest tests/stress/scenarios/st008_wave_timing.py -v --tb=short "$@"
pytest tests/stress/scenarios/st009_byzantine_agent.py -v --tb=short "$@"
pytest tests/stress/scenarios/st010_memory_conflict.py -v --tb=short "$@"

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "=========================================="
echo "FULL STRESS TEST SUITE COMPLETE"
echo "=========================================="
echo "Total Duration: ${DURATION} seconds"
echo ""
echo "All 11 stress tests passed!"
echo "System validated for:"
echo "  ✓ 100+ concurrent agents"
echo "  ✓ 500+ task orchestration"
echo "  ✓ Cascade failure recovery"
echo "  ✓ Memory coherence at scale"
echo "  ✓ Lock contention handling"
echo "  ✓ Multi-agent coordination"
echo "=========================================="
