#!/usr/bin/env python3
"""Security Scan Hook - Detect secrets and vulnerabilities

Scans staged files for:
- API keys and tokens
- Private keys
- Passwords in config
- AWS credentials
- Database connection strings
"""

import re
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

SECRET_PATTERNS = [
    (r'(?i)(api[_-]?key|apikey)\s*[=:]\s*["\']?[\w-]{20,}', "API Key"),
    (r'(?i)(secret[_-]?key|secretkey)\s*[=:]\s*["\']?[\w-]{20,}', "Secret Key"),
    (r'(?i)(password|passwd|pwd)\s*[=:]\s*["\']?.{8,}["\']?', "Password"),
    (r'(?i)bearer\s+[\w-]{20,}', "Bearer Token"),
    (r'sk-[a-zA-Z0-9]{20,}', "Stripe/OpenAI Key"),
    (r'sk-ant-[a-zA-Z0-9-]{50,}', "Anthropic API Key"),
    (r'sk-or-v1-[a-zA-Z0-9]{50,}', "OpenRouter API Key"),
    (r'ghp_[a-zA-Z0-9]{36}', "GitHub Personal Token"),
    (r'gho_[a-zA-Z0-9]{36}', "GitHub OAuth Token"),
    (r'AKIA[0-9A-Z]{16}', "AWS Access Key"),
    (r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[=:]\s*[\w/+]{40}', "AWS Secret Key"),
    (r'-----BEGIN (RSA |DSA |EC )?PRIVATE KEY-----', "Private Key"),
    (r'(?i)(mongodb|postgres|mysql|redis)://[^\s]+:[^\s]+@', "Database URL with credentials"),
    (r'eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', "JWT Token"),
    (r'xox[baprs]-[a-zA-Z0-9-]+', "Slack Token"),
]

IGNORE_PATTERNS = [
    r'\.env\.example$',
    r'\.env\.sample$',
    r'\.env\.template$',
    r'test.*\.py$',
    r'.*_test\.py$',
    r'mock.*\.py$',
    r'\.md$',
]


def get_staged_files() -> List[str]:
    """Get list of staged files."""
    try:
        result = subprocess.run(
            ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            capture_output=True,
            text=True
        )
        return [f for f in result.stdout.strip().split('\n') if f]
    except Exception:
        return []


def should_scan(file_path: str) -> bool:
    """Check if file should be scanned."""
    for pattern in IGNORE_PATTERNS:
        if re.search(pattern, file_path):
            return False
    return True


def scan_file(file_path: str) -> List[Tuple[int, str, str]]:
    """Scan file for secrets. Returns list of (line_num, matched_text, secret_type)."""
    findings = []

    try:
        path = Path(file_path)
        if not path.exists():
            return findings

        if path.stat().st_size > 1_000_000:
            return findings

        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                for pattern, secret_type in SECRET_PATTERNS:
                    matches = re.findall(pattern, line)
                    if matches:
                        masked = line.strip()[:50] + "..."
                        findings.append((line_num, masked, secret_type))
                        break

    except Exception as e:
        print(f"Error scanning {file_path}: {e}", file=sys.stderr)

    return findings


def main() -> int:
    """Run security scan on staged files."""
    files = get_staged_files()

    if not files:
        print("No staged files to scan")
        return 0

    all_findings = []

    for file_path in files:
        if not should_scan(file_path):
            continue

        findings = scan_file(file_path)
        if findings:
            all_findings.extend([(file_path, *f) for f in findings])

    if all_findings:
        print("\n🚨 SECURITY SCAN FAILED - Potential secrets detected:\n")
        for file_path, line_num, text, secret_type in all_findings:
            print(f"  {file_path}:{line_num}")
            print(f"    Type: {secret_type}")
            print(f"    Content: {text}\n")

        print("\nTo fix:")
        print("  1. Remove secrets from code")
        print("  2. Use environment variables instead")
        print("  3. Add to .gitignore if config file")
        print("\nTo bypass (not recommended):")
        print("  git commit --no-verify")

        return 1

    print("✅ Security scan passed - no secrets detected")
    return 0


if __name__ == "__main__":
    sys.exit(main())
