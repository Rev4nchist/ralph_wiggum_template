#!/bin/bash
# Setup OpenRouter with Claude Code Router for tiered model usage
# Run this inside the DevContainer

set -e

echo "=== Setting up OpenRouter + Claude Code Router ==="

# Install Claude Code Router
echo "Installing Claude Code Router..."
npm install -g @musistudio/claude-code-router 2>/dev/null || {
    echo "Trying with sudo..."
    sudo npm install -g @musistudio/claude-code-router
}

# Create config directory
mkdir -p ~/.claude-code-router

# Copy config from project
if [ -f "/workspaces/ralph-wiggum-test/.claude-code-router/config.json" ]; then
    cp /workspaces/ralph-wiggum-test/.claude-code-router/config.json ~/.claude-code-router/config.json
    echo "✓ Config copied to ~/.claude-code-router/"
fi

# Set environment variables (get these from your .env file or secrets manager)
# NEVER commit real secrets - these must be set from external source
if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY not set. Export it before running this script."
    exit 1
fi
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "ERROR: TELEGRAM_BOT_TOKEN not set. Export it before running this script."
    exit 1
fi
if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "ERROR: TELEGRAM_CHAT_ID not set. Export it before running this script."
    exit 1
fi

# Add to shell profile for persistence (references env vars, not hardcoded)
echo "export OPENROUTER_API_KEY=\"\$OPENROUTER_API_KEY\"" >> ~/.bashrc
echo "export TELEGRAM_BOT_TOKEN=\"\$TELEGRAM_BOT_TOKEN\"" >> ~/.bashrc
echo "export TELEGRAM_CHAT_ID=\"\$TELEGRAM_CHAT_ID\"" >> ~/.bashrc

echo ""
echo "=== Configuration ==="
echo "Model Routing:"
echo "  • Planning/Thinking: anthropic/claude-opus-4.5"
echo "  • Default Work:      z-ai/glm-4.7"
echo "  • Background/Long:   minimax/minimax-m2.1"
echo ""
echo "=== Usage ==="
echo "Instead of 'claude', use 'ccr code' to start Claude Code with routing"
echo ""
echo "To run Ralph with OpenRouter:"
echo "  ccr code -p \"\$(cat plans/ralph-prompt.txt)\""
echo ""
echo "=== Setup Complete ==="
