"""
Ralph Wiggum Stress Test Suite

Tests designed to expose real failure modes in multi-agent orchestration:
- ST-001: Memory Coherence (10+ concurrent agent writes)
- ST-002: Lock Contention (100 agents, 10 files)
- ST-003: Handoff TTL Expiry (chain breaks mid-execution)
- ST-004: Cascade Agent Failures (50% crash mid-wave)
- ST-005: Large DAG (100+ tasks with complex dependencies)
- ST-006: Queue Backpressure (500 tasks, 80% fail deps)
- ST-007: Memory Recall Scalability (1000+ memories)
- ST-008: Wave Timing Race Conditions
- ST-009: Byzantine Agent (malformed data)
- ST-010: Memory Conflict Resolution
- ST-011: Full Orchestration Flow (complete PRD to tested code)

Run with: pytest tests/stress/ -v --tb=short
"""
