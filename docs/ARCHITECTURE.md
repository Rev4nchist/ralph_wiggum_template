# Ralph Wiggum Architecture Guide

## Complete Multi-Agent Orchestration Platform

**Version:** 1.0.0
**Tests:** 477 passing
**Last Updated:** 2025-01-08

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Architecture Diagram](#2-architecture-diagram)
3. [Core Components](#3-core-components)
4. [Data Flow & Communication](#4-data-flow--communication)
5. [Redis Schema Reference](#5-redis-schema-reference)
6. [Agent Types & Selection](#6-agent-types--selection)
7. [Complete Workflow Example](#7-complete-workflow-example)
8. [Memory System Deep Dive](#8-memory-system-deep-dive)
9. [Orchestration Protocol](#9-orchestration-protocol)
10. [Security & Coordination](#10-security--coordination)
11. [Extension Points](#11-extension-points)

---

## 1. System Overview

### What is Ralph Wiggum?

Ralph Wiggum is a **multi-agent autonomous coding platform** that enables multiple AI agents to collaborate on software projects. Unlike single-agent systems that process tasks sequentially, Ralph Wiggum:

- **Parallelizes work** across specialized agents (frontend, backend, QA, etc.)
- **Prevents conflicts** via atomic task claiming and file locking
- **Maintains context** through persistent memory across sessions
- **Enables human oversight** via Telegram notifications and approval gates

### Core Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Parallel Execution** | Multiple agents work simultaneously on independent tasks |
| **Atomic Operations** | Lua scripts ensure race-condition-free task claiming |
| **Pessimistic Locking** | File locks prevent simultaneous edits |
| **Persistent Memory** | Redis + Claude-Mem survive across sessions |
| **Human-in-the-Loop** | Telegram notifications for escalation |

### Key Metrics

- **18 MCP Tools** for Claude Code integration
- **7 Specialist Agent Types** with automatic selection
- **477 Passing Tests** with zero known race conditions
- **4 Memory Categories** for context preservation

---

## 2. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLAUDE CODE (Human Interface)                    │
│                    User interacts via natural language                   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ MCP Protocol
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         MCP SERVER (TypeScript)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │ Orchestration   │  │ Librarian       │  │ Memory                  │  │
│  │ Tools (11)      │  │ Tools (6)       │  │ Tools (4)               │  │
│  │                 │  │                 │  │                         │  │
│  │ • list_agents   │  │ • search        │  │ • memory_store          │  │
│  │ • send_task     │  │ • list_sources  │  │ • memory_recall         │  │
│  │ • broadcast     │  │ • get_document  │  │ • memory_context        │  │
│  │ • get_status    │  │ • search_api    │  │ • memory_handoff        │  │
│  │ • lock_file     │  │ • search_error  │  │                         │  │
│  │ • unlock_file   │  │ • find_library  │  └─────────────────────────┘  │
│  │ • get_artifacts │  └─────────────────┘                               │
│  │ • send_message  │                                                    │
│  │ • get_queue     │  ┌─────────────────────────────────────────────┐  │
│  │ • cancel_task   │  │ Validation & Safety                         │  │
│  │ • validate_deps │  │ • Cycle detection (DFS)                     │  │
│  └─────────────────┘  │ • Path sanitization                         │  │
│                       │ • Zod schema validation                     │  │
│                       └─────────────────────────────────────────────┘  │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 │ ioredis
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         REDIS (Central Message Bus)                      │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ Task Queue   │  │ Agent        │  │ File Locks   │  │ Memory      │  │
│  │              │  │ Registry     │  │              │  │ Cache       │  │
│  │ Sorted Set   │  │ Hash + TTL   │  │ String + TTL │  │ Hash        │  │
│  │ + Lua Claims │  │ Keys         │  │ + Lua Unlock │  │             │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │ Pub/Sub Channels                                                  │   │
│  │ • ralph:messages:{agent_id}  - Agent-specific messages           │   │
│  │ • ralph:broadcast            - All-agent broadcasts              │   │
│  │ • ralph:events               - System events                     │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ AGENT: Frontend │   │ AGENT: Backend  │   │ AGENT: QA       │
│                 │   │                 │   │                 │
│ • React/UI      │   │ • API/Database  │   │ • Testing       │
│ • CSS/Styling   │   │ • Docker        │   │ • Security      │
│ • Components    │   │ • Python        │   │ • Code Review   │
│                 │   │                 │   │                 │
│ ┌─────────────┐ │   │ ┌─────────────┐ │   │ ┌─────────────┐ │
│ │RalphClient  │ │   │ │RalphClient  │ │   │ │RalphClient  │ │
│ │             │ │   │ │             │ │   │ │             │ │
│ │• claim_task │ │   │ │• claim_task │ │   │ │• claim_task │ │
│ │• file_lock  │ │   │ │• file_lock  │ │   │ │• file_lock  │ │
│ │• remember   │ │   │ │• remember   │ │   │ │• remember   │ │
│ │• heartbeat  │ │   │ │• heartbeat  │ │   │ │• heartbeat  │ │
│ └─────────────┘ │   │ └─────────────┘ │   │ └─────────────┘ │
└─────────────────┘   └─────────────────┘   └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌─────────────────────┐
                    │ SHARED RESOURCES    │
                    │                     │
                    │ • File System       │
                    │ • Artifacts Volume  │
                    │ • Claude-Mem Store  │
                    └─────────────────────┘
```

---

## 3. Core Components

### 3.1 MCP Server (`mcp-server/src/index.ts`)

The MCP Server is the bridge between Claude Code and the Ralph Wiggum system.

**Technology:** TypeScript, ioredis, Zod

**Responsibilities:**
- Expose 18 MCP tools to Claude Code
- Validate all inputs via Zod schemas
- Detect circular dependencies before task creation
- Integrate with Librarian CLI for documentation search
- Handle Redis connection with retry strategy

**Key Code Patterns:**

```typescript
// Tool registration pattern
server.tool("ralph_send_task", schema, async (args) => {
  // 1. Validate input
  const validated = SendTaskSchema.parse(args);

  // 2. Check dependencies for cycles
  if (validated.dependencies?.length) {
    const cycles = detectCycles(validated.dependencies);
    if (cycles.length) return { error: "Circular dependency" };
  }

  // 3. Execute Redis operation
  const result = await redis.rpush("ralph:tasks:queue", JSON.stringify(task));

  // 4. Return structured response
  return { success: true, task_id: validated.id };
});
```

### 3.2 Python Client Library (`lib/ralph-client/`)

The Python client provides the agent-side API for task execution and coordination.

**Modules:**

| Module | Purpose | Key Classes |
|--------|---------|-------------|
| `client.py` | Main agent API | `RalphClient` |
| `tasks.py` | Task queue operations | `TaskQueue`, `Task` |
| `registry.py` | Agent discovery | `AgentRegistry` |
| `locks.py` | File coordination | `FileLock` |
| `telemetry.py` | Metrics collection | `RalphMetrics` |
| `tracing.py` | Distributed tracing | `TaskTracer` |

**RalphClient Lifecycle:**

```python
# 1. Initialize
client = RalphClient(
    agent_id="agent-frontend-001",
    agent_type="frontend",
    redis_url="redis://localhost:6379"
)

# 2. Start (registers agent, starts heartbeat)
client.start()

# 3. Claim and execute tasks
task = client.claim_task(task_data)
if task:
    # Work on task...
    client.complete_task(task_id, result, summary, learnings, next_steps)

# 4. Stop (deregisters, cleanup)
client.stop()
```

### 3.3 Task Queue (`lib/ralph-client/tasks.py`)

The task queue implements **atomic claiming** via Lua scripts to prevent race conditions.

**Task States:**

```
PENDING ──► CLAIMED ──► IN_PROGRESS ──► COMPLETED
    │           │                           │
    │           └──► BLOCKED                │
    │                   │                   │
    └───────────────────┴───────► FAILED ◄──┘
```

**Atomic Claim Script (Lua):**

```lua
-- CLAIM_SCRIPT: Atomically claim task if conditions met
local task_id = KEYS[1]
local agent_id = ARGV[1]
local claimed_key = "ralph:tasks:claimed:" .. task_id
local task_key = "ralph:tasks:data:" .. task_id

-- Check 1: Not already claimed
if redis.call("EXISTS", claimed_key) == 1 then
    return {0, "already_claimed"}
end

-- Check 2: All dependencies completed
local task_data = redis.call("GET", task_key)
local task = cjson.decode(task_data)
for _, dep_id in ipairs(task.dependencies or {}) do
    local dep_status = redis.call("HGET", "ralph:tasks:data:" .. dep_id, "status")
    if dep_status ~= "completed" then
        return {0, "dependency_not_met:" .. dep_id}
    end
end

-- Atomically claim
redis.call("SET", claimed_key, agent_id, "EX", 3600)  -- 1hr TTL
redis.call("HSET", task_key, "status", "claimed", "claimed_by", agent_id)
redis.call("ZREM", "ralph:tasks:queue", task_id)

return {1, "claimed"}
```

### 3.4 File Locking (`lib/ralph-client/locks.py`)

Pessimistic locking prevents simultaneous file edits.

**Lock Lifecycle:**

```
UNLOCKED ──► LOCKED (by Agent A) ──► UNLOCKED
                    │
                    └──► TTL EXPIRES ──► UNLOCKED (deadlock prevention)
```

**Key Features:**
- **TTL-based deadlock prevention:** Locks auto-expire (default 300s)
- **Owner verification:** Only lock holder can release (Lua script)
- **Path normalization:** Prevents traversal attacks
- **Wait-for-lock:** Blocking wait with timeout

**Unlock Script (Lua):**

```lua
-- UNLOCK_SCRIPT: Release only if caller is owner
local lock_key = KEYS[1]
local agent_id = ARGV[1]

local lock_data = redis.call("GET", lock_key)
if not lock_data then
    return {0, "not_locked"}
end

local lock = cjson.decode(lock_data)
if lock.agent_id ~= agent_id then
    return {0, "not_owner"}
end

redis.call("DEL", lock_key)
return {1, "released"}
```

### 3.5 Agent Registry (`lib/ralph-client/registry.py`)

Tracks active agents and their capabilities.

**Heartbeat System:**

```
Agent starts ──► Register ──► Heartbeat every 5s ──► Agent stops ──► Deregister
                    │                                      │
                    └──► Missed heartbeats ──► Cleanup removes agent
                              (15s TTL)
```

**Agent Discovery:**

```python
# Find agents by type
backend_agents = registry.get_agents_by_type("backend")

# Find agents with specific capability
security_agents = registry.get_agents_with_mode("security")

# Check if agent is alive
if registry.is_alive("agent-frontend-001"):
    # Send task to agent
```

---

## 4. Data Flow & Communication

### 4.1 Task Execution Flow

```
                    ┌─────────────────────────────────────┐
                    │ 1. TASK CREATION                    │
                    │                                     │
                    │ Orchestrator calls ralph_send_task  │
                    │ or ralph_broadcast_task             │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │ 2. QUEUE                            │
                    │                                     │
                    │ Task stored in Redis:               │
                    │ • ralph:tasks:queue (sorted set)    │
                    │ • ralph:tasks:data:{id} (full JSON) │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │ 3. CLAIM                            │
                    │                                     │
                    │ Agent calls claim_task()            │
                    │ Lua script checks:                  │
                    │ • Not already claimed               │
                    │ • All dependencies completed        │
                    │ • All wait_for completed            │
                    │                                     │
                    │ Atomically:                         │
                    │ • Sets claimed key with TTL         │
                    │ • Updates status to CLAIMED         │
                    │ • Removes from queue                │
                    └──────────────────┬──────────────────┘
                                       │
                                       ▼
                    ┌─────────────────────────────────────┐
                    │ 4. EXECUTE                          │
                    │                                     │
                    │ Agent works on task:                │
                    │ • Acquires file locks as needed     │
                    │ • Updates progress periodically     │
                    │ • Retrieves memories for context    │
                    │ • Stores learnings during work      │
                    └──────────────────┬──────────────────┘
                                       │
                          ┌────────────┴────────────┐
                          │                         │
                          ▼                         ▼
        ┌─────────────────────────┐   ┌─────────────────────────┐
        │ 5a. COMPLETE            │   │ 5b. FAIL                │
        │                         │   │                         │
        │ complete_task() calls:  │   │ fail_task() calls:      │
        │ • Stores result         │   │ • Stores error          │
        │ • Commits memory        │   │ • Logs blocker          │
        │ • Creates handoff       │   │ • Triggers escalation   │
        │ • Releases locks        │   │ • Releases locks        │
        │ • Updates status        │   │ • Notifies via Telegram │
        └─────────────────────────┘   └─────────────────────────┘
```

### 4.2 Inter-Agent Communication

**Direct Messaging:**

```python
# Agent A sends to Agent B
client_a.send_message(
    target_agent="agent-backend-001",
    msg_type="artifact_ready",
    payload={"artifact_id": "art-123", "file": "api/schema.py"}
)

# Agent B receives (via registered handler)
@client_b.on_message("artifact_ready")
def handle_artifact(payload):
    artifact = client_b.get_artifact(payload["artifact_id"])
    # Use artifact...
```

**Broadcast:**

```python
# Orchestrator broadcasts to all agents
client.broadcast(
    msg_type="pause_all",
    payload={"reason": "Security vulnerability detected"}
)
```

**Pub/Sub Channels:**

| Channel | Purpose | Publishers | Subscribers |
|---------|---------|------------|-------------|
| `ralph:messages:{agent_id}` | Direct messages | Any agent | Target agent |
| `ralph:broadcast` | All-agent broadcasts | Orchestrator | All agents |
| `ralph:events` | System events | System | Orchestrator |

### 4.3 Memory Handoff Flow

```
┌──────────────────────────────────────────────────────────────────────┐
│ AGENT A: Completes Task FE-001                                       │
│                                                                      │
│ complete_task(                                                       │
│     task_id="FE-001",                                               │
│     result={"files": ["src/Login.tsx"]},                            │
│     summary="Implemented login form with validation",                │
│     learnings=["Use React Hook Form for complex validation"],        │
│     next_steps=["Add password reset", "Write integration tests"]     │
│ )                                                                    │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ MEMORY SYSTEM                                                        │
│                                                                      │
│ Stores in Redis:                                                     │
│ • claude_mem:project:memories (learnings)                           │
│ • claude_mem:project:handoffs:FE-001 (handoff notes)                │
│ • claude_mem:project:task:FE-001:context (task context)             │
│                                                                      │
│ Stores in Claude-Mem (persistent):                                   │
│ • Learning: "Use React Hook Form for complex validation"             │
│ • Handoff: Summary + next steps for FE-002                          │
└─────────────────────────────────┬────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│ AGENT B: Starts Task FE-002 (depends on FE-001)                      │
│                                                                      │
│ context = ralph_memory_context(task_id="FE-002")                     │
│                                                                      │
│ Returns:                                                             │
│ {                                                                    │
│   "project_context": "React/TypeScript project, uses Hook Form...", │
│   "task_context": "FE-002 depends on FE-001...",                    │
│   "previous_handoffs": [{                                            │
│     "task_id": "FE-001",                                            │
│     "summary": "Implemented login form with validation",             │
│     "next_steps": ["Add password reset", "Write integration tests"] │
│   }],                                                                │
│   "relevant_memories": [                                             │
│     {"content": "Use React Hook Form for complex validation", ...}  │
│   ]                                                                  │
│ }                                                                    │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 5. Redis Schema Reference

### Task Management

```yaml
ralph:tasks:queue:
  type: Sorted Set
  score: priority (lower = higher priority)
  member: task_id
  purpose: Priority queue for pending tasks

ralph:tasks:data:{task_id}:
  type: String (JSON)
  content: Full task object
  fields:
    - id, title, description
    - task_type, agent (assigned agent type)
    - priority (1-10)
    - status (pending|claimed|in_progress|blocked|completed|failed)
    - dependencies (list of task IDs)
    - wait_for (list of task IDs)
    - acceptance_criteria (list of strings)
    - result (completion data)

ralph:tasks:claimed:{task_id}:
  type: String
  ttl: 3600 (1 hour)
  content: claiming agent_id
  purpose: Claim lock with auto-expiry

ralph:tasks:by_status:{status}:
  type: Sorted Set
  score: timestamp
  member: task_id
  purpose: O(log N) status lookups
```

### Agent Registry

```yaml
ralph:agents:
  type: Hash
  key: agent_id
  value: JSON object
  fields:
    - agent_id, agent_type
    - specialist_modes (list)
    - status (idle|busy|error)
    - registered_at, last_heartbeat
    - current_task (if any)
    - metadata

ralph:heartbeats:{agent_id}:
  type: String
  ttl: 15 seconds
  content: timestamp
  purpose: Liveness detection (key exists = alive)
```

### File Locks

```yaml
ralph:locks:file:{normalized_path}:
  type: String (JSON)
  ttl: Variable (default 300s)
  content:
    agent_id: lock holder
    acquired_at: timestamp
    ttl: lock duration
    file_path: original path
```

### Memory System

```yaml
claude_mem:{project_id}:memories:
  type: Hash
  key: memory_id
  value: JSON object
  fields:
    - id, content, category
    - scope (project|task|agent)
    - tags, task_id
    - created_at, metadata

claude_mem:{project_id}:task:{task_id}:memories:
  type: Set
  members: memory_ids
  purpose: Fast lookup of task-specific memories

claude_mem:{project_id}:handoffs:{task_id}:
  type: Hash
  fields:
    - summary, next_steps (JSON array)
    - task_id, created_at
    - agent_id (who created handoff)

claude_mem:{project_id}:project_context:
  type: Hash
  fields:
    - name, description
    - tech_stack (JSON array)
    - conventions, created_at
```

### Messaging

```yaml
ralph:messages:{agent_id}:
  type: Pub/Sub Channel
  purpose: Agent-specific messages

ralph:broadcast:
  type: Pub/Sub Channel
  purpose: All-agent broadcasts

ralph:events:
  type: Pub/Sub Channel
  purpose: System events (task completed, agent joined, etc.)

ralph:progress:{task_id}:
  type: List
  purpose: Progress updates for long-running tasks
```

---

## 6. Agent Types & Selection

### 6.1 The 7 Specialist Agent Types

| Agent Type | Model | Primary Focus | Trigger Keywords |
|------------|-------|---------------|------------------|
| **security-auditor** | Minimax | OWASP, vulnerability detection | security, audit, vulnerability, owasp, penetration |
| **debugger** | GLM | Root cause analysis, fix verification | debug, error, fix, bug, failing |
| **test-architect** | GLM | Test strategy, coverage optimization | test, qa, coverage |
| **refactorer** | GLM | Code structure, tech debt elimination | refactor, cleanup, smell, debt |
| **docs-writer** | Minimax | README, API docs, guides | docs, document, readme, documentation, guide |
| **code-reviewer** | Minimax | Five-dimension code analysis | review, pr, pull request |
| **backend** | Opus | API, database, infrastructure | api, backend, database, docker, python, fastapi |
| **frontend** | Opus | React, UI, styling | ui, frontend, component, react, form, css |
| **general-purpose** | Opus | Architecture, planning (default) | (fallback) |

### 6.2 Selection Algorithm

The agent type is selected based on task title keywords, checked in priority order:

```python
def select_agent_type(task_title: str) -> str:
    """Select agent type based on task title keywords."""
    title_lower = task_title.lower()

    # Priority order: most specific first
    if matches(title_lower, r"security|audit|vulnerabilit|owasp|penetration"):
        return "security-auditor"
    if matches(title_lower, r"\bdebug|\berror\b|\bfix\b|\bbug\b|failing"):
        return "debugger"
    if matches(title_lower, r"\btest|\bqa\b|coverage"):
        return "test-architect"
    if matches(title_lower, r"refactor|cleanup|smell|debt|reorganize"):
        return "refactorer"
    if matches(title_lower, r"\bdocs?\b|readme|documentation|\bdocument\b|\bguide\b"):
        return "docs-writer"
    if matches(title_lower, r"review|\bpr\b|pull.?request|code.?review"):
        return "code-reviewer"
    if matches(title_lower, r"\bapi\b|backend|database|docker|python|fastapi|server|endpoint"):
        return "backend"
    if matches(title_lower, r"\bui\b|frontend|component|react|\bform\b|\bcss\b|plasmo|style"):
        return "frontend"

    return "general-purpose"  # Default fallback
```

### 6.3 Model Selection Rationale

| Model | Strengths | Used For |
|-------|-----------|----------|
| **Opus** | Deep reasoning, architecture, complex implementation | backend, frontend, general-purpose |
| **GLM** | Systematic analysis, debugging, testing | debugger, test-architect, refactorer |
| **Minimax** | Fast review, pattern matching, documentation | code-reviewer, security-auditor, docs-writer |

---

## 7. Complete Workflow Example

### Scenario: "Build User Authentication Feature"

**Input:** PRD describing authentication requirements

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 1: TASK GENERATION                                                │
│                                                                         │
│ User: "Build user authentication with login, registration, and JWT"     │
│                                                                         │
│ 1. Taskmaster parses PRD:                                               │
│    npx task-master parse-prd --input prd.txt --num-tasks 10             │
│                                                                         │
│ 2. Generate Ralph format:                                               │
│    ./scripts/generate-prd.sh . --from-taskmaster                        │
│                                                                         │
│ Output: plans/prd.json with 9 tasks                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 2: DEPENDENCY ANALYSIS & WAVE PLANNING                            │
│                                                                         │
│ Tasks generated:                                                        │
│ ┌────────────────────────────────────────────────────────────────────┐ │
│ │ TASK-001: Set up auth database schema      [deps: none]   → backend│ │
│ │ TASK-002: Implement JWT service            [deps: 001]    → backend│ │
│ │ TASK-003: Create login API endpoints       [deps: 001,002]→ backend│ │
│ │ TASK-004: Build React login form           [deps: 003]    → frontend│
│ │ TASK-005: Implement protected route        [deps: 003]    → frontend│
│ │ TASK-006: Create auth context              [deps: 004,005]→ frontend│
│ │ TASK-007: Write unit tests for auth        [deps: 003]    → test   │ │
│ │ TASK-008: Security audit for auth          [deps: 003,006]→ security│
│ │ TASK-009: Update API documentation         [deps: 003]    → docs   │ │
│ └────────────────────────────────────────────────────────────────────┘ │
│                                                                         │
│ Wave calculation (respecting dependencies):                             │
│                                                                         │
│ Wave 1: [TASK-001]           ← No dependencies                          │
│ Wave 2: [TASK-002]           ← Depends on 001                           │
│ Wave 3: [TASK-003]           ← Depends on 001, 002                      │
│ Wave 4: [TASK-004, TASK-005, TASK-007, TASK-009] ← All depend on 003   │
│ Wave 5: [TASK-006]           ← Depends on 004, 005                      │
│ Wave 6: [TASK-008]           ← Depends on 003, 006                      │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 3: EXECUTION (Wave by Wave)                                       │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 1: Architecture                                                    │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   Orchestrator spawns:                                                  │
│   Task(subagent_type="backend", prompt="TASK-001: Set up auth schema") │
│                                                                         │
│   Backend Agent:                                                        │
│   1. claim_task(TASK-001)                                              │
│   2. acquire_file_lock("prisma/schema.prisma")                         │
│   3. Creates User, Session models                                       │
│   4. remember("Using Prisma ORM for auth", category="architecture")    │
│   5. complete_task(TASK-001, result={files: [...]})                    │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 2: JWT Service                                                     │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   Backend Agent:                                                        │
│   1. ralph_memory_context(task_id="TASK-002") → Gets TASK-001 context  │
│   2. claim_task(TASK-002) ✓ (TASK-001 completed)                       │
│   3. Implements JWT signing/verification                                │
│   4. complete_task(TASK-002, learnings=["Using RS256 for JWT"])        │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 3: API Endpoints                                                   │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   Backend Agent:                                                        │
│   1. claim_task(TASK-003) ✓ (TASK-001, TASK-002 completed)             │
│   2. Creates /login, /register, /logout endpoints                       │
│   3. complete_task(TASK-003, next_steps=["Add rate limiting"])         │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 4: PARALLEL EXECUTION (4 agents simultaneously)                    │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐          │
│   │ Frontend Agent  │ │ Frontend Agent  │ │ Test Agent      │          │
│   │ TASK-004        │ │ TASK-005        │ │ TASK-007        │          │
│   │ Login Form      │ │ Protected Route │ │ Unit Tests      │          │
│   └────────┬────────┘ └────────┬────────┘ └────────┬────────┘          │
│            │                   │                   │                    │
│   ┌─────────────────┐          │                   │                    │
│   │ Docs Agent      │          │                   │                    │
│   │ TASK-009        │          │                   │                    │
│   │ API Docs        │          │                   │                    │
│   └────────┬────────┘          │                   │                    │
│            │                   │                   │                    │
│            └───────────────────┴───────────────────┘                    │
│                         All run in parallel!                            │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 5: Auth Context                                                    │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   Frontend Agent:                                                       │
│   1. claim_task(TASK-006) ✓ (TASK-004, TASK-005 completed)             │
│   2. Creates AuthProvider with useAuth hook                             │
│   3. complete_task(TASK-006)                                           │
│                                                                         │
│ ═══════════════════════════════════════════════════════════════════════│
│ WAVE 6: Security Audit                                                  │
│ ═══════════════════════════════════════════════════════════════════════│
│                                                                         │
│   Security Agent:                                                       │
│   1. ralph_memory_context() → Gets all previous context                │
│   2. claim_task(TASK-008)                                              │
│   3. OWASP checklist: XSS, CSRF, SQL injection, etc.                   │
│   4. Checks JWT implementation                                          │
│   5. complete_task(TASK-008, result={vulnerabilities: 0})              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 4: QA CYCLE                                                       │
│                                                                         │
│   Test Architect automatically spawned after all impl tasks:            │
│                                                                         │
│   1. Runs full test suite                                               │
│   2. If tests pass → Feature complete                                  │
│   3. If tests fail:                                                     │
│      a. Spawns Debugger agent                                           │
│      b. Debugger fixes issue                                            │
│      c. Re-spawns Test Architect (re-test)                             │
│      d. Loop until pass or escalate (max 3 attempts)                   │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────┐          │
│   │ QA → Fix → Re-QA Cycle                                  │          │
│   │                                                         │          │
│   │  Tests ──► Pass ──► Complete                           │          │
│   │    │                                                    │          │
│   │    ▼                                                    │          │
│   │  Fail                                                   │          │
│   │    │                                                    │          │
│   │    ▼                                                    │          │
│   │  Spawn Debugger ──► Fix ──► Re-test                    │          │
│   │    │                           │                        │          │
│   │    │                           ▼                        │          │
│   │    │                     3 failures?                    │          │
│   │    │                           │                        │          │
│   │    │            Yes ◄──────────┘                        │          │
│   │    │             │                                      │          │
│   │    ▼             ▼                                      │          │
│   │  Escalate via Telegram                                  │          │
│   └─────────────────────────────────────────────────────────┘          │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 5: COMPLETION & HANDOFF                                           │
│                                                                         │
│   Final handoff stored:                                                 │
│   {                                                                     │
│     "project": "auth-feature",                                          │
│     "tasks_completed": 9,                                               │
│     "agents_used": ["backend", "frontend", "test-architect",           │
│                     "security-auditor", "docs-writer"],                 │
│     "summary": "Authentication feature implemented and tested",         │
│     "next_steps": ["Deploy to staging", "User acceptance testing"],    │
│     "learnings": [                                                      │
│       "Using Prisma ORM for auth",                                      │
│       "Using RS256 for JWT",                                            │
│       "React Hook Form for validation"                                  │
│     ]                                                                   │
│   }                                                                     │
│                                                                         │
│   Memory persisted for future sessions.                                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Memory System Deep Dive

### 8.1 Memory Categories

| Category | Purpose | Examples |
|----------|---------|----------|
| **architecture** | Design decisions, patterns | "Using Prisma for ORM", "Microservices with API Gateway" |
| **pattern** | Reusable code patterns | "AAA pattern for tests", "Repository pattern for data access" |
| **decision** | Key choices made | "Chose JWT over sessions for statelessness" |
| **blocker** | Problems and solutions | "Redis connection timeout - fixed with retry strategy" |
| **learning** | Insights from completed work | "React Hook Form better than Formik for complex validation" |
| **handoff** | Notes for next agent | Summary, next steps, context |

### 8.2 Memory Scopes

```
PROJECT SCOPE (all agents can access)
├── Architecture decisions
├── Tech stack choices
└── Project conventions

TASK SCOPE (specific to task)
├── Task-specific learnings
├── Files modified
└── Handoff notes

AGENT SCOPE (private to agent)
├── Agent preferences
└── Work patterns
```

### 8.3 Memory Recall Algorithm

```python
def recall(query: str, category: str = None, task_id: str = None, limit: int = 10):
    """
    Hybrid recall combining:
    1. Exact match on category/task_id
    2. Semantic similarity on content
    3. Recency weighting
    """
    memories = []

    # Filter by category/task_id if specified
    candidates = get_candidates(category, task_id)

    # Score by relevance
    for memory in candidates:
        score = 0
        score += semantic_similarity(query, memory.content) * 0.6
        score += recency_score(memory.created_at) * 0.2
        score += category_match_score(query, memory.category) * 0.2
        memories.append((memory, score))

    # Return top results
    return sorted(memories, key=lambda x: x[1], reverse=True)[:limit]
```

---

## 9. Orchestration Protocol

### 9.1 Orchestrator Responsibilities

The Orchestrator (Claude Code with orchestration skill loaded) is responsible for:

1. **Parse PRD** → Generate `plans/prd.json` via Taskmaster
2. **Load Context** → Call `ralph_memory_context` for project history
3. **Plan Waves** → Calculate execution order from dependencies
4. **Spawn Agents** → Use Task tool with correct `subagent_type`
5. **Monitor Progress** → Check `ralph_get_status` periodically
6. **Handle Failures** → Trigger fix agents, escalate if needed
7. **Spawn QA** → Automatically after implementation complete
8. **Aggregate Results** → Create final handoff

### 9.2 What Orchestrators NEVER Do

- Implement code directly (delegate to specialists)
- Work sequentially on multi-task projects
- Skip memory context loading
- Forget to spawn QA after implementation
- Ignore escalation rules

### 9.3 Spawn Pattern

```python
# Correct: Spawn specialist agent
Task(
    subagent_type="frontend",
    prompt="""
    Task: FE-001 - Build login form

    Context from memory:
    - Using React Hook Form for validation
    - Tailwind CSS for styling

    Previous handoff:
    - API endpoints ready at /api/auth/*

    Acceptance criteria:
    - Form validates email and password
    - Shows loading state during submission
    - Displays error messages from API
    """
)

# Wrong: Doing the work yourself
# Never implement directly unless single trivial task
```

---

## 10. Security & Coordination

### 10.1 Input Validation

| Layer | Validation | Purpose |
|-------|------------|---------|
| MCP Server | Zod schemas | Type safety, required fields |
| File Paths | Normalization + traversal check | Prevent `../` attacks |
| Task Dependencies | Cycle detection (DFS) | Prevent infinite loops |
| Librarian Args | Shell metacharacter removal | Prevent injection |

### 10.2 Coordination Safety

| Mechanism | Implementation | Purpose |
|-----------|----------------|---------|
| Atomic Claims | Lua scripts | Prevent race conditions |
| File Locks | SET NX + TTL | Prevent edit conflicts |
| Owner Verification | Lua unlock script | Prevent unauthorized releases |
| Heartbeat TTL | 15 second expiry | Detect dead agents |
| Claim TTL | 1 hour expiry | Prevent stuck tasks |

### 10.3 Escalation Rules

```python
ESCALATION_TRIGGERS = [
    "same_test_fails_3_times",
    "fix_introduces_new_failures",
    "security_vulnerability_found",
    "agent_unresponsive_30_seconds",
    "circular_dependency_detected"
]

def escalate(reason: str, context: dict):
    # 1. Log blocker in memory
    memory.remember(
        content=f"Escalation: {reason}",
        category="blocker",
        metadata=context
    )

    # 2. Send Telegram notification
    notify_telegram(
        message=f"🚨 Escalation: {reason}\n\nContext: {context}",
        level="critical"
    )

    # 3. Pause related tasks
    pause_dependent_tasks(context.get("task_id"))
```

---

## 11. Extension Points

### 11.1 Adding New Agent Types

1. **Create template** in `templates/specialists/{agent-type}.md`
2. **Add keywords** to `scripts/generate-prd.sh` (both type and agent sections)
3. **Update tests** in `tests/orchestration/test_agent_selection.py`
4. **Document** in orchestration skill

### 11.2 Adding New MCP Tools

1. **Define schema** in `mcp-server/src/index.ts`
2. **Implement handler** with Redis operations
3. **Add validation** via Zod
4. **Write tests** for tool behavior
5. **Document** in MCP tools reference

### 11.3 Custom Memory Categories

1. **Add category** to `ProjectMemory.CATEGORIES`
2. **Create helper method** like `note_architecture()`
3. **Update recall** to handle new category
4. **Document** usage patterns

### 11.4 Integration Points

| Integration | How | Purpose |
|-------------|-----|---------|
| **CI/CD** | Webhook on task completion | Trigger deployments |
| **Slack/Discord** | Replace Telegram handler | Team notifications |
| **Custom Docs** | Add to Librarian sources | Project-specific docs |
| **Monitoring** | Expose metrics endpoint | Grafana dashboards |

---

## Appendix A: File Reference

| Path | Purpose |
|------|---------|
| `mcp-server/src/index.ts` | MCP server with 18 tools |
| `lib/ralph-client/client.py` | Main Python client |
| `lib/ralph-client/tasks.py` | Task queue with Lua scripts |
| `lib/ralph-client/locks.py` | File locking system |
| `lib/ralph-client/registry.py` | Agent discovery |
| `lib/memory/project_memory.py` | Memory system |
| `.claude/skills/orchestration/SKILL.md` | Orchestration protocol |
| `.claude/skills/taskmaster/SKILL.md` | Taskmaster integration |
| `scripts/generate-prd.sh` | PRD generation with agent detection |
| `docker-compose.yml` | Infrastructure definition |
| `templates/agent-CLAUDE.md` | Base agent instructions |
| `templates/specialists/*.md` | Specialist templates |

---

## Appendix B: Quick Reference

### Start an Agent

```python
from ralph_client import RalphClient

client = RalphClient("agent-001", "frontend", "redis://localhost:6379")
client.start()
```

### Claim and Complete a Task

```python
task = client.claim_task(task_data)
if task:
    # Do work...
    client.complete_task(
        task_id=task["id"],
        result={"files": ["src/component.tsx"]},
        summary="Implemented component",
        learnings=["Used memo for performance"],
        next_steps=["Add tests"]
    )
```

### Store and Recall Memory

```python
# Store
client.remember(
    content="Using React Query for data fetching",
    category="pattern",
    tags=["react", "data"]
)

# Recall
memories = client.recall(query="data fetching", category="pattern")
```

### Acquire File Lock

```python
if client.acquire_file_lock("src/api.ts", timeout=300):
    try:
        # Edit file...
    finally:
        client.release_file_lock("src/api.ts")
```

---

*Ralph Wiggum v1.0.0 - Multi-Agent Orchestration Platform*
