# Ralph Wiggum Multi-Agent Integration Test Plan

## Overview

This test validates the complete multi-agent orchestration system including:
- Redis coordination
- Agent registration and heartbeat
- Task queue and dependencies
- File locking
- Memory integration
- Model routing
- Hooks system

---

## Test Scenario: Todo App with Frontend + Backend Agents

Two agents collaborate to build a simple Todo application:
- **agent-backend**: Builds the API (TypeScript/Express)
- **agent-frontend**: Builds the UI (TypeScript/React)

### Why This Test?

1. **Task Dependencies** — Frontend depends on backend API
2. **File Coordination** — Shared types file requires locking
3. **Handoff** — Backend must handoff API spec to frontend
4. **Memory** — Patterns and decisions are shared
5. **Model Routing** — Planning vs implementation phases

---

## Phase 1: Infrastructure Validation

### 1.1 Redis Health Check

```bash
# Start Redis
docker-compose up -d redis

# Verify
docker-compose exec redis redis-cli ping
# Expected: PONG

# Check no stale data
docker-compose exec redis redis-cli KEYS "ralph:*"
# Expected: (empty list)
```

### 1.2 MCP Server Build

```bash
cd mcp-server
npm install
npm run build

# Verify build
ls -la dist/index.js
# Expected: File exists
```

---

## Phase 2: Single Agent Test

Before multi-agent, verify one agent works.

### 2.1 Setup Test Workspace

```bash
./scripts/setup-agent-workspace.sh ./tests/integration/single-agent test-agent general "implement,test"
```

### 2.2 Create Simple PRD

```json
[
  {
    "id": "task-001",
    "category": "setup",
    "priority": 1,
    "description": "Create a function that adds two numbers",
    "acceptance_criteria": [
      "src/math.ts exports add(a, b) function",
      "Function returns sum of two numbers",
      "Basic test exists and passes"
    ],
    "dependencies": [],
    "passes": false
  }
]
```

### 2.3 Run Single Iteration

```bash
cd tests/integration/single-agent
RALPH_AGENT_ID=test-agent ../../../plans/ralph-multi.sh --once
```

### 2.4 Verify

- [ ] Task marked as `passes: true`
- [ ] `src/math.ts` exists with `add` function
- [ ] Test passes
- [ ] Git commit created

---

## Phase 3: Multi-Agent Coordination Test

### 3.1 Setup Two Agent Workspaces

```bash
# Backend agent
./scripts/setup-agent-workspace.sh ./tests/integration/todo-backend agent-backend backend "implement,test"

# Frontend agent
./scripts/setup-agent-workspace.sh ./tests/integration/todo-frontend agent-frontend frontend "implement,test"
```

### 3.2 Backend PRD (`todo-backend/plans/prd.json`)

```json
[
  {
    "id": "be-001",
    "category": "setup",
    "priority": 1,
    "description": "Initialize Express TypeScript project",
    "acceptance_criteria": [
      "package.json with express, typescript",
      "tsconfig.json configured",
      "Basic server starts on port 3001"
    ],
    "dependencies": [],
    "passes": false
  },
  {
    "id": "be-002",
    "category": "feature",
    "priority": 2,
    "description": "Create Todo CRUD API endpoints",
    "acceptance_criteria": [
      "GET /todos returns array of todos",
      "POST /todos creates new todo",
      "PUT /todos/:id updates todo",
      "DELETE /todos/:id removes todo",
      "All endpoints return JSON"
    ],
    "dependencies": ["be-001"],
    "passes": false
  },
  {
    "id": "be-003",
    "category": "types",
    "priority": 3,
    "description": "Create shared Todo type definition",
    "acceptance_criteria": [
      "shared/types.ts exports Todo interface",
      "Interface has id, title, completed, createdAt",
      "File is in shared directory for frontend access"
    ],
    "dependencies": ["be-002"],
    "passes": false
  }
]
```

### 3.3 Frontend PRD (`todo-frontend/plans/prd.json`)

```json
[
  {
    "id": "fe-001",
    "category": "setup",
    "priority": 1,
    "description": "Initialize React TypeScript project",
    "acceptance_criteria": [
      "package.json with react, typescript",
      "Basic App component renders",
      "Development server starts"
    ],
    "dependencies": [],
    "passes": false
  },
  {
    "id": "fe-002",
    "category": "feature",
    "priority": 2,
    "description": "Create TodoList component",
    "acceptance_criteria": [
      "Component fetches todos from API",
      "Displays list of todos",
      "Each todo shows title and status",
      "Uses shared Todo type from backend"
    ],
    "dependencies": ["fe-001"],
    "wait_for": ["be-003"],
    "artifacts_from": ["be-003"],
    "passes": false
  },
  {
    "id": "fe-003",
    "category": "feature",
    "priority": 3,
    "description": "Add todo creation form",
    "acceptance_criteria": [
      "Form with title input",
      "Submit creates new todo via API",
      "List refreshes after creation"
    ],
    "dependencies": ["fe-002"],
    "passes": false
  }
]
```

### 3.4 Start Agents

```bash
# Terminal 1: Backend agent
cd tests/integration/todo-backend
RALPH_AGENT_ID=agent-backend \
RALPH_AGENT_TYPE=backend \
REDIS_URL=redis://localhost:6379 \
../../../plans/ralph-multi.sh 10

# Terminal 2: Frontend agent
cd tests/integration/todo-frontend
RALPH_AGENT_ID=agent-frontend \
RALPH_AGENT_TYPE=frontend \
REDIS_URL=redis://localhost:6379 \
../../../plans/ralph-multi.sh 10
```

### 3.5 Verify Coordination

```bash
# Check both agents registered
redis-cli HGETALL ralph:agents

# Check task queue
redis-cli ZRANGE ralph:tasks:queue 0 -1

# Watch events
redis-cli SUBSCRIBE ralph:events
```

---

## Phase 4: Validation Checklist

### Agent Registration
- [ ] Both agents appear in `ralph:agents`
- [ ] Heartbeats are being sent
- [ ] Status updates reflect current work

### Task Dependencies
- [ ] Frontend `fe-002` waits for backend `be-003`
- [ ] Tasks execute in correct order
- [ ] Dependencies are checked before claiming

### File Locking
- [ ] Shared types file is locked during backend edit
- [ ] Frontend waits if trying to read locked file
- [ ] Lock is released after edit

### Memory Integration
- [ ] Backend stores architecture decisions
- [ ] Frontend retrieves project context
- [ ] Handoff notes are created

### Model Routing
- [ ] Planning phases log `[MODEL: opus]`
- [ ] Implementation phases log `[MODEL: glm]`
- [ ] Testing phases log `[MODEL: minimax]`

### Hooks
- [ ] Security scan runs on commit
- [ ] Auto-format runs after edits
- [ ] Tests run on task completion

### Final Output
- [ ] Backend API runs and returns todos
- [ ] Frontend displays todos from API
- [ ] All PRD tasks marked `passes: true`

---

## Phase 5: Cleanup

```bash
# Stop Redis
docker-compose down

# Clean up test workspaces
rm -rf tests/integration/single-agent
rm -rf tests/integration/todo-backend
rm -rf tests/integration/todo-frontend
```

---

## Automated Test Script

See `tests/integration/run-integration-test.sh` for automated execution.

---

## Success Criteria

| Test | Pass Condition |
|------|----------------|
| Infrastructure | Redis responds, MCP builds |
| Single Agent | Completes simple task |
| Multi-Agent Registration | Both agents in registry |
| Task Dependencies | Correct execution order |
| File Locking | No conflicts on shared files |
| Memory | Context persists across agents |
| Final Integration | Todo app works end-to-end |

---

## Troubleshooting

### Agent stuck on task
```bash
# Check agent status
redis-cli HGET ralph:agents agent-backend

# Check for blocked tasks
redis-cli KEYS "ralph:tasks:claimed:*"

# Force release
redis-cli DEL "ralph:tasks:claimed:task-id"
```

### Memory not persisting
```bash
# Check Claude-Mem is running
curl http://localhost:37777/health

# Check memory entries
redis-cli HGETALL "ralph:memory:test-project"
```

### Model not switching
```bash
# Check router config
cat .claude-code-router/config.json

# Look for model signals in logs
grep "\[MODEL:" plans/ralph.log
```
