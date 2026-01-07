# Ralph Wiggum - Starting a New Project

> How to tell Claude Code you want to use the multi-agent orchestration platform

---

## Quick Start (Copy-Paste Ready)

When starting a new Claude Code session, say:

```
I want to create a new project using Ralph Wiggum multi-agent orchestration.
The platform is at: C:\Users\david.hayes\Projects\ralph-wiggum-test

Project: <YOUR PROJECT NAME>
Description: <WHAT YOU WANT TO BUILD>
Agents needed: <frontend, backend, integration, or custom>

Please:
1. Read the Ralph Wiggum README at the platform path
2. Set up agent workspaces using setup-agent-workspace.sh
3. Help me create a PRD using Taskmaster or generate tasks
4. Configure the agents and start the orchestration
```

---

## Detailed Steps

### Step 1: Reference the Platform

Tell Claude Code where Ralph Wiggum is installed:

```
The Ralph Wiggum multi-agent platform is at:
C:\Users\david.hayes\Projects\ralph-wiggum-test

Read the README.md to understand the system.
```

### Step 2: Describe Your Project

Be specific about what you're building:

```
I want to build a <type> application with:
- <Feature 1>
- <Feature 2>
- <Technology preferences>

This will need:
- Backend agent for API/database
- Frontend agent for UI
```

### Step 3: Generate Tasks

**Option A: Use Taskmaster (Recommended)**

```
Let's use Taskmaster to generate tasks:
1. I'll describe the project requirements
2. Generate a PRD document
3. Run: npx task-master parse-prd --input prd.md
4. Convert to Ralph format: ./scripts/generate-prd.sh . --from-taskmaster
```

**Option B: Direct Task Creation**

```
Help me create a Ralph Wiggum PRD (plans/prd.json) with tasks for:
- Project setup
- Core features
- Testing
- Integration

Follow the Ralph PRD format with:
- id, category, priority, description
- acceptance_criteria array
- dependencies array
- model_hint (planning/implementation/verification)
```

### Step 4: Setup Workspaces

```
Run the setup script for each agent:
./scripts/setup-agent-workspace.sh ./projects/backend agent-backend backend "implement,test"
./scripts/setup-agent-workspace.sh ./projects/frontend agent-frontend frontend "implement,test"
```

### Step 5: Start Orchestration

```
Start the infrastructure:
docker-compose up -d redis

Then I'll start each agent in separate terminals.
```

---

## Example: Full Bootstrap Message

```
I want to create a new project using Ralph Wiggum multi-agent orchestration.
Platform location: C:\Users\david.hayes\Projects\ralph-wiggum-test

Project: Task Management API with React Dashboard
Description: A RESTful API for task management with a React dashboard for visualization

Agents needed:
- agent-backend: Express/TypeScript API with PostgreSQL
- agent-frontend: React/TypeScript dashboard with charts

Requirements:
- User authentication (JWT)
- CRUD operations for tasks
- Task assignment and status tracking
- Dashboard with task statistics
- Real-time updates via WebSocket

Please:
1. Read the Ralph Wiggum platform README
2. Help me create a detailed PRD using Taskmaster
3. Set up the agent workspaces
4. Configure the MCP server for Claude Code control
5. Guide me through starting the multi-agent orchestration
```

---

## Adding Ralph Wiggum to Your CLAUDE.md

Add this to your `~/.claude/CLAUDE.md` for persistent awareness:

```markdown
## Ralph Wiggum Multi-Agent Platform

Location: C:\Users\david.hayes\Projects\ralph-wiggum-test

When I say "use Ralph Wiggum" or "multi-agent project":
1. Read the platform README.md
2. Use setup-agent-workspace.sh for new agent workspaces
3. Generate PRD using Taskmaster integration
4. Follow the orchestration patterns in docs/

Key commands:
- Setup: ./scripts/setup-agent-workspace.sh <path> <agent-id> <type> <modes>
- PRD: ./scripts/generate-prd.sh <project> --from-taskmaster
- Test: ./tests/integration/run-multi-agent-test.sh
```

---

## Skill Integration (Optional)

If you have a skills system, add this skill:

**Location:** `~/.claude/skills/ralph-wiggum/SKILL.md`

```markdown
# Ralph Wiggum Skill

Trigger: User mentions "Ralph Wiggum", "multi-agent", or "agent orchestration"

Actions:
1. Load platform context from C:\Users\david.hayes\Projects\ralph-wiggum-test
2. Offer to create new project or manage existing
3. Guide through PRD generation and workspace setup
4. Configure MCP integration for Claude Code control
```

---

## MCP Configuration for Claude Code

Ensure your `~/.mcp.json` includes:

```json
{
  "mcpServers": {
    "ralph": {
      "command": "node",
      "args": ["C:/Users/david.hayes/Projects/ralph-wiggum-test/mcp-server/dist/index.js"],
      "env": {
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

This gives Claude Code access to:
- `ralph_list_agents` - See active agents
- `ralph_send_task` - Assign work to agents
- `ralph_get_status` - Monitor progress
- `ralph_lock_file` / `ralph_unlock_file` - Coordinate file access
- `ralph_get_queue` - View pending tasks

---

## Troubleshooting

### "Claude Code doesn't know about Ralph Wiggum"

Explicitly tell it:
```
Read C:\Users\david.hayes\Projects\ralph-wiggum-test\README.md
This is the Ralph Wiggum multi-agent orchestration platform.
```

### "MCP tools not available"

Check your `~/.mcp.json` configuration and restart Claude Code.

### "Agents not coordinating"

Verify Redis is running:
```bash
docker-compose -f <ralph-path>/docker-compose.yml ps redis
```

---

*Think Different. Build Together.*
