# Ralph Wiggum Multi-Agent Orchestration Platform

> *"Me fail English? That's unpossible!"* — Ralph Wiggum

A multi-agent autonomous coding platform where AI agents collaborate on software projects, coordinated by Claude Code sessions via MCP (Model Context Protocol).

---

## Status: Pre-Release Template

This repository serves as a **template** for setting up Ralph Wiggum multi-agent projects. It includes:
- Fully functional MCP server with 18 tools
- Python coordination library (tasks, locks, registry)
- Librarian documentation search integration
- Telegram bidirectional notifications
- 93 passing tests (Python + TypeScript)

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     CLAUDE CODE SESSION                          │
│            (Human-in-the-loop control via MCP)                  │
└─────────────────────────┬───────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RALPH MCP SERVER                              │
│  18 Tools: ralph_* (orchestration) + librarian_* (docs search) │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          ▼               ▼               ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │  REDIS   │    │TELEGRAM  │    │LIBRARIAN │
    │ Task Bus │    │  Human   │    │   Docs   │
    │ + Locks  │    │  Loop    │    │  Search  │
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

## Core Components

### MCP Server (18 Tools)

**Orchestration Tools:**
| Tool | Description |
|------|-------------|
| `ralph_list_agents` | List active agents with status |
| `ralph_send_task` | Send task to specific agent |
| `ralph_broadcast_task` | Broadcast to all/filtered agents |
| `ralph_get_status` | Get agent or task status |
| `ralph_lock_file` | Acquire file lock (prevents conflicts) |
| `ralph_unlock_file` | Release file lock |
| `ralph_get_artifacts` | Get task outputs |
| `ralph_send_message` | Send message to agent |
| `ralph_get_queue` | View pending tasks |
| `ralph_cancel_task` | Cancel pending task |
| `ralph_validate_deps` | Check for circular dependencies |

**Documentation Search Tools (Librarian):**
| Tool | Description |
|------|-------------|
| `librarian_find_library` | Find library ID for searching |
| `librarian_search` | Search indexed documentation |
| `librarian_search_api` | Find API/function docs |
| `librarian_search_error` | Find error solutions |
| `librarian_list_sources` | List available doc sources |
| `librarian_get_document` | Retrieve specific document |

### Python Coordination Library

```
lib/ralph-client/
├── client.py      # Main RalphClient class
├── tasks.py       # TaskQueue with atomic Lua claiming
├── locks.py       # FileLock with pessimistic locking
└── registry.py    # AgentRegistry with TTL heartbeats
```

**Key Features:**
- **Atomic Task Claiming**: Lua script prevents race conditions
- **Cycle Detection**: DFS algorithm prevents dependency deadlocks
- **File Locking**: Pessimistic locking with TTL expiration
- **Heartbeat System**: 30-second TTL for agent liveness

### Telegram Human-in-the-Loop

Bidirectional communication for human oversight:
```bash
# Send notification
./plans/notify.sh "question" "Should I refactor this module?"

# Check for response
./plans/check-response.sh
```

Bot: [@ralph_wiggum_template_bot](https://t.me/ralph_wiggum_template_bot)

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Node.js 20+
- Python 3.10+
- Claude Code CLI
- OpenRouter API key

### 1. Clone and Configure

```bash
git clone <repo> ralph-wiggum
cd ralph-wiggum

# Copy environment template
cp .env.example .env

# Edit .env with your API keys:
# - OPENROUTER_API_KEY (required)
# - TELEGRAM_BOT_TOKEN (for notifications)
# - TELEGRAM_CHAT_ID (for notifications)
```

### 2. Install Dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Node.js dependencies
npm install

# MCP Server
cd mcp-server && npm install && npm run build && cd ..
```

### 3. Start Infrastructure

```bash
# Start Redis
docker-compose up -d redis

# Verify
docker-compose ps
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

### 5. Run Tests

```bash
# Python tests (40 tests)
python -m pytest tests/unit/py/ralph_client/ -v

# TypeScript tests (53 tests)
npm test

# All 93 tests should pass
```

---

## Project Structure

```
ralph-wiggum/
├── mcp-server/                 # MCP server (TypeScript)
│   └── src/index.ts            # 18 tools implementation
│
├── lib/
│   ├── ralph-client/           # Coordination library (Python)
│   │   ├── client.py           # Main client
│   │   ├── tasks.py            # Task queue + Lua claiming
│   │   ├── locks.py            # File locking
│   │   └── registry.py         # Agent registry
│   │
│   ├── hooks/                  # Automation hooks
│   │   ├── runner.py           # Hook execution
│   │   └── builtin/            # Pre-commit, post-edit, etc.
│   │
│   ├── memory/                 # Persistent memory
│   │   ├── project_memory.py   # Memory operations
│   │   └── memory_protocol.py  # Categories & triggers
│   │
│   └── librarian/              # Documentation search
│       ├── client.py           # Librarian CLI wrapper
│       └── detect.py           # Library detection
│
├── templates/
│   ├── agent-CLAUDE.md         # Agent instruction template
│   └── specialists/            # 6 specialist modes
│       ├── code-reviewer.md
│       ├── debugger.md
│       ├── test-architect.md
│       ├── refactorer.md
│       ├── security-auditor.md
│       └── docs-writer.md
│
├── plans/
│   ├── ralph-multi.sh          # Multi-agent loop script
│   ├── notify.sh               # Telegram notifications
│   └── check-response.sh       # Poll for user responses
│
├── scripts/
│   ├── setup-agent-workspace.sh
│   └── generate-prd.sh
│
├── tests/
│   ├── conftest.py             # Pytest fixtures
│   └── unit/
│       ├── py/ralph_client/    # Python tests (40)
│       └── ts/                 # TypeScript tests (15)
│
├── docker-compose.yml          # Redis + optional services
├── hooks.json                  # Hook configuration
└── .env                        # Environment variables
```

---

## Test Coverage

**93 tests passing** across Python and TypeScript:

| Component | Tests | Priority |
|-----------|-------|----------|
| Task Claiming (Lua) | 7 | P0 Critical |
| File Locks | 13 | P0 Critical |
| Agent Registry | 12 | P0 Critical |
| Cycle Detection | 15 | P0 Critical |
| Task Queue Ops | 10 | P1 High |
| Other (calc, strings) | 36 | Demo |

```bash
# Run all tests
python -m pytest tests/unit/py/ -v && npm test
```

---

## Specialist Modes

Six specialist templates for different development phases:

| Specialist | Purpose | When to Use |
|------------|---------|-------------|
| **code-reviewer** | Quality, security, performance | Post-implementation |
| **debugger** | Root cause analysis, bug fixing | When errors occur |
| **test-architect** | Test design, coverage | Alongside features |
| **refactorer** | Code structure, tech debt | Cleanup sprints |
| **security-auditor** | OWASP, vulnerability detection | Pre-release |
| **docs-writer** | README, API docs, architecture | Post-feature |

---

## Creating a New Project

### Using This Template

1. Fork or clone this repository
2. Configure `.env` with your API keys
3. Set up agent workspaces:

```bash
./scripts/setup-agent-workspace.sh ./projects/backend agent-backend backend "implement,test"
./scripts/setup-agent-workspace.sh ./projects/frontend agent-frontend frontend "implement,test"
```

4. Start agents:

```bash
# Terminal 1
docker-compose up agent-backend

# Terminal 2
docker-compose up agent-frontend
```

5. Orchestrate from Claude Code:

```
Use ralph_list_agents to see active agents
Use ralph_send_task to assign work
Use ralph_get_status to monitor progress
```

---

## Troubleshooting

### Redis Connection Failed
```bash
docker-compose ps redis
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

### Telegram Not Working
```bash
# Test bot connection
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# Send test message
./plans/notify.sh "status" "Test message"
```

---

## License

MIT

---

*"I'm learnding!"* — Ralph Wiggum
