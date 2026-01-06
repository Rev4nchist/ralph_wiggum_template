# Ralph Wiggum Test Project

Autonomous coding loop test environment integrating:
- **Ralph Wiggum** - Iterative autonomous development
- **Claude-Mem** - Persistent memory across sessions
- **Librarian** - Documentation search
- **Telegram** - iOS bidirectional notifications

## Quick Start

### 1. Prerequisites

- Docker Desktop (Linux containers mode)
- VS Code with Dev Containers extension
- Anthropic API key
- (Optional) Telegram Bot token for notifications

### 2. Environment Variables

Create `.env` file in project root or set in your shell:

```bash
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# Optional: Telegram notifications
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_CHAT_ID="your-chat-id"
```

### 3. Open in DevContainer

1. Open this folder in VS Code
2. Click "Reopen in Container" when prompted
3. Wait for container build and setup

### 4. Initialize (inside container)

```bash
# Install npm dependencies
npm install

# (Optional) Set up Librarian
librarian setup
librarian seed
librarian ingest --embed
```

### 5. Run Ralph Loop

```bash
# Single iteration (for testing)
./plans/ralph.sh --once

# Full autonomous loop (20 iterations)
./plans/ralph.sh 20

# Overnight run (100 iterations)
tmux new-session -d -s ralph './plans/ralph.sh 100'
```

## Setting Up Telegram Notifications

1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram
2. Get your chat ID by messaging [@userinfobot](https://t.me/userinfobot)
3. Set environment variables:
   - `TELEGRAM_BOT_TOKEN`: The token from BotFather
   - `TELEGRAM_CHAT_ID`: Your chat ID

## Project Structure

```
ralph-wiggum-test/
├── .devcontainer/       # DevContainer config
├── .claude/             # Claude Code settings
├── .librarian/          # Documentation sources
├── plans/
│   ├── prd.json         # Task backlog
│   ├── progress.txt     # Progress log
│   ├── ralph.sh         # Main loop script
│   └── notify.sh        # Telegram notifications
├── src/                 # Source code (created by Ralph)
└── tests/               # Tests (created by Ralph)
```

## Monitoring

- **Progress**: `tail -f plans/progress.txt`
- **Logs**: `tail -f plans/ralph.log`
- **Metrics**: `cat plans/metrics.csv`
- **Claude-Mem UI**: http://localhost:37777

## Commands

```bash
# View PRD status
jq '.' plans/prd.json

# Reset PRD (mark all incomplete)
jq '.[].passes = false' plans/prd.json > tmp.json && mv tmp.json plans/prd.json

# Manual notification test
./plans/notify.sh status "Test message"
```
