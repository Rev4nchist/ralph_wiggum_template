# Secrets Management for Ralph Wiggum

## Golden Rule

**NEVER commit secrets to git.** Not even "temporarily." Git history is forever.

---

## Quick Setup

### 1. Copy the Example File
```bash
cp .env.example .env
```

### 2. Edit `.env` with Your Real Keys
```bash
# Use your preferred editor
nano .env
# or
code .env
```

### 3. Verify `.env` is Gitignored
```bash
git check-ignore .env
# Should output: .env
```

---

## Required Secrets

| Variable | Source | Purpose |
|----------|--------|---------|
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | LLM API access |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) | Human-in-the-loop notifications |
| `TELEGRAM_CHAT_ID` | [@userinfobot](https://t.me/userinfobot) | Your Telegram user ID |
| `REDIS_URL` | Your Redis instance | Agent coordination (optional) |

---

## File Structure

```
ralph-wiggum-test/
├── .env                  # YOUR secrets (gitignored, never commit)
├── .env.example          # Template with placeholders (committed)
├── .gitignore            # Must include .env
└── plans/
    └── setup-openrouter.sh  # Reads from env vars, no hardcoded secrets
```

---

## What Goes Where

### `.env` (Local Only - NEVER Commit)
```bash
# Real secrets - this file stays on your machine only
OPENROUTER_API_KEY=sk-or-v1-your-real-key-here
TELEGRAM_BOT_TOKEN=1234567890:AAH-your-real-token-here
TELEGRAM_CHAT_ID=your-chat-id
REDIS_URL=redis://localhost:6379
```

### `.env.example` (Committed - Safe Template)
```bash
# Template for other developers - no real values
OPENROUTER_API_KEY=your-openrouter-key-here
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=your-chat-id-here
REDIS_URL=redis://localhost:6379
```

---

## Loading Secrets

### In Bash Scripts
```bash
#!/bin/bash
# Load from .env file
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Validate required vars
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY not set"
    exit 1
fi
```

### In Python
```python
from dotenv import load_dotenv
import os

load_dotenv()  # Loads from .env

api_key = os.getenv('OPENROUTER_API_KEY')
if not api_key:
    raise ValueError("OPENROUTER_API_KEY not set")
```

### In TypeScript/Node
```typescript
import dotenv from 'dotenv';
dotenv.config();

const apiKey = process.env.OPENROUTER_API_KEY;
if (!apiKey) {
    throw new Error('OPENROUTER_API_KEY not set');
}
```

### In Docker Compose
```yaml
services:
  ralph-agent:
    env_file:
      - .env  # Loads all vars from .env
    environment:
      - REDIS_URL=${REDIS_URL}  # Or reference individually
```

---

## DevContainer Setup

The DevContainer automatically loads `.env` if present. For first-time setup:

1. Create `.env` in project root before starting container
2. Or create inside container at `/workspaces/ralph-wiggum-test/.env`

```bash
# Inside DevContainer
cd /workspaces/ralph-wiggum-test
cp .env.example .env
nano .env  # Add your real keys
```

---

## Pre-Commit Hook (Recommended)

Add to `.git/hooks/pre-commit`:

```bash
#!/bin/bash
# Prevent accidental secret commits

# Patterns that indicate secrets
PATTERNS=(
    'sk-or-v1-[a-zA-Z0-9]+'
    '[0-9]+:AA[A-Za-z0-9_-]+'
    'ghp_[a-zA-Z0-9]+'
    'api[_-]?key\s*=\s*["\x27][^"\x27]+'
)

for pattern in "${PATTERNS[@]}"; do
    if git diff --cached | grep -qE "$pattern"; then
        echo "ERROR: Potential secret detected in staged changes!"
        echo "Pattern: $pattern"
        echo "Run 'git diff --cached' to review"
        exit 1
    fi
done
```

Make executable: `chmod +x .git/hooks/pre-commit`

---

## If You Accidentally Commit Secrets

### 1. Rotate Immediately
The secret is compromised. Generate new keys before doing anything else.

### 2. Remove from Current Files
Edit the file to remove the secret, commit the fix.

### 3. Remove from Git History (Optional but Recommended)

Using BFG Repo Cleaner:
```bash
# Install BFG
brew install bfg  # macOS
# or download from https://rtyley.github.io/bfg-repo-cleaner/

# Create file with secrets to remove
echo "sk-or-v1-your-leaked-key" > secrets.txt
echo "1234567890:AAH-your-leaked-token" >> secrets.txt

# Run BFG
bfg --replace-text secrets.txt your-repo.git

# Force push (coordinate with team first!)
git reflog expire --expire=now --all
git gc --prune=now --aggressive
git push --force
```

### 4. Dismiss Security Alerts
Mark incidents as resolved in GitGuardian/GitHub Security.

---

## Checklist Before Every Commit

- [ ] `git diff --cached` - Review staged changes
- [ ] No API keys, tokens, or passwords visible
- [ ] `.env` is NOT in staged files
- [ ] Setup scripts reference `$ENV_VAR`, not hardcoded values

---

## Common Mistakes to Avoid

| Mistake | Why It's Bad | Correct Approach |
|---------|--------------|------------------|
| Hardcoding in scripts | Committed to history forever | Use `$ENV_VAR` references |
| `.env` not in `.gitignore` | Gets committed accidentally | Always gitignore `.env` |
| Copying secrets to docs | Docs get committed | Link to setup instructions |
| "Temporary" test keys | No such thing as temporary in git | Use `.env` from day one |
| Sharing `.env` via git | Defeats the purpose | Use secure channels (1Password, etc.) |

---

## Team Secret Sharing

For sharing secrets with team members:

1. **1Password/Bitwarden** - Shared vault for team secrets
2. **Azure Key Vault** - For production deployments
3. **Doppler/Infisical** - Secrets management platforms
4. **Direct message** - Last resort, delete after sharing

**NEVER:** Email, Slack channels, git commits, documentation

---

*Last updated: 2026-01-08*
*After the great OpenRouter key incident of January 2026*
