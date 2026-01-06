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

# Set environment variables
export OPENROUTER_API_KEY="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"
export TELEGRAM_BOT_TOKEN="8352598115:AAFSsdNAx1tmbYMeWHYMExb1x60rAAZVPfk"
export TELEGRAM_CHAT_ID="6891749518"

# Add to shell profile for persistence
echo 'export OPENROUTER_API_KEY="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"' >> ~/.bashrc
echo 'export TELEGRAM_BOT_TOKEN="8352598115:AAFSsdNAx1tmbYMeWHYMExb1x60rAAZVPfk"' >> ~/.bashrc
echo 'export TELEGRAM_CHAT_ID="6891749518"' >> ~/.bashrc

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
