#!/bin/bash
set -e

echo "Initializing firewall rules..."

# Preserve Docker DNS rules
DOCKER_DNS_RULES=$(iptables-save | grep -E "DOCKER|172\.17\." || true)

# Flush existing rules
iptables -F
iptables -X
ipset destroy 2>/dev/null || true

# Set default policies
iptables -P INPUT ACCEPT
iptables -P FORWARD DROP
iptables -P OUTPUT DROP

# Allow loopback
iptables -A OUTPUT -o lo -j ACCEPT

# Allow established connections
iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Allow DNS (required for domain resolution)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Allow SSH (for git operations)
iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT

# Create ipset for allowed domains
ipset create allowed_hosts hash:ip 2>/dev/null || ipset flush allowed_hosts

# Whitelist: Anthropic API
for ip in $(dig +short api.anthropic.com); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Whitelist: GitHub (for git, packages)
GITHUB_META=$(curl -s https://api.github.com/meta 2>/dev/null || echo '{}')
for range in $(echo "$GITHUB_META" | jq -r '.web[]?, .api[]?, .git[]?' 2>/dev/null | head -50 | sort -u); do
    ipset add allowed_hosts $range 2>/dev/null || true
done

# Whitelist: npm registry
for ip in $(dig +short registry.npmjs.org); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Whitelist: PyPI (for Python packages)
for ip in $(dig +short pypi.org files.pythonhosted.org); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Whitelist: Statsig (Claude Code telemetry)
for ip in $(dig +short statsigapi.net api.statsig.com); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Whitelist: Sentry (error reporting)
for ip in $(dig +short sentry.io); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Whitelist: Telegram API (for notifications)
for ip in $(dig +short api.telegram.org); do
    ipset add allowed_hosts $ip 2>/dev/null || true
done

# Allow traffic to whitelisted IPs
iptables -A OUTPUT -m set --match-set allowed_hosts dst -j ACCEPT

# Allow HTTPS to whitelisted hosts
iptables -A OUTPUT -p tcp --dport 443 -m set --match-set allowed_hosts dst -j ACCEPT
iptables -A OUTPUT -p tcp --dport 80 -m set --match-set allowed_hosts dst -j ACCEPT

# Restore Docker DNS rules if they existed
if [ -n "$DOCKER_DNS_RULES" ]; then
    echo "$DOCKER_DNS_RULES" | iptables-restore -n 2>/dev/null || true
fi

# Log dropped packets (for debugging)
iptables -A OUTPUT -j LOG --log-prefix "BLOCKED: " --log-level 4

echo "Firewall initialized. Allowed domains:"
echo "  - api.anthropic.com (Claude API)"
echo "  - github.com (Git operations)"
echo "  - registry.npmjs.org (npm packages)"
echo "  - pypi.org (Python packages)"
echo "  - statsigapi.net (telemetry)"
echo "  - sentry.io (error reporting)"
echo "  - api.telegram.org (notifications)"
