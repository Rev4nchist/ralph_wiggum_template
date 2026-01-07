# Ralph Wiggum Stress Test Design

> *"The measure of intelligence is the ability to change."*
>
> This test is designed to break things. That's the point.

---

## Philosophy

A system is only as strong as its weakest component under stress. This test suite will:

1. **Find Race Conditions** — Concurrent operations that corrupt state
2. **Expose Resource Leaks** — Locks, connections, memory that never release
3. **Test Recovery** — What happens when things die unexpectedly
4. **Validate Coordination** — Multi-agent scenarios that seem correct but fail
5. **Stress Scale** — What breaks at 10x, 100x, 1000x

---

## Test Categories

### Category 1: Concurrency Chaos

#### Test 1.1: Task Claim Race
**Scenario:** 5 agents simultaneously try to claim the same high-priority task.

```
Agent-1 ─┐
Agent-2 ─┼──► CLAIM task-001 (at exact same millisecond)
Agent-3 ─┤
Agent-4 ─┤
Agent-5 ─┘
```

**Expected:** Exactly ONE agent gets the task. Others get rejection.
**Failure Mode:** Multiple agents think they own the task, duplicate work.
**Test:**
```bash
# Spawn 5 parallel Redis SETNX commands
for i in {1..5}; do
  redis-cli SETNX ralph:tasks:claimed:race-task "agent-$i" &
done
wait
# Verify only one succeeded
redis-cli GET ralph:tasks:claimed:race-task
```

#### Test 1.2: File Lock Stampede
**Scenario:** 10 agents simultaneously request lock on `shared/types.ts`.

**Expected:** One gets lock, 9 wait/retry.
**Failure Mode:** Lock corruption, multiple holders, deadlock.
**Stress Factor:** Increase to 100 agents.

#### Test 1.3: Heartbeat During Heavy Load
**Scenario:** Agent is processing complex task, heartbeat renewal competes with task updates.

**Expected:** Heartbeat continues, agent stays registered.
**Failure Mode:** Agent marked dead while actively working, task orphaned.

---

### Category 2: Failure & Recovery

#### Test 2.1: Agent Death Mid-Task
**Scenario:** Agent crashes while:
- Holding a file lock
- Processing a task (marked in_progress)
- Mid-commit to git

```
Agent-backend:
  1. Claims task-005
  2. Acquires lock on src/api/users.ts
  3. [CRASH - kill -9]
```

**Expected:**
- Lock expires (TTL)
- Task returns to queue
- Another agent picks up

**Failure Mode:**
- Orphaned lock (no TTL or TTL too long)
- Task stuck in "in_progress" forever
- Partial file edits left in workspace

**Test:**
```bash
# Start agent, let it claim task, force kill
AGENT_PID=$(pgrep -f "ralph-multi.sh")
sleep 5  # Let it start working
kill -9 $AGENT_PID

# Wait for lock TTL (default 300s, we'll use 30s for test)
sleep 35

# Verify lock released
redis-cli EXISTS ralph:locks:file:src:api:users.ts
# Expected: 0

# Verify task returned to queue
redis-cli ZSCORE ralph:tasks:queue task-005
# Expected: score (not nil)
```

#### Test 2.2: Redis Connection Loss
**Scenario:** Redis becomes unreachable mid-operation.

```
Agent-frontend:
  1. Reads task from queue → OK
  2. Redis goes down
  3. Tries to update task status → FAIL
  4. Tries to acquire lock → FAIL
```

**Expected:** Agent detects failure, waits/retries, doesn't corrupt state.
**Failure Mode:** Silent failures, inconsistent state, agent continues blindly.

#### Test 2.3: Partial Task Completion
**Scenario:** Task has 5 acceptance criteria. Agent completes 3, crashes.

**Expected:** Task stays incomplete, next agent sees partial state, continues.
**Failure Mode:**
- Task marked complete with partial work
- Next agent redoes everything (wasted work)
- Conflicts from partial + full implementation

---

### Category 3: Dependency Hell

#### Test 3.1: Circular Dependencies
**Scenario:** PRD with circular task dependencies.

```json
[
  {"id": "A", "dependencies": ["C"]},
  {"id": "B", "dependencies": ["A"]},
  {"id": "C", "dependencies": ["B"]}
]
```

**Expected:** System detects cycle, reports error, doesn't deadlock.
**Failure Mode:** All agents wait forever, system appears hung.

#### Test 3.2: Missing Dependency
**Scenario:** Task depends on non-existent task.

```json
{"id": "task-010", "dependencies": ["task-999"]}
```

**Expected:** Clear error, task blocked with explanation.
**Failure Mode:** Task silently skipped, or system crash.

#### Test 3.3: Deep Dependency Chain
**Scenario:** 50-task linear chain where each depends on previous.

```
task-001 → task-002 → task-003 → ... → task-050
```

**Expected:** Sequential execution, correct ordering.
**Failure Mode:**
- Out-of-order execution
- Performance degradation at depth
- Stack overflow in dependency resolver

#### Test 3.4: Diamond Dependency
**Scenario:** Classic diamond problem.

```
        task-A
       /      \
    task-B   task-C
       \      /
        task-D
```

**Expected:** A first, B and C in parallel, D after both complete.
**Failure Mode:** D starts before B or C complete.

---

### Category 4: Multi-Agent Coordination

#### Test 4.1: Shared Types Modification
**Scenario:** Backend and frontend both need to modify `shared/types.ts`.

```
Timeline:
  T0: Backend claims task to add UserType
  T1: Frontend claims task to add ProductType
  T2: Backend acquires lock, starts editing
  T3: Frontend blocked, waiting for lock
  T4: Backend commits, releases lock
  T5: Frontend acquires lock
  T6: Frontend must merge Backend's changes + add own
```

**Expected:** Both changes appear in final file, no conflicts.
**Failure Mode:**
- Frontend overwrites backend's changes
- Merge conflicts
- Lock timeout during merge

#### Test 4.2: Wait-For Timeout
**Scenario:** Frontend task `wait_for: ["be-003"]`, but backend is slow.

```json
{
  "id": "fe-002",
  "wait_for": ["be-003"],
  "timeout": 300
}
```

**Expected:** Frontend waits, eventually times out with clear message.
**Failure Mode:**
- Infinite wait
- No visibility into what's blocking
- Silent skip

#### Test 4.3: Artifact Dependency
**Scenario:** Frontend needs `api-spec.json` artifact from backend.

```
Backend task-004:
  artifacts: ["shared/api-spec.json"]

Frontend task-003:
  artifacts_from: ["task-004"]
```

**Expected:** Frontend waits for artifact, can access it.
**Failure Mode:**
- Artifact path wrong
- Artifact not created
- Artifact created but not signaled

#### Test 4.4: Message Passing Under Load
**Scenario:** Orchestrator sends 100 messages to agent in 1 second.

```bash
for i in {1..100}; do
  redis-cli PUBLISH ralph:messages:agent-1 '{"type":"status_request"}'
done
```

**Expected:** Agent processes all messages (or gracefully drops with backpressure).
**Failure Mode:**
- Messages lost
- Agent overwhelmed, stops responding
- Memory exhaustion

---

### Category 5: Scale Testing

#### Test 5.1: Large PRD
**Scenario:** PRD with 500 tasks, complex dependency graph.

**Metrics to capture:**
- Time to parse PRD
- Memory usage during planning
- Task queue insertion time
- Dependency resolution time

**Expected:** Linear or near-linear scaling.
**Failure Mode:** Exponential slowdown, memory exhaustion.

#### Test 5.2: Many Agents
**Scenario:** 20 agents competing for tasks from same queue.

```
Agents: agent-{1..20}
Tasks: task-{1..100}
```

**Expected:** Fair distribution, no starvation, efficient completion.
**Failure Mode:**
- One agent gets all tasks
- Thrashing (constant claim/release)
- Redis CPU saturation

#### Test 5.3: Long-Running Session
**Scenario:** System runs for 8 hours continuously.

**Monitor:**
- Memory growth over time
- Redis key count growth
- Leaked locks
- Orphaned tasks
- Heartbeat drift

**Expected:** Stable resource usage.
**Failure Mode:** Memory leak, key explosion, eventual OOM.

#### Test 5.4: Large File Handling
**Scenario:** Agent needs to process 10MB source file.

**Expected:** Handles gracefully, maybe with streaming.
**Failure Mode:** Memory exhaustion, timeout, corruption.

---

### Category 6: Specialist Edge Cases

#### Test 6.1: Specialist Chain
**Scenario:** Code review finds issue → triggers debugger → triggers security audit.

```
code-reviewer finds bug
  → spawns debugger task
    → debugger finds security issue
      → spawns security-auditor task
        → security-auditor finds more issues
          → spawns code-reviewer task (CYCLE!)
```

**Expected:** Cycle detection, maximum depth limit.
**Failure Mode:** Infinite specialist spawning.

#### Test 6.2: Wrong Specialist for Task
**Scenario:** Task says `specialist: "security-auditor"` but task is "add button".

**Expected:** Specialist handles gracefully, maybe notes mismatch.
**Failure Mode:** Bizarre security audit of a button component.

#### Test 6.3: Specialist Output Parsing
**Scenario:** Security auditor produces malformed severity classification.

```markdown
## Findings
🔴 CRITICAL: SQL Injection
(but forgets to include Location, Fix, etc.)
```

**Expected:** System handles partial output.
**Failure Mode:** Downstream process crashes on missing fields.

---

### Category 7: Memory System Stress

#### Test 7.1: Memory Conflict
**Scenario:** Two agents store conflicting architectural decisions.

```python
# Agent-backend:
memory.note_architecture("Use SQL", "ACID compliance needed")

# Agent-frontend:
memory.note_architecture("Use NoSQL", "Flexible schema needed")
```

**Expected:** Both stored, conflict surfaced on recall.
**Failure Mode:** One overwrites other silently.

#### Test 7.2: Memory Recall Flood
**Scenario:** 50 memory entries, agent recalls with broad query.

```python
memory.recall("*")  # Everything
```

**Expected:** Paginated results, doesn't overwhelm context.
**Failure Mode:** Returns all 50 in one shot, exceeds context window.

#### Test 7.3: Handoff to Dead Agent
**Scenario:** Agent-1 creates handoff for Agent-2, but Agent-2 never starts.

**Expected:** Handoff persists, eventually expires or is claimed.
**Failure Mode:** Handoff lost, work duplicated.

---

### Category 8: Model Routing

#### Test 8.1: Missing Model Signal
**Scenario:** Agent completes task but never emits `[MODEL: xxx]`.

**Expected:** Default model used, logged.
**Failure Mode:** Wrong model silently used, cost explosion.

#### Test 8.2: Rapid Model Switching
**Scenario:** Task requires frequent context switches.

```
UNDERSTAND [opus] → IMPLEMENT [glm] → VERIFY [minimax] →
REFINE [glm] → REVIEW [opus] → COMMIT [minimax]
```

**Expected:** Each phase uses correct model.
**Failure Mode:**
- Model sticky, doesn't switch
- Cost overrun from using opus for everything
- Context loss between switches

#### Test 8.3: Cost Budget Exceeded
**Scenario:** Project has $50 budget, agents blow through it.

**Expected:** Warning when approaching limit, graceful stop.
**Failure Mode:** Silent overspend, surprise bill.

---

### Category 9: Infrastructure Failures

#### Test 9.1: Redis Restart
**Scenario:** Redis container restarts during operation.

```bash
docker restart ralph-redis
```

**Expected:** Agents reconnect, resume from last known state.
**Failure Mode:**
- Agents crash permanently
- State lost, tasks restart from zero
- Duplicate task execution

#### Test 9.2: MCP Server Restart
**Scenario:** MCP server crashes while Claude Code is connected.

**Expected:** Claude Code shows error, can reconnect.
**Failure Mode:** Claude Code session corrupted.

#### Test 9.3: Disk Full
**Scenario:** Workspace disk fills up during git commit.

**Expected:** Clear error, no data corruption.
**Failure Mode:** Partial commit, corrupted repo.

#### Test 9.4: Network Partition
**Scenario:** Agent can reach Redis but not external APIs.

**Expected:** Agent continues coordination, fails tasks requiring external access.
**Failure Mode:** Silent failures, tasks marked complete without actual work.

---

### Category 10: Real-World Chaos

#### Test 10.1: The Thundering Herd
**Scenario:** System idle, then 100 tasks added at once.

**Expected:** Smooth ramp-up, tasks distributed.
**Failure Mode:**
- Redis overwhelmed
- All agents claim same tasks
- Cascade of lock conflicts

#### Test 10.2: The Slow Consumer
**Scenario:** One agent 10x slower than others.

```
Agent-fast: 10 tasks/hour
Agent-slow: 1 task/hour
```

**Expected:** Fast agent compensates, slow agent contributes.
**Failure Mode:**
- Slow agent hogs tasks it can't complete
- System waits for slow agent

#### Test 10.3: The Flapping Agent
**Scenario:** Agent keeps crashing and restarting every 30 seconds.

**Expected:** System detects instability, stops assigning tasks.
**Failure Mode:**
- Tasks constantly claimed and orphaned
- Progress never made
- No alerting

#### Test 10.4: The Byzantine Agent
**Scenario:** Agent is compromised/buggy, sends malformed data.

```python
# Evil agent sends:
redis.hset("ralph:agents", "evil-agent", "not-json-at-all")
redis.publish("ralph:events", b"\x00\xff\xfe")
```

**Expected:** System rejects malformed data, doesn't crash.
**Failure Mode:**
- System crash
- Data corruption
- Security breach

---

## Test Execution Framework

### Setup

```bash
#!/bin/bash
# tests/stress/setup.sh

# Start fresh Redis
docker-compose down
docker-compose up -d redis
sleep 3
redis-cli FLUSHALL

# Build MCP server
cd mcp-server && npm run build && cd ..

# Create test workspaces
for i in {1..10}; do
  ./scripts/setup-agent-workspace.sh \
    ./tests/stress/agent-$i \
    agent-$i \
    general \
    "implement,test"
done
```

### Metrics Collection

```bash
#!/bin/bash
# tests/stress/metrics.sh

# Collect every 5 seconds
while true; do
  TIMESTAMP=$(date +%s)

  # Redis metrics
  KEYS=$(redis-cli DBSIZE | awk '{print $2}')
  MEMORY=$(redis-cli INFO memory | grep used_memory: | cut -d: -f2)

  # Task metrics
  QUEUE_SIZE=$(redis-cli ZCARD ralph:tasks:queue)
  CLAIMED=$(redis-cli KEYS "ralph:tasks:claimed:*" | wc -l)
  COMPLETED=$(redis-cli SCARD ralph:tasks:completed)

  # Agent metrics
  AGENTS=$(redis-cli HLEN ralph:agents)
  LOCKS=$(redis-cli KEYS "ralph:locks:*" | wc -l)

  echo "$TIMESTAMP,$KEYS,$MEMORY,$QUEUE_SIZE,$CLAIMED,$COMPLETED,$AGENTS,$LOCKS" >> metrics.csv

  sleep 5
done
```

### Test Harness

```python
# tests/stress/harness.py

import redis
import time
import threading
import json
from dataclasses import dataclass
from typing import List, Callable

@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    errors: List[str]
    metrics: dict

class StressTestHarness:
    def __init__(self, redis_url="redis://localhost:6379"):
        self.redis = redis.from_url(redis_url)
        self.results: List[TestResult] = []

    def run_test(self, name: str, test_fn: Callable, timeout: int = 60):
        """Run a single test with timeout and metrics collection."""
        start = time.time()
        errors = []
        metrics = {}

        try:
            # Run test in thread with timeout
            result = {"passed": False}
            def wrapper():
                try:
                    test_fn(self.redis, metrics)
                    result["passed"] = True
                except Exception as e:
                    errors.append(str(e))

            thread = threading.Thread(target=wrapper)
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                errors.append(f"Test timed out after {timeout}s")
        except Exception as e:
            errors.append(f"Test setup failed: {e}")

        duration = time.time() - start
        test_result = TestResult(
            name=name,
            passed=len(errors) == 0 and result.get("passed", False),
            duration=duration,
            errors=errors,
            metrics=metrics
        )
        self.results.append(test_result)
        return test_result

    def report(self):
        """Generate test report."""
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed

        print(f"\n{'='*60}")
        print(f"STRESS TEST RESULTS")
        print(f"{'='*60}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print()

        for r in self.results:
            status = "✓" if r.passed else "✗"
            print(f"{status} {r.name} ({r.duration:.2f}s)")
            if r.errors:
                for e in r.errors:
                    print(f"    ERROR: {e}")
            if r.metrics:
                for k, v in r.metrics.items():
                    print(f"    {k}: {v}")
```

---

## Priority Ranking

### Must Test First (Critical Path)
1. **Test 1.1** - Task Claim Race (core functionality)
2. **Test 2.1** - Agent Death Mid-Task (recovery)
3. **Test 3.4** - Diamond Dependency (coordination)
4. **Test 4.1** - Shared Types Modification (real-world)

### Should Test (Important Edge Cases)
5. **Test 1.2** - File Lock Stampede
6. **Test 3.1** - Circular Dependencies
7. **Test 5.2** - Many Agents
8. **Test 9.1** - Redis Restart

### Nice to Test (Deep Edge Cases)
9. **Test 6.1** - Specialist Chain
10. **Test 10.4** - Byzantine Agent
11. **Test 7.1** - Memory Conflict
12. **Test 5.3** - Long-Running Session

---

## Expected Outcomes

After running this test suite, we will have:

### Known Weaknesses (Likely to Find)
1. **Lock TTL too long** - Default 300s means 5 min wait on agent death
2. **No circuit breaker** - Redis failure cascades to all agents
3. ~~**No dependency cycle detection** - System will deadlock~~ ✅ **FIXED** - Cycle detection implemented in MCP server
4. **No cost tracking** - Model routing has no budget enforcement
5. **Memory recall unbounded** - Could overwhelm context

### Metrics Dashboard Needs
- Task throughput (tasks/hour)
- Lock contention rate
- Agent health score
- Memory growth rate
- Model cost per task

### Documentation Gaps
- Recovery procedures for each failure mode
- Tuning guide for scale parameters
- Monitoring/alerting recommendations

---

## Implementation Order

```
Week 1: Critical Path Tests (1.1, 2.1, 3.4, 4.1)
        → Identify blocking issues

Week 2: Important Edge Cases (1.2, 3.1, 5.2, 9.1)
        → Harden coordination layer

Week 3: Deep Edge Cases (6.1, 10.4, 7.1)
        → Polish and edge case handling

Week 4: Long-Running Test (5.3)
        → Stability validation
```

---

## Success Criteria

The system passes stress testing when:

1. **No data loss** under any failure scenario
2. **No silent failures** - all errors logged/surfaced
3. **Recovery time < 30s** for agent death
4. **Linear scaling** to 20 agents
5. **Stable memory** over 8-hour run
6. **Clear error messages** for invalid states

---

*"Move fast and break things. Then fix them properly."*
