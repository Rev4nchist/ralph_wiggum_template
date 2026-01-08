<p align="center">
  <img src="assets/ralph-vibe-coder.png" alt="Ralph Wiggum - I'm a Vibe Coder" width="200">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Ready%20to%20Use-brightgreen?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/Tests-482%20Passing-success?style=for-the-badge" alt="Tests">
  <img src="https://img.shields.io/badge/MCP%20Tools-18-blue?style=for-the-badge" alt="MCP Tools">
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License">
</p>

<h1 align="center">🚀 Ralph Wiggum</h1>
<h3 align="center">Multi-Agent Autonomous Coding Platform</h3>

<p align="center">
  <i>"I'm a Vibe Coder!"</i> — Ralph Wiggum
</p>

<p align="center">
  <b>Deploy a swarm of AI agents that collaborate on your codebase while you sleep.</b><br>
  Coordinate multiple Claude Code sessions via MCP. Real-time Telegram notifications keep you in control.
</p>

---

## ✨ Why Ralph Wiggum?

| Problem | Ralph Wiggum Solution |
|---------|----------------------|
| 🐌 Single-agent bottleneck | **Parallel agents** work on frontend, backend, and tests simultaneously |
| 🔥 Race conditions & conflicts | **Atomic task claiming** with Lua scripts + **file locking** prevents collisions |
| 😴 Waiting for AI responses | **Autonomous loops** run overnight; get Telegram pings when decisions needed |
| 📚 Outdated API knowledge | **Librarian integration** searches live documentation before coding |
| 🤔 "What did it do?" | **Full task queue visibility** + artifacts + progress tracking |

---

## 🎯 Perfect For

<table>
<tr>
<td width="33%" align="center">
<h3>🏗️ Large Refactors</h3>
<p>Split work across agents by module. One handles API, another handles tests, third handles UI.</p>
</td>
<td width="33%" align="center">
<h3>🌙 Overnight Builds</h3>
<p>Queue up tasks before bed. Wake up to PRs with passing tests and Telegram summaries.</p>
</td>
<td width="33%" align="center">
<h3>👥 Team Projects</h3>
<p>Each team member runs their own agent. Redis coordinates to prevent stepping on toes.</p>
</td>
</tr>
</table>

---

## 🏛️ Architecture

```
                          ┌─────────────────────────────┐
                          │    👤 YOU (Human-in-Loop)   │
                          │    Telegram Notifications   │
                          └──────────────┬──────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │      CLAUDE CODE + MCP      │
                          │   "ralph_send_task(...)"    │
                          └──────────────┬──────────────┘
                                         │
┌────────────────────────────────────────┼────────────────────────────────────────┐
│                            RALPH MCP SERVER                                      │
│                                                                                  │
│   🔧 ORCHESTRATION          📚 DOCUMENTATION         📱 NOTIFICATIONS           │
│   ├─ ralph_send_task        ├─ librarian_search      └─ Telegram Bot            │
│   ├─ ralph_list_agents      ├─ librarian_search_api                             │
│   ├─ ralph_lock_file        └─ librarian_get_document                           │
│   └─ ralph_get_status                                                           │
└────────────────────────────────────────┬────────────────────────────────────────┘
                                         │
                          ┌──────────────▼──────────────┐
                          │         REDIS BUS          │
                          │  Tasks • Locks • Heartbeats │
                          └──────────────┬──────────────┘
                                         │
              ┌──────────────────────────┼──────────────────────────┐
              │                          │                          │
    ┌─────────▼─────────┐     ┌─────────▼─────────┐     ┌─────────▼─────────┐
    │   🎨 AGENT        │     │   ⚙️ AGENT        │     │   🧪 AGENT        │
    │   Frontend        │     │   Backend         │     │   Testing         │
    │   React/Vue/etc   │     │   APIs/Services   │     │   Jest/Pytest     │
    └───────────────────┘     └───────────────────┘     └───────────────────┘
```

---

## 🛠️ 18 MCP Tools at Your Fingertips

<details>
<summary><b>🔧 Orchestration Tools (11)</b> — Click to expand</summary>

| Tool | What It Does |
|------|--------------|
| `ralph_list_agents` | See all active agents and their current status |
| `ralph_send_task` | Assign a task to a specific agent |
| `ralph_broadcast_task` | Send task to all agents (or filtered by type) |
| `ralph_get_status` | Check progress on any agent or task |
| `ralph_lock_file` | Claim exclusive edit rights (prevents conflicts) |
| `ralph_unlock_file` | Release your file lock |
| `ralph_get_artifacts` | Retrieve task outputs and results |
| `ralph_send_message` | Send a message to another agent |
| `ralph_get_queue` | View all pending tasks |
| `ralph_cancel_task` | Cancel a queued task |
| `ralph_validate_deps` | Check for circular dependency issues |

</details>

<details>
<summary><b>📚 Librarian Tools (6)</b> — Live documentation search</summary>

| Tool | What It Does |
|------|--------------|
| `librarian_find_library` | Find the library ID (e.g., "react" → "reactjs/react.dev") |
| `librarian_search` | Search documentation with hybrid keyword+semantic |
| `librarian_search_api` | Look up specific API/function docs |
| `librarian_search_error` | Find solutions for error messages |
| `librarian_list_sources` | See all indexed documentation sources |
| `librarian_get_document` | Retrieve full document content |

</details>

<details>
<summary><b>📱 Telegram Integration</b> — Stay in the loop</summary>

```bash
# Agent asks you a question
./plans/notify.sh "question" "Should I use REST or GraphQL for this API?"

# You reply in Telegram, agent picks it up
./plans/check-response.sh
# → "Use GraphQL, we're standardizing on it"
```

**Bot:** [@ralph_wiggum_template_bot](https://t.me/ralph_wiggum_template_bot)

</details>

---

## ⚡ Quick Start (5 minutes)

### 1️⃣ Clone & Configure

```bash
git clone https://github.com/Rev4nchist/ralph_wiggum_template.git
cd ralph_wiggum_template

cp .env.example .env
# Edit .env with your API keys

# ⚠️ Security: See docs/SECRETS_MANAGEMENT.md for proper key handling
```

### 2️⃣ Install Dependencies

```bash
# Python
pip install -r requirements.txt

# Node.js + MCP Server
npm install
cd mcp-server && npm install && npm run build && cd ..
```

### 3️⃣ Start Redis

```bash
docker-compose up -d redis
```

### 4️⃣ Add to Claude Code

Add to your `~/.mcp.json`:

```json
{
  "mcpServers": {
    "ralph": {
      "command": "node",
      "args": ["/path/to/ralph_wiggum_template/mcp-server/dist/index.js"],
      "env": {
        "REDIS_URL": "redis://localhost:6379"
      }
    }
  }
}
```

### 5️⃣ Verify Installation

```bash
# Run all 482 tests
npm test && python -m pytest tests/ -v
```

**You're ready!** Open Claude Code and try: `Use ralph_list_agents to see active agents`

---

## 🎭 Specialist Modes

Pre-built agent personas for different development phases:

| Specialist | Superpower | Best For |
|------------|------------|----------|
| 🔍 **code-reviewer** | Quality, security, performance analysis | Post-implementation review |
| 🐛 **debugger** | Root cause analysis, systematic bug hunting | When things break |
| 🧪 **test-architect** | Test strategy, coverage optimization | Building test suites |
| ♻️ **refactorer** | Code structure, tech debt elimination | Cleanup sprints |
| 🔒 **security-auditor** | OWASP checks, vulnerability detection | Pre-release audits |
| 📝 **docs-writer** | README, API docs, architecture diagrams | Documentation sprints |

---

## 🧪 Battle-Tested

<table>
<tr>
<td align="center"><h1>482</h1><p>Tests Passing</p></td>
<td align="center"><h1>164</h1><p>New Tests Added</p></td>
<td align="center"><h1>0</h1><p>Known Race Conditions</p></td>
</tr>
</table>

| Component | Tests | Why It Matters |
|-----------|-------|----------------|
| Atomic Task Claiming | 7 | Lua scripts prevent duplicate work |
| File Locks | 13 | No two agents edit same file |
| Agent Registry | 12 | Dead agents don't receive tasks |
| Cycle Detection | 15 | Prevents dependency deadlocks |
| Task Queue Ops | 10 | Reliable task lifecycle |
| MCP Server Tools | 53 | All 17 tools validated |
| Hook System | 51 | Automation triggers tested |
| Memory System | 35 | Agent persistence verified |
| Telegram Scripts | 25 | Notification flow validated |

---

## 📂 Project Structure

```
ralph_wiggum_template/
├── 🔧 mcp-server/              # TypeScript MCP server (18 tools)
│   └── src/index.ts
│
├── 📚 lib/
│   ├── ralph-client/           # Python coordination (tasks, locks, registry)
│   ├── hooks/                  # Automation hooks (pre-commit, post-edit)
│   ├── memory/                 # Persistent memory across sessions
│   └── librarian/              # Documentation search wrapper
│
├── 📋 templates/
│   ├── agent-CLAUDE.md         # Base agent instructions
│   └── specialists/            # 6 specialist mode templates
│
├── 🚀 plans/
│   ├── notify.sh               # Telegram notifications
│   └── check-response.sh       # Poll for human responses
│
├── 🧪 tests/                   # 93 tests (Python + TypeScript)
│
└── 🐳 docker-compose.yml       # Redis + services
```

---

## 🆘 Troubleshooting

<details>
<summary><b>Redis won't connect</b></summary>

```bash
docker-compose ps redis          # Check if running
docker-compose restart redis     # Restart it
docker-compose logs redis        # Check logs
```
</details>

<details>
<summary><b>Agent not appearing in list</b></summary>

```bash
redis-cli KEYS "ralph:heartbeats:*"   # Check heartbeats
redis-cli KEYS "ralph:agents"         # Check registry
```
</details>

<details>
<summary><b>File lock stuck</b></summary>

```bash
redis-cli KEYS "ralph:locks:*"                    # List all locks
redis-cli DEL "ralph:locks:file:/path/to/file"   # Force release
```
</details>

<details>
<summary><b>Telegram not working</b></summary>

```bash
# Test bot connection
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe"

# Send test message
./plans/notify.sh "status" "Test message"
```
</details>

---

## 🤝 Contributing

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Run tests (`npm test && pytest`)
4. Commit your changes
5. Push to the branch
6. Open a Pull Request

---

## 📜 License

MIT — Use it, modify it, ship it.

---

<p align="center">
  <i>"I'm learnding!"</i> — Ralph Wiggum
</p>

<p align="center">
  <b>Built with ❤️ for teams who want AI agents that actually work together.</b>
</p>
