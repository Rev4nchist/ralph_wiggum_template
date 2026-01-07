# Ralph Wiggum Multi-Agent Orchestration Platform

> *"The people who are crazy enough to think they can change the world are the ones who do."*

A multi-agent autonomous coding platform where AI agents collaborate on software projects, coordinated by Claude Code sessions via MCP.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE SESSION                          │
│            (Human-in-the-loop control via MCP)                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RALPH MCP SERVER                              │
│     ralph_list_agents │ ralph_send_task │ ralph_lock_file       │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  REDIS   │    │CLAUDE-MEM│    │LIBRARIAN │
    │ Working  │    │Persistent│    │ External │
    │ Memory   │    │  Memory  │    │Knowledge │
    └────┬─────┘    └────┬─────┘    └────┬─────┘
         │               │               │
         └───────────────┴───────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐    ┌──────────┐    ┌──────────┐
   │  Agent   │    │  Agent   │    │  Agent   │
   │ Frontend │    │ Backend  │    │Integration│
   └──────────┘    └──────────┘    └──────────┘
```

---

## Starting a New Project

### The Flow

```
1. START CLAUDE CODE → "I want to start a new Ralph Wiggum project"
                            │
2. UPLOAD PRD         → You provide requirements document
                            │
3. TASKMASTER PARSES  → npx task-master parse-prd --input prd.md
                            │
4. CONVERT TO RALPH   → ./scripts/generate-prd.sh --from-taskmaster
                            │
5. SETUP WORKSPACES   → Creates backend/frontend agent directories
                            │
6. LAUNCH AGENTS      → Start Redis, run agents in terminals
```

### Quick Start (Tell Claude Code)

```
I want to start a new Ralph Wiggum multi-agent project.
Platform: C:\Users\david.hayes\Projects\ralph-wiggum-test

Here's my PRD: [paste or upload your requirements document]

Please parse it with Taskmaster, convert to Ralph format, and set up agents.
```

### Manual Setup

```bash
# 1. Parse PRD with Taskmaster
npx task-master parse-prd --input my-project-prd.md

# 2. Convert to Ralph format
./scripts/generate-prd.sh ./my-project --from-taskmaster

# 3. Setup agent workspaces
./scripts/setup-agent-workspace.sh ./my-project/backend agent-backend backend "implement,test"
./scripts/setup-agent-workspace.sh ./my-project/frontend agent-frontend frontend "implement,test"

# 4. Start infrastructure
docker-compose up -d redis

# 5. Run agents (separate terminals)
cd ./my-project/backend && ./plans/ralph-multi.sh 10
cd ./my-project/frontend && ./plans/ralph-multi.sh 10
```

See [BOOTSTRAP.md](BOOTSTRAP.md) for detailed instructions.

---

## Features

### Multi-Agent Coordination
- **Redis Message Bus** — Real-time task queue, file locks, agent registry
- **Task Dependencies** — Agents wait for dependent tasks to complete
- **File Locking** — Pessimistic locking prevents edit conflicts
- **Artifact Sharing** — Agents share build outputs and results

### Persistent Memory (Claude-Mem)
- **Architecture Decisions** — Design choices survive across sessions
- **Code Patterns** — Discovered patterns shared with all agents
- **Blockers & Solutions** — Problems solved once, remembered forever
- **Handoff Notes** — Seamless continuity between agents

### Documentation Search (Librarian)
- **Research First** — Search docs before implementing unfamiliar code
- **Best Practices** — Find established patterns for any library
- **Up-to-date** — Always current documentation

### Intelligent Model Routing
| Task Type | Model | Purpose |
|-----------|-------|---------|
| Planning/Review | `claude-opus-4.5` | Architecture, design, quality |
| Implementation | `z-ai/glm-4.7` | Coding, features, debugging |
| Testing/Docs | `minimax-m2.1` | Fast verification, documentation |

### Automation Hooks
- **Pre-commit** — Security scan, lint, type check
- **Post-edit** — Auto-format code
- **Task-complete** — Run tests, verify build

### Specialist Agents

Six specialist modes for different phases of the development lifecycle:

| Specialist | Purpose | Model | Dev Phase |
|------------|---------|-------|-----------|
| **code-reviewer** | Quality, security, performance review | minimax | Post-implementation |
| **debugger** | Root cause analysis, bug fixing | glm | When errors occur |
| **test-architect** | Test design, coverage improvement | glm | Alongside features |
| **refactorer** | Code structure, tech debt reduction | glm | Cleanup sprints |
| **security-auditor** | OWASP Top 10, vulnerability detection | minimax | Pre-release |
| **docs-writer** | README, API docs, architecture docs | minimax | Post-feature |

See `templates/specialists/` for detailed specialist instructions.

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+
- Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
- OpenRouter API key

### 1. Clone and Configure

```bash
git clone <repo> ralph-wiggum
cd ralph-wiggum

# Copy environment template
cp .env.example .env

# Edit .env with your API keys
# - OPENROUTER_API_KEY (required)
# - TELEGRAM_BOT_TOKEN (optional)
# - TELEGRAM_CHAT_ID (optional)
```

### 2. Start Infrastructure

```bash
# Start Redis
docker-compose up -d redis

# Verify Redis is running
docker-compose ps
```

### 3. Build MCP Server

```bash
cd mcp-server
npm install
npm run build
cd ..
```

### 4. Configure Claude Code MCP

Add to `~/.mcp.json`:

```json
{
  "mcpServers": {
    "ralph": {
      "command": "node",
      "args": ["/path/to/ralph-wiggum/mcp-server/dist/index.js"],
      "env": {
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

### 5. Setup Agent Workspaces

```bash
# Create frontend agent workspace
./scripts/setup-agent-workspace.sh ./projects/frontend agent-frontend frontend "implement,debug,review"

# Create backend agent workspace
./scripts/setup-agent-workspace.sh ./projects/backend agent-backend backend "implement,debug,security"
```

### 6. Start Agents

```bash
# Terminal 1: Frontend agent
docker-compose up agent-frontend

# Terminal 2: Backend agent
docker-compose up agent-backend
```

### 7. Orchestrate from Claude Code

```
Use ralph_list_agents to see active agents
Use ralph_send_task to assign work to specific agents
Use ralph_get_status to monitor progress
```

---

## Architecture

### Directory Structure

```
ralph-wiggum/
├── docker-compose.yml          # Multi-agent stack
├── hooks.json                  # Automation hooks config
├── .env                        # Environment variables
│
├── lib/
│   ├── ralph-client/           # Python coordination library
│   │   ├── client.py           # Main client class
│   │   ├── registry.py         # Agent discovery
│   │   ├── tasks.py            # Task queue
│   │   └── locks.py            # File locking
│   │
│   ├── hooks/                  # Automation hooks
│   │   ├── runner.py           # Hook execution
│   │   └── builtin/            # Built-in hooks
│   │
│   └── memory/                 # Claude-Mem integration
│       ├── project_memory.py   # Memory operations
│       └── memory_protocol.py  # Categories & triggers
│
├── mcp-server/                 # Claude Code MCP server
│   └── src/index.ts            # MCP tools implementation
│
├── templates/
│   ├── agent-CLAUDE.md         # Agent instruction template
│   └── specialists/            # Specialist mode templates
│       ├── code-reviewer.md    # Code review protocol
│       ├── debugger.md         # Bug fixing protocol
│       ├── test-architect.md   # Test design protocol
│       ├── refactorer.md       # Refactoring protocol
│       ├── security-auditor.md # Security audit protocol
│       └── docs-writer.md      # Documentation protocol
│
├── scripts/
│   └── setup-agent-workspace.sh
│
├── plans/
│   ├── ralph-multi.sh          # Multi-agent orchestration loop
│   ├── prd.json                # Task backlog
│   └── progress.txt            # Progress log
│
└── projects/                   # Agent workspaces
    ├── frontend/
    ├── backend/
    └── integration/
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `ralph_list_agents` | List active agents with status |
| `ralph_send_task` | Send task to specific agent |
| `ralph_broadcast_task` | Send task to all/filtered agents |
| `ralph_get_status` | Get agent or task status |
| `ralph_lock_file` | Acquire file lock |
| `ralph_unlock_file` | Release file lock |
| `ralph_get_artifacts` | Get task outputs |
| `ralph_send_message` | Send message to agent |
| `ralph_get_queue` | View pending tasks |
| `ralph_cancel_task` | Cancel pending task |

---

## Agent Philosophy

Each agent operates with these principles:

1. **Think Different** — Question assumptions, find elegant solutions
2. **Obsess Over Details** — Understand the codebase deeply
3. **Plan Like Da Vinci** — Sketch architecture before coding
4. **Craft, Don't Code** — Every function name should sing
5. **Iterate Relentlessly** — First version is never enough
6. **Simplify Ruthlessly** — Remove unnecessary complexity

---

## Memory System

### Categories

| Category | Purpose |
|----------|---------|
| `architecture` | Design decisions and rationale |
| `pattern` | Code patterns to follow |
| `blocker` | Problems and solutions |
| `handoff` | Notes for next agent |

### Usage

```python
from lib.memory import ProjectMemory

memory = ProjectMemory(project_id="my-app", agent_id="agent-frontend")
memory.note_architecture("Repository pattern", "Separates concerns")
memory.handoff("task-001", "API complete", ["Frontend can integrate"])
```

---

## Single-Agent Mode

For simpler projects, run a single agent:

```bash
# Single iteration (testing)
./plans/ralph-multi.sh --once

# Full loop (20 iterations)
./plans/ralph-multi.sh 20

# Dry run (show prompt)
./plans/ralph-multi.sh --dry-run
```

---

## Monitoring

| What | Command |
|------|---------|
| Progress | `tail -f plans/progress.txt` |
| Logs | `tail -f plans/ralph.log` |
| Metrics | `cat plans/metrics.csv` |
| Claude-Mem UI | http://localhost:37777 |
| Redis UI | http://localhost:8081 (debug profile) |

---

## Telegram Notifications

1. Create bot via [@BotFather](https://t.me/BotFather)
2. Get chat ID from [@userinfobot](https://t.me/userinfobot)
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`

---

## Troubleshooting

### Redis Connection Failed
```bash
docker-compose ps redis
docker-compose logs redis
docker-compose restart redis
```

### Agent Not Registering
```bash
redis-cli KEYS "ralph:heartbeats:*"
```

### File Lock Stuck
```bash
redis-cli KEYS "ralph:locks:*"
redis-cli DEL "ralph:locks:file:path"  # Force release
```

---

## License

MIT

---

*Built with craftsmanship. Every line of code should feel inevitable.*
