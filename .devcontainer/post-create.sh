#!/bin/bash
set -e

echo "=== Post-Create Setup ==="
echo "Working directory: $(pwd)"
echo "User: $(whoami)"
echo "Home: $HOME"

# Ensure PATH includes bun and uv
export PATH="$HOME/.bun/bin:$HOME/.local/bin:$PATH"

# Verify bun is available
if command -v bun &> /dev/null; then
    echo "✓ Bun $(bun --version) available"
else
    echo "⚠ Bun not found, installing..."
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
fi

# Verify uv is available
if command -v uv &> /dev/null; then
    echo "✓ uv available"
else
    echo "⚠ uv not found, installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Install Claude-Mem plugin
echo ""
echo "=== Installing Claude-Mem Plugin ==="
if command -v claude &> /dev/null; then
    echo "Adding Claude-Mem from marketplace..."
    claude mcp add claude-mem -- npx -y @anthropic-ai/claude-mem-mcp 2>/dev/null || \
    echo "Note: Claude-Mem MCP may need manual configuration"
else
    echo "⚠ Claude Code CLI not found"
fi

# Install Ralph Wiggum plugin
echo ""
echo "=== Installing Ralph Wiggum Plugin ==="
if command -v claude &> /dev/null; then
    echo "Note: Ralph Wiggum is typically run via the external loop script"
    echo "The plugin provides the Stop hook behavior"
fi

# Install Librarian
echo ""
echo "=== Installing Librarian ==="
if [ ! -d "$HOME/.librarian-cli" ]; then
    echo "Cloning Librarian..."
    git clone https://github.com/iannuttall/librarian.git "$HOME/.librarian-cli" || {
        echo "Failed to clone Librarian, trying npm install..."
        npm install -g @iannuttall/librarian 2>/dev/null || true
    }

    if [ -d "$HOME/.librarian-cli" ]; then
        cd "$HOME/.librarian-cli"
        bun install
        echo "✓ Librarian installed from source"
        cd /workspace
    fi
fi

# Add librarian to PATH in shell configs
if [ -d "$HOME/.librarian-cli" ]; then
    LIBRARIAN_PATH='export PATH="$HOME/.librarian-cli:$PATH"'
    grep -q ".librarian-cli" "$HOME/.zshrc" 2>/dev/null || echo "$LIBRARIAN_PATH" >> "$HOME/.zshrc"
    grep -q ".librarian-cli" "$HOME/.bashrc" 2>/dev/null || echo "$LIBRARIAN_PATH" >> "$HOME/.bashrc"
fi

# Create Claude-Mem settings if not exists
echo ""
echo "=== Configuring Claude-Mem ==="
if [ ! -f "$HOME/.claude-mem/settings.json" ]; then
    mkdir -p "$HOME/.claude-mem"
    cat > "$HOME/.claude-mem/settings.json" << 'CLAUDE_MEM_EOF'
{
  "worker": {
    "port": 37777,
    "autoStart": true,
    "healthCheck": {
      "enabled": true,
      "interval": 30000
    }
  },
  "compression": {
    "model": "claude-sonnet-4-20250514",
    "maxTokens": 4096,
    "temperature": 0.3
  },
  "context": {
    "injection": {
      "enabled": true,
      "maxTokens": 8000,
      "strategy": "progressive",
      "includeObservations": true,
      "includeSummaries": true
    }
  },
  "search": {
    "hybrid": true,
    "vectorWeight": 0.6,
    "keywordWeight": 0.4
  },
  "storage": {
    "retentionDays": 90
  },
  "privacy": {
    "excludePatterns": [
      "**/secrets/**",
      "**/.env*",
      "**/credentials*"
    ]
  },
  "logging": {
    "level": "info"
  }
}
CLAUDE_MEM_EOF
    echo "✓ Claude-Mem settings created"
else
    echo "✓ Claude-Mem settings already exist"
fi

# Create Librarian config if not exists
echo ""
echo "=== Configuring Librarian ==="
if [ ! -f "$HOME/.config/librarian/config.yml" ]; then
    mkdir -p "$HOME/.config/librarian"
    cat > "$HOME/.config/librarian/config.yml" << 'LIBRARIAN_EOF'
# Librarian Configuration
github_token: ${GITHUB_TOKEN}
embedding_model: local
concurrency: 5
cache_ttl: 86400

# Default sources (customize per project in .librarian/libraries.yml)
default_sources: []
LIBRARIAN_EOF
    echo "✓ Librarian config created"
fi

# Create project-specific Librarian sources
if [ ! -f "/workspace/.librarian/libraries.yml" ]; then
    mkdir -p /workspace/.librarian
    cat > /workspace/.librarian/libraries.yml << 'LIBS_EOF'
# Project Documentation Sources
sources:
  # Claude Code
  - url: https://github.com/anthropics/claude-code
    docs: docs
    ref: main

  # Anthropic SDK (TypeScript)
  - url: https://github.com/anthropics/anthropic-sdk-typescript
    docs: .
    ref: main

  # Add your project's framework docs here
  # Example for Next.js:
  # - url: https://github.com/vercel/next.js
  #   docs: docs
  #   version: 15.x
LIBS_EOF
    echo "✓ Project Librarian sources created"
fi

# Verify installations
echo ""
echo "=== Verification ==="
echo "Node: $(node --version)"
echo "npm: $(npm --version)"
echo "Bun: $(bun --version 2>/dev/null || echo 'not found')"
echo "Git: $(git --version)"
command -v claude &> /dev/null && echo "Claude: $(claude --version 2>/dev/null || echo 'installed')" || echo "Claude: not found"
command -v librarian &> /dev/null && echo "Librarian: installed" || echo "Librarian: check PATH"

echo ""
echo "=== Post-Create Complete ==="
echo ""
echo "Next steps:"
echo "1. Run: librarian setup       # Initialize embedding model"
echo "2. Run: librarian seed        # Ingest documentation sources"
echo "3. Edit plans/prd.json        # Define your tasks"
echo "4. Run: ./plans/ralph.sh 10   # Start autonomous loop"
