# Ralph Wiggum Knowledge System Test Design

> *"The system learns. The system improves. The system crafts better code."*

---

## Philosophy

The knowledge system is the brain of the multi-agent platform. These tests verify that:

1. **Claude-Mem** stores and retrieves memories reliably
2. **Librarian** provides accurate documentation lookup
3. **Redis** coordinates real-time state efficiently
4. **Integration** ensures all three work together seamlessly

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    KNOWLEDGE ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   LIBRARIAN     │  │   CLAUDE-MEM    │  │     REDIS       │  │
│  │   (External)    │  │  (Persistent)   │  │   (Working)     │  │
│  │                 │  │                 │  │                 │  │
│  │ • API Docs      │  │ • Architecture  │  │ • Task Queue    │  │
│  │ • Best Practices│  │ • Patterns      │  │ • File Locks    │  │
│  │ • Up-to-date    │  │ • Blockers      │  │ • Agent Registry│  │
│  │                 │  │ • Handoffs      │  │ • Pub/Sub       │  │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  │
│           │                    │                    │           │
│           └────────────────────┼────────────────────┘           │
│                                │                                │
│                    ┌───────────▼───────────┐                    │
│                    │   AGENT CONTEXT       │                    │
│                    │   (Unified View)      │                    │
│                    └───────────────────────┘                    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Test Categories

### Category 1: Claude-Mem (Persistent Memory)

#### Test 1.1: Memory Store and Recall
**Scenario:** Store a memory and retrieve it.

```python
memory = ProjectMemory(project_id="test-project", agent_id="agent-1")

# Store
mem_id = memory.remember(
    content="React components use PascalCase",
    category="pattern",
    scope="project"
)

# Recall
results = memory.recall(query="React component naming")
assert len(results) > 0
assert "PascalCase" in results[0].content
```

**Expected:** Memory stored and retrieved with relevance score.
**Failure Mode:** Memory not found, incorrect category, low relevance.

---

#### Test 1.2: Memory Categories
**Scenario:** Each category stored and retrieved correctly.

| Category | Test Content |
|----------|--------------|
| `architecture` | "Using Repository pattern for data access" |
| `pattern` | "All API calls wrapped in try-catch" |
| `decision` | "Chose jose over jsonwebtoken for edge runtime" |
| `blocker` | "ESM modules fixed with transformIgnorePatterns" |
| `learning` | "Middleware pattern cleaner than per-route auth" |
| `handoff` | "Auth complete, frontend can integrate" |
| `quality` | "All components must have unit tests" |

**Expected:** Category filtering returns only matching memories.
**Failure Mode:** Cross-category pollution, missing results.

---

#### Test 1.3: Memory Scopes
**Scenario:** Scope isolation between project, task, and agent.

```
Project Scope:  visible to all agents
Task Scope:     visible to agents working on same task
Agent Scope:    visible only to specific agent
```

**Test:**
```python
# Agent 1 stores project-scoped memory
agent1_mem = ProjectMemory(project_id="p1", agent_id="agent-1")
agent1_mem.remember("Project-wide pattern", scope="project")

# Agent 2 stores agent-scoped memory
agent2_mem = ProjectMemory(project_id="p1", agent_id="agent-2")
agent2_mem.remember("Agent 2 private note", scope="agent")

# Agent 1 should see project scope, not agent-2 scope
results = agent1_mem.recall("pattern", scope="agent")
# Should NOT contain Agent 2's private note
```

**Expected:** Proper scope isolation.
**Failure Mode:** Scope leakage, privacy violation.

---

#### Test 1.4: Handoff Continuity
**Scenario:** Agent 1 completes task, Agent 2 continues.

```
Agent-1: task-001 ──► [Complete with handoff notes]
                              │
                              ▼
Agent-2: task-001 ──► [Receives handoff context]
```

**Test:**
```python
# Agent 1 completes and hands off
mem1 = ProjectMemory(project_id="p1", agent_id="agent-1")
mem1.handoff(
    task_id="task-001",
    summary="Auth backend complete",
    next_steps=["Implement frontend login", "Add refresh token"]
)

# Agent 2 receives context
mem2 = ProjectMemory(project_id="p1", agent_id="agent-2")
context = mem2.get_task_context("task-001")
assert "Auth backend complete" in context
assert "frontend login" in context
```

**Expected:** Seamless handoff with full context.
**Failure Mode:** Lost context, incomplete handoff.

---

#### Test 1.5: Memory Conflict Resolution
**Scenario:** Two agents store conflicting architecture decisions.

```
Agent-1: "Using REST API"     ──┐
                                ├──► Which is canonical?
Agent-2: "Using GraphQL API"  ──┘
```

**Expected:** Later decision has precedence, or conflict flagged.
**Failure Mode:** Silent conflict, data loss.

---

#### Test 1.6: Memory Relevance Scoring
**Scenario:** Query returns results in relevance order.

```python
memory.remember("React hooks for state management", category="pattern")
memory.remember("Redux for complex state", category="pattern")
memory.remember("CSS styling with Tailwind", category="pattern")

results = memory.recall("state management React")
# Results should be ordered: hooks > Redux > Tailwind
```

**Expected:** Semantic relevance ordering.
**Failure Mode:** Random order, irrelevant results first.

---

#### Test 1.7: Memory Persistence Across Sessions
**Scenario:** Memories survive container restart.

```
Session 1: Store architecture decision
         ──► [Container restart]
Session 2: Recall architecture decision
```

**Expected:** Memory persists across restarts.
**Failure Mode:** Data loss, corruption.

---

### Category 2: Librarian (Documentation Search)

#### Test 2.1: Library Documentation Lookup
**Scenario:** Search for library-specific documentation.

```bash
librarian search --library react "useEffect cleanup"
librarian search --library nextjs "server actions"
librarian search --library prisma "relation queries"
```

**Expected:** Relevant, up-to-date documentation returned.
**Failure Mode:** Stale docs, wrong library, no results.

---

#### Test 2.2: Best Practices Retrieval
**Scenario:** Query for established patterns.

```bash
librarian search --library typescript "generic constraints best practices"
```

**Expected:** Official best practices returned.
**Failure Mode:** Unofficial/outdated advice.

---

#### Test 2.3: Error Message Resolution
**Scenario:** Search for error solutions.

```bash
librarian search --library prisma "P2002 unique constraint failed"
```

**Expected:** Specific error resolution steps.
**Failure Mode:** Generic advice, wrong error.

---

#### Test 2.4: Cross-Library Search
**Scenario:** Search across multiple libraries.

```bash
librarian search "authentication JWT"
# Should search across: nextjs, express, jose, etc.
```

**Expected:** Results from relevant libraries.
**Failure Mode:** Single-library tunnel vision.

---

#### Test 2.5: Documentation Freshness
**Scenario:** Verify docs are current.

```
Library Version: react@19.0.0
Documentation:   Should reference React 19 features
```

**Expected:** Docs match installed version or latest.
**Failure Mode:** Outdated docs for new features.

---

#### Test 2.6: Research Protocol Integration
**Scenario:** Librarian feeds into Claude-Mem.

```
1. Agent searches: librarian search --library nextjs "app router"
2. Agent implements feature
3. Agent stores learning: memory.note_pattern("App Router", ...)
4. Future agents benefit from both Librarian AND stored learnings
```

**Expected:** Knowledge compounds over time.
**Failure Mode:** Redundant research, no learning retention.

---

### Category 3: Redis Working Memory

#### Test 3.1: Agent Registry Accuracy
**Scenario:** Registry reflects true agent state.

```python
# Agent starts
client = RalphClient(agent_id="agent-test", agent_type="frontend")
client.start()

# Registry should show agent
agents = client.get_active_agents()
assert any(a['agent_id'] == 'agent-test' for a in agents)

# Agent stops
client.stop()

# Registry should NOT show agent (after heartbeat TTL)
time.sleep(HEARTBEAT_TTL + 1)
agents_after = client.get_active_agents()
assert not any(a['agent_id'] == 'agent-test' for a in agents_after)
```

**Expected:** Registry accurate within heartbeat TTL.
**Failure Mode:** Ghost agents, missing agents.

---

#### Test 3.2: Task State Consistency
**Scenario:** Task state consistent across all views.

```
Task created    ──► queue shows pending
Task claimed    ──► queue removes, data shows claimed
Task completed  ──► data shows completed with result
```

**Test:**
```python
task = Task(id="t1", title="Test", description="Test task")
queue.enqueue(task)
assert queue.get("t1").status == "pending"

queue.claim(task)
assert queue.get("t1").status == "claimed"
assert queue.get("t1").assigned_to == agent_id

queue.complete("t1", {"result": "success"})
assert queue.get("t1").status == "completed"
```

**Expected:** State transitions are atomic and consistent.
**Failure Mode:** Race conditions, stuck states.

---

#### Test 3.3: Artifact Sharing
**Scenario:** Agent stores artifact, others retrieve.

```python
# Agent 1 produces artifact
client1.store_artifact("build-output", {"files": ["dist/app.js"]}, task_id="t1")

# Agent 2 retrieves artifact
artifact = client2.get_artifact("agent-1:build-output:...")
assert artifact['data']['files'] == ["dist/app.js"]
```

**Expected:** Artifacts accessible to all agents.
**Failure Mode:** Missing artifacts, access denied.

---

#### Test 3.4: Event Pub/Sub Reliability
**Scenario:** Events published and received by all subscribers.

```python
events_received = []

def handler(event):
    events_received.append(event)

# Subscribe
client1.on_message('task_completed')(handler)
client2.on_message('task_completed')(handler)

# Publish
client3.broadcast('task_completed', {'task_id': 't1'})

# Both should receive
assert len(events_received) == 2
```

**Expected:** All subscribers receive events.
**Failure Mode:** Lost events, duplicate events.

---

#### Test 3.5: Memory-Redis Dual Write
**Scenario:** Claude-Mem and Redis both updated.

```python
# When storing memory, both should be updated
memory = ProjectMemory(project_id="p1", agent_id="a1", redis_client=redis)
mem_id = memory.remember("Test pattern", category="pattern")

# Verify Redis has the memory
redis_data = redis.hget("ralph:memory:p1", mem_id)
assert redis_data is not None

# Verify Claude-Mem has the memory (via recall)
results = memory.recall("Test pattern")
assert len(results) > 0
```

**Expected:** Dual write consistency.
**Failure Mode:** Partial write, inconsistent state.

---

### Category 4: Integration & Efficiency

#### Test 4.1: Agent Context Loading Time
**Scenario:** Measure time to load full agent context.

```
Context includes:
  - Project memories (Claude-Mem)
  - Task context (Claude-Mem)
  - Active agents (Redis)
  - Task queue (Redis)
  - Relevant docs (Librarian)
```

**Metrics:**
| Operation | Target | Acceptable |
|-----------|--------|------------|
| Project memories | < 500ms | < 1000ms |
| Task context | < 200ms | < 500ms |
| Agent registry | < 50ms | < 100ms |
| Task queue | < 100ms | < 200ms |
| Doc search | < 2000ms | < 5000ms |
| **Total Context** | < 3000ms | < 7000ms |

**Expected:** Context loads within target time.
**Failure Mode:** Slow context load, agent startup delay.

---

#### Test 4.2: Memory Growth Management
**Scenario:** System handles growing memory gracefully.

```
Phase 1: 10 memories     ──► Recall time baseline
Phase 2: 100 memories    ──► Recall time < 2x baseline
Phase 3: 1000 memories   ──► Recall time < 5x baseline
```

**Expected:** Sub-linear recall time growth.
**Failure Mode:** Linear/exponential slowdown.

---

#### Test 4.3: Multi-Agent Knowledge Sharing
**Scenario:** Multiple agents sharing knowledge efficiently.

```
                    ┌─────────────┐
                    │  Agent-1    │
                    │ (Frontend)  │
                    └──────┬──────┘
                           │ Store: "React pattern"
                           ▼
                    ┌─────────────┐
                    │ Shared Mem  │ ◄── Claude-Mem + Redis
                    └──────┬──────┘
                           │ Recall: "React pattern"
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
   │  Agent-2    │  │  Agent-3    │  │  Agent-4    │
   │ (Frontend)  │  │ (Backend)   │  │(Integration)│
   └─────────────┘  └─────────────┘  └─────────────┘
```

**Test:**
- Agent-1 stores pattern
- Agent-2,3,4 each recall pattern
- All should get same result

**Expected:** Knowledge immediately available to all agents.
**Failure Mode:** Propagation delay, inconsistent views.

---

#### Test 4.4: Research-First Workflow
**Scenario:** Agent follows research-first protocol.

```
1. Task: "Implement OAuth with Google"
2. Agent checks Claude-Mem for existing patterns ──► None found
3. Agent searches Librarian for OAuth docs ──► Finds best practices
4. Agent implements following docs
5. Agent stores learnings in Claude-Mem
6. Future: Next agent finds stored pattern ──► Skips Librarian
```

**Expected:** Research compounds, agents get smarter.
**Failure Mode:** Redundant research, no learning.

---

#### Test 4.5: Blocker Resolution Efficiency
**Scenario:** Agent encounters known blocker.

```
Agent-1 (Past):
  - Encountered: "Jest ESM module error"
  - Solved: "transformIgnorePatterns config"
  - Stored blocker in Claude-Mem

Agent-2 (Now):
  - Encounters: "Jest ESM module error"
  - Recalls blocker from Claude-Mem
  - Applies known solution immediately
```

**Metrics:**
- Time without prior knowledge: ~30 minutes (research, trial/error)
- Time with stored blocker: < 2 minutes (apply known fix)

**Expected:** 10x+ speedup for known blockers.
**Failure Mode:** Blocker not found, redundant debugging.

---

#### Test 4.6: Handoff Chain Integrity
**Scenario:** Task passes through 3 agents.

```
Agent-1: Design API    ──► Handoff ──► Agent-2: Implement API ──► Handoff ──► Agent-3: Test API
            │                                      │                                    │
            └──► context preserved ◄───────────────┴────────────────────────────────────┘
```

**Test:**
```python
# Agent 1 designs
mem1 = ProjectMemory(project_id="p1", agent_id="a1")
mem1.note_architecture("REST API with /users endpoint", "Follows team conventions")
mem1.handoff("task-api", "Design complete", ["Implement CRUD operations"])

# Agent 2 implements
mem2 = ProjectMemory(project_id="p1", agent_id="a2")
ctx2 = mem2.get_task_context("task-api")
assert "REST API" in ctx2
mem2.note_pattern("User controller pattern", "see src/controllers/users.ts")
mem2.handoff("task-api", "Implementation complete", ["Add integration tests"])

# Agent 3 tests
mem3 = ProjectMemory(project_id="p1", agent_id="a3")
ctx3 = mem3.get_task_context("task-api")
assert "REST API" in ctx3
assert "User controller" in ctx3
```

**Expected:** Full context chain preserved.
**Failure Mode:** Context loss, incomplete handoff.

---

#### Test 4.7: System Recovery
**Scenario:** System recovers from partial failures.

```
Failure Scenarios:
  1. Redis restart ──► Agents re-register, tasks resume
  2. Claude-Mem unavailable ──► Fallback to Redis cache
  3. Librarian timeout ──► Use cached docs or proceed without
```

**Expected:** Graceful degradation, no data loss.
**Failure Mode:** System halt, data corruption.

---

## Implementation Priority

### Phase 1: Core Memory Tests (Critical)
```
Test 1.1 - Memory Store and Recall
Test 1.4 - Handoff Continuity
Test 3.2 - Task State Consistency
Test 3.5 - Memory-Redis Dual Write
```

### Phase 2: Efficiency Tests (High)
```
Test 4.1 - Agent Context Loading Time
Test 4.3 - Multi-Agent Knowledge Sharing
Test 4.5 - Blocker Resolution Efficiency
```

### Phase 3: Edge Cases (Medium)
```
Test 1.3 - Memory Scopes
Test 1.5 - Memory Conflict Resolution
Test 1.6 - Memory Relevance Scoring
Test 4.2 - Memory Growth Management
```

### Phase 4: Integration Tests (Medium)
```
Test 2.6 - Research Protocol Integration
Test 4.4 - Research-First Workflow
Test 4.6 - Handoff Chain Integrity
Test 4.7 - System Recovery
```

---

## Expected Outcomes

### Success Criteria
1. **Memory Operations**: < 500ms average latency
2. **Recall Accuracy**: > 90% relevant results in top 5
3. **Handoff Completeness**: 100% context preservation
4. **Agent Discovery**: < 100ms registry queries
5. **Knowledge Reuse**: > 50% of tasks benefit from prior learnings

### Known Gaps to Address
1. ~~**Librarian Implementation**: Currently conceptual, needs concrete implementation~~ ✅ **IMPLEMENTED** - `lib/librarian/` with client, protocol, mock for testing
2. **Memory Conflict Resolution**: No current strategy for conflicting decisions
3. **Relevance Scoring**: Depends on Claude-Mem MCP implementation
4. **Cache Strategy**: Redis cache for Claude-Mem not fully implemented

### Metrics Dashboard
```
┌─────────────────────────────────────────────────────────────┐
│                KNOWLEDGE SYSTEM METRICS                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Memory Store Rate:     ████████████░░░░  75/hr             │
│  Memory Recall Time:    ████████░░░░░░░░  320ms avg         │
│  Handoff Success:       ████████████████  100%              │
│  Knowledge Reuse:       ██████████░░░░░░  62%               │
│  Blocker Hit Rate:      ████████░░░░░░░░  45%               │
│                                                              │
│  Active Agents:         3                                    │
│  Total Memories:        247                                  │
│  Tasks Completed:       89                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Test Implementation Files

```
tests/knowledge/
├── KNOWLEDGE-TEST-DESIGN.md    # This document
├── test_claude_mem.py          # Claude-Mem unit tests (15 tests)
├── test_librarian.py           # Librarian unit tests (40 tests) ✅ IMPLEMENTED
├── test_redis_working.py       # Redis working memory tests (16 tests)
├── test_integration.py         # Integration tests (TODO)
├── test_efficiency.py          # Performance/efficiency tests (TODO)
└── run_knowledge_tests.sh      # Test runner script
```

### Current Test Summary
| Component | Tests | Status |
|-----------|-------|--------|
| Claude-Mem | 15 | ✅ Passing |
| Librarian | 40 | ✅ Passing |
| Redis Working Memory | 16 | ✅ Passing |
| Cycle Detection | 8 | ✅ Passing |
| **Total** | **79** | **All Passing** |

---

*Every memory stored makes the next agent wiser.*
*Every pattern documented prevents the next blocker.*
*Every handoff note enables seamless continuity.*

**The system learns. The system improves. The system crafts better code.**
