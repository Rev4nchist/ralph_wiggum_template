FROM node:20-bookworm

ARG CLAUDE_CODE_VERSION=latest
ARG USERNAME=node

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    wget \
    vim \
    jq \
    fzf \
    ripgrep \
    iptables \
    ipset \
    dnsutils \
    sudo \
    python3 \
    python3-pip \
    python3-venv \
    tmux \
    && rm -rf /var/lib/apt/lists/*

# Set up command history persistence
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    && mkdir -p /commandhistory \
    && touch /commandhistory/.bash_history \
    && chown -R ${USERNAME} /commandhistory \
    && echo "$SNIPPET" >> "/home/${USERNAME}/.bashrc" \
    && echo "$SNIPPET" >> "/home/${USERNAME}/.zshrc"

# Install Claude Code globally (as root)
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# Copy and set up firewall script
COPY init-firewall.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/init-firewall.sh && \
    echo "${USERNAME} ALL=(root) NOPASSWD: /usr/local/bin/init-firewall.sh" > /etc/sudoers.d/node-firewall && \
    chmod 0440 /etc/sudoers.d/node-firewall

# Create directories for plugins and data (as root first)
RUN mkdir -p /home/${USERNAME}/.claude/plugins \
    && mkdir -p /home/${USERNAME}/.claude-mem \
    && mkdir -p /home/${USERNAME}/.librarian \
    && mkdir -p /home/${USERNAME}/.config/librarian \
    && chown -R ${USERNAME}:${USERNAME} /home/${USERNAME}

# Switch to node user for user-specific installations
USER ${USERNAME}
WORKDIR /home/${USERNAME}

# Install Bun (as node user - FIXED from original guide)
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/home/${USERNAME}/.bun/bin:${PATH}"

# Install uv (Python package manager - as node user)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/home/${USERNAME}/.local/bin:${PATH}"

# Set working directory
WORKDIR /workspace
