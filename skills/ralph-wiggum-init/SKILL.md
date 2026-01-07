# Ralph Wiggum Initialization Skill

## Trigger Conditions

Activate when user mentions:
- "ralph wiggum"
- "multi-agent project"
- "agent orchestration"
- "spin up agents"
- "new ralph project"

## Platform Location

```
C:\Users\david.hayes\Projects\ralph-wiggum-test
```

## Initialization Workflow

### 1. Gather Project Information

Ask user for:
- **Project Name**: What to call the project
- **Description**: What the project does
- **Agent Types Needed**:
  - `backend` - API, database, server logic
  - `frontend` - UI, React/Vue, client code
  - `integration` - Testing, CI/CD, deployment
  - `general` - Mixed responsibilities

### 2. Create Project Structure

```bash
# Set project root
PROJECT_ROOT="<user-specified-path>"
RALPH_ROOT="C:/Users/david.hayes/Projects/ralph-wiggum-test"

# Create base structure
mkdir -p "$PROJECT_ROOT/plans"
mkdir -p "$PROJECT_ROOT/shared"

# Copy orchestration scripts
cp "$RALPH_ROOT/plans/ralph-multi.sh" "$PROJECT_ROOT/plans/"
cp -r "$RALPH_ROOT/lib" "$PROJECT_ROOT/"
```

### 3. Setup Agent Workspaces

For each agent type requested:

```bash
"$RALPH_ROOT/scripts/setup-agent-workspace.sh" \
    "$PROJECT_ROOT/agents/<agent-id>" \
    <agent-id> \
    <agent-type> \
    "<modes>"
```

Example for typical fullstack project:
```bash
# Backend agent
./scripts/setup-agent-workspace.sh ./agents/backend agent-backend backend "implement,test,security"

# Frontend agent
./scripts/setup-agent-workspace.sh ./agents/frontend agent-frontend frontend "implement,test,ui"
```

### 4. Generate PRD

**Option A: Taskmaster Integration**
```bash
# If user has requirements doc
npx task-master parse-prd --input requirements.md
"$RALPH_ROOT/scripts/generate-prd.sh" "$PROJECT_ROOT" --from-taskmaster
```

**Option B: Interactive Generation**
Help user define tasks in Ralph PRD format:
```json
[
  {
    "id": "task-001",
    "category": "setup|feature|test|docs",
    "priority": 1,
    "description": "What needs to be done",
    "acceptance_criteria": ["Specific", "Measurable", "Criteria"],
    "dependencies": [],
    "passes": false,
    "model_hint": "planning|implementation|verification"
  }
]
```

### 5. Configure Environment

Create `.env` in project root:
```bash
REDIS_URL=redis://localhost:6379
OPENROUTER_API_KEY=<from-user-env>
USE_OPENROUTER=true
ANTHROPIC_MODEL=z-ai/glm-4.7
```

### 6. Start Infrastructure

```bash
cd "$RALPH_ROOT"
docker-compose up -d redis

# Verify
docker-compose exec redis redis-cli ping
```

### 7. Provide Launch Instructions

Output to user:
```
Ralph Wiggum project initialized!

To start agents:

Terminal 1 (Backend):
  cd $PROJECT_ROOT/agents/backend
  RALPH_AGENT_ID=agent-backend ./plans/ralph-multi.sh 10

Terminal 2 (Frontend):
  cd $PROJECT_ROOT/agents/frontend
  RALPH_AGENT_ID=agent-frontend ./plans/ralph-multi.sh 10

Monitor:
  redis-cli SUBSCRIBE ralph:events
  redis-cli HGETALL ralph:agents
```

## Model Routing Reference

| Task Type | Model | Use When |
|-----------|-------|----------|
| Planning | `claude-opus-4.5` | Architecture, design decisions |
| Implementation | `z-ai/glm-4.7` | Writing code, features |
| Verification | `minimax-m2.1` | Tests, docs, quick checks |

## Memory Protocol

Remind agents to:
- `memory.recall()` at task start
- `memory.note_*()` during work
- `memory.handoff()` at task end

## File Coordination

For shared files:
- Agent must `ralph_lock_file` before editing
- Release with `ralph_unlock_file` after
- Locks expire after 5 minutes

## Success Indicators

Project is ready when:
- [ ] Redis responds to ping
- [ ] Agent workspaces created
- [ ] PRD file exists with tasks
- [ ] Environment configured
- [ ] Launch commands provided
