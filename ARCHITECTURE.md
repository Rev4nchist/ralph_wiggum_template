# Ralph Wiggum Multi-Agent Architecture

## Overview

Ralph Wiggum is a multi-agent autonomous coding platform that enables multiple AI agents to work collaboratively on software projects, coordinated by Claude Code sessions.

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE SESSION                          │
│  (Human-in-the-loop control plane via MCP tools)                │
└─────────────────────────┬───────────────────────────────────────┘
                          │ MCP Protocol
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RALPH MCP SERVER                              │
│  ralph_list_agents | ralph_send_task | ralph_lock_file | ...    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                      REDIS MESSAGE BUS                           │
│  Agents │ Tasks │ Locks │ Artifacts │ Events │ Messages         │
└────┬────────────┬────────────┬────────────┬────────────┬────────┘
     │            │            │            │            │
     ▼            ▼            ▼            ▼            ▼
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │
│Frontend │ │Backend  │ │Integr.  │ │   N     │ │  N+1    │
└─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
     │            │            │
     └────────────┴────────────┘
              │
              ▼
        Telegram Bot
      (Notifications)
```

## Components

### 1. Docker Compose Stack (`docker-compose.yml`)

- **Redis**: Central message bus for coordination
- **agent-frontend**: Frontend specialist container
- **agent-backend**: Backend specialist container
- **agent-integration**: Full-stack/integration container
- **redis-commander**: Debug UI (optional)

### 2. Agent Client Library (`lib/ralph-client/`)

Python library for agent coordination:

```python
from ralph_client import RalphClient, Task, TaskStatus

client = RalphClient()
client.start()

# Register with heartbeat
# Subscribe to messages
# Claim tasks from queue
# Acquire/release file locks
# Store/retrieve artifacts
```

**Modules:**
- `client.py` - Main client class
- `registry.py` - Agent registration & discovery
- `tasks.py` - Task queue management
- `locks.py` - File locking

### 3. Hooks System (`lib/hooks/`)

Automation hooks for pre/post operations:

```json
{
  "hooks": [
    {
      "name": "security-scan",
      "trigger": "pre-commit",
      "command": "python -m lib.hooks.builtin.security_scan",
      "blocking": true
    }
  ]
}
```

**Triggers:**
- `pre-commit`, `post-commit`
- `pre-edit`, `post-edit`
- `pre-task`, `post-task`
- `task-complete`, `task-fail`
- `on-error`

**Built-in Hooks:**
- `security_scan.py` - Detect secrets/credentials
- `file_protection.py` - Check locks before edit

### 4. MCP Server (`mcp-server/`)

Model Context Protocol server for Claude Code integration:

**Tools:**
- `ralph_list_agents` - List active agents
- `ralph_send_task` - Send task to agent
- `ralph_broadcast_task` - Broadcast to all
- `ralph_get_status` - Agent/task status
- `ralph_lock_file` - Acquire file lock
- `ralph_unlock_file` - Release lock
- `ralph_get_artifacts` - Retrieve outputs
- `ralph_send_message` - Inter-agent messaging
- `ralph_get_queue` - View task queue
- `ralph_cancel_task` - Cancel task

### 5. Enhanced Ralph Loop (`plans/ralph-multi.sh`)

Multi-agent aware orchestration script:
- Redis registration & heartbeat
- External task queue polling
- File lock integration
- Hooks execution
- Status broadcasting

## Redis Schema

```
ralph:agents                     # Hash: agent_id → agent_data
ralph:heartbeats:{agent_id}      # String with TTL: heartbeat timestamp
ralph:tasks:queue                # Sorted Set: task_ids by priority
ralph:tasks:data:{task_id}       # String: task JSON
ralph:tasks:claimed:{task_id}    # String: claiming agent_id
ralph:locks:file:{path}          # String: lock data
ralph:artifacts:{id}             # Hash: artifact data
ralph:messages:{agent_id}        # Pub/Sub channel
ralph:broadcast                  # Pub/Sub channel (all agents)
ralph:events                     # Pub/Sub channel (system events)
ralph:telegram:queue             # List: notification queue
```

## Specialist Modes

Agents can operate in different modes:

| Mode | Focus | Tools |
|------|-------|-------|
| implement | Feature development | Build, test, lint |
| debug | Bug investigation | Logs, traces, breakpoints |
| review | Code quality | Lint, complexity, patterns |
| test | Test coverage | Jest, Playwright, coverage |
| security | Vulnerability scanning | SAST, secrets, deps |
| refactor | Code improvement | AST, metrics, patterns |
| docs | Documentation | JSDoc, README, API docs |

## Task Schema

```typescript
interface Task {
  id: string;
  title: string;
  description: string;
  task_type: 'implement' | 'debug' | 'review' | 'test' | 'security' | 'refactor' | 'docs';
  priority: number;  // 1-10
  status: 'pending' | 'claimed' | 'in_progress' | 'blocked' | 'completed' | 'failed';
  assigned_to?: string;
  created_by?: string;
  project?: string;
  files: string[];
  dependencies: string[];
  wait_for: string[];
  artifacts_from: string[];
  acceptance_criteria: string[];
  metadata: Record<string, any>;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  result?: Record<string, any>;
  error?: string;
  orchestration_id?: string;
}
```

## Orchestration Workflow

```
UNDERSTAND → PLAN → DELEGATE → INTEGRATE → VERIFY → DELIVER

1. UNDERSTAND
   - Parse requirements
   - Identify affected systems
   - Map dependencies

2. PLAN
   - Break into tasks
   - Assign to agents by specialty
   - Define task order

3. DELEGATE
   - Send tasks via ralph_send_task
   - Monitor progress
   - Handle blocks

4. INTEGRATE
   - Collect artifacts
   - Merge changes
   - Resolve conflicts

5. VERIFY
   - Run full test suite
   - Security audit
   - Performance check

6. DELIVER
   - Create PR
   - Update docs
   - Notify completion
```

## Quick Start

1. **Start Infrastructure**
   ```bash
   docker-compose up -d redis
   ```

2. **Install MCP Server**
   ```bash
   cd mcp-server && npm install && npm run build
   ```

3. **Configure Claude Code**
   Add to `~/.mcp.json`:
   ```json
   {
     "mcpServers": {
       "ralph": {
         "command": "node",
         "args": ["/path/to/mcp-server/dist/index.js"],
         "env": { "REDIS_URL": "redis://localhost:6379" }
       }
     }
   }
   ```

4. **Start Agents**
   ```bash
   docker-compose up agent-frontend agent-backend
   ```

5. **Orchestrate from Claude Code**
   ```
   Use ralph_list_agents to see active agents
   Use ralph_send_task to assign work
   Use ralph_get_status to monitor progress
   ```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| RALPH_AGENT_ID | Unique agent identifier | agent-default |
| RALPH_AGENT_TYPE | Agent specialty | general |
| RALPH_SPECIALIST_MODES | Comma-separated modes | implement |
| REDIS_URL | Redis connection URL | redis://localhost:6379 |
| OPENROUTER_API_KEY | OpenRouter API key | - |
| ANTHROPIC_MODEL | Primary model | z-ai/glm-4.7 |
| ANTHROPIC_SMALL_FAST_MODEL | Fast model | minimax/minimax-m2.1 |
| TELEGRAM_BOT_TOKEN | Telegram bot token | - |
| TELEGRAM_CHAT_ID | Telegram chat ID | - |

## File Structure

```
ralph-wiggum-test/
├── docker-compose.yml          # Multi-agent stack
├── hooks.json                  # Hooks configuration
├── ARCHITECTURE.md             # This file
├── .devcontainer/              # Base container config
├── lib/
│   ├── ralph-client/           # Python coordination library
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── registry.py
│   │   ├── tasks.py
│   │   └── locks.py
│   ├── hooks/                  # Hooks system
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── runner.py
│   │   └── builtin/
│   │       ├── security_scan.py
│   │       └── file_protection.py
│   ├── modes/                  # Specialist mode definitions
│   └── skills/                 # Domain knowledge bases
├── mcp-server/                 # Claude Code MCP server
│   ├── package.json
│   ├── tsconfig.json
│   └── src/index.ts
├── plans/
│   ├── ralph.sh               # Original single-agent loop
│   ├── ralph-multi.sh         # Multi-agent aware loop
│   ├── prd.json               # Task backlog
│   └── progress.txt           # Progress log
└── projects/                   # Agent workspaces
    ├── frontend/
    ├── backend/
    └── integration/
```

## Next Steps

1. **Phase 1**: Test Redis + 2 agents locally
2. **Phase 2**: Add specialist modes
3. **Phase 3**: Implement skills system
4. **Phase 4**: Full orchestration workflow
5. **Phase 5**: Production hardening
