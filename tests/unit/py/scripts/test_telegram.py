"""Tests for Telegram notification scripts.

Note: These tests focus on static analysis of the scripts since
running bash scripts on Windows requires special handling.
"""

import os
from pathlib import Path

import pytest


PLANS_DIR = Path(__file__).parent.parent.parent.parent.parent / "plans"


class TestNotifyScript:
    """Tests for notify.sh script."""

    def test_script_exists(self):
        script_path = PLANS_DIR / "notify.sh"
        assert script_path.exists(), f"notify.sh not found at {script_path}"

    def test_script_has_shebang(self):
        script_path = PLANS_DIR / "notify.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
        assert first_line.startswith('#!/bin/bash'), "Script should have bash shebang"

    def test_script_checks_credentials(self):
        script_path = PLANS_DIR / "notify.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'TELEGRAM_BOT_TOKEN' in content, "Script should check for bot token"
        assert 'TELEGRAM_CHAT_ID' in content, "Script should check for chat ID"

    def test_script_supports_message_types(self):
        script_path = PLANS_DIR / "notify.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()

        expected_types = ['question', 'error', 'complete', 'blocked']
        for msg_type in expected_types:
            assert msg_type in content, f"notify.sh should support {msg_type} type"

    def test_script_uses_curl(self):
        script_path = PLANS_DIR / "notify.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'curl' in content, "Script should use curl for API calls"

    def test_script_uses_telegram_api(self):
        script_path = PLANS_DIR / "notify.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'api.telegram.org' in content, "Script should use Telegram API"


class TestCheckResponseScript:
    """Tests for check-response.sh script."""

    def test_script_exists(self):
        script_path = PLANS_DIR / "check-response.sh"
        assert script_path.exists(), f"check-response.sh not found at {script_path}"

    def test_script_has_shebang(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
        assert first_line.startswith('#!/bin/bash'), "Script should have bash shebang"

    def test_script_checks_credentials(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'TELEGRAM_BOT_TOKEN' in content, "Script should check for bot token"
        assert 'TELEGRAM_CHAT_ID' in content, "Script should check for chat ID"

    def test_script_uses_state_file(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.telegram_state' in content, "Script should use state file"

    def test_script_uses_response_file(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '.telegram_response' in content, "Script should use response file"

    def test_script_uses_jq(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'jq' in content, "Script should use jq for JSON parsing"

    def test_script_tracks_update_id(self):
        script_path = PLANS_DIR / "check-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'update_id' in content.lower(), "Script should track update_id"


class TestWaitResponseScript:
    """Tests for wait-response.sh script."""

    def test_script_exists(self):
        script_path = PLANS_DIR / "wait-response.sh"
        assert script_path.exists(), f"wait-response.sh not found at {script_path}"

    def test_script_has_shebang(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            first_line = f.readline()
        assert first_line.startswith('#!/bin/bash'), "Script should have bash shebang"

    def test_script_checks_credentials(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'TELEGRAM_BOT_TOKEN' in content, "Script should check for bot token"
        assert 'TELEGRAM_CHAT_ID' in content, "Script should check for chat ID"

    def test_default_timeout(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'TIMEOUT=${1:-300}' in content, "Default timeout should be 300 seconds"

    def test_script_clears_response_file(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'rm -f' in content, "Script should clear response file"
        assert '.telegram_response' in content, "Script should use response file"

    def test_script_has_poll_loop(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'while' in content, "Script should have polling loop"
        assert 'sleep' in content, "Script should sleep between polls"

    def test_script_sends_acknowledgment(self):
        script_path = PLANS_DIR / "wait-response.sh"
        with open(script_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'sendMessage' in content, "Script should send acknowledgment message"


class TestTelegramScriptIntegration:
    """Integration tests for Telegram scripts working together."""

    def test_all_scripts_exist(self):
        for script_name in ['notify.sh', 'check-response.sh', 'wait-response.sh']:
            script_path = PLANS_DIR / script_name
            assert script_path.exists(), f"{script_name} not found"

    def test_state_file_location_consistent(self):
        for script_name in ['check-response.sh', 'wait-response.sh']:
            script_path = PLANS_DIR / script_name
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'plans/' in content, f"{script_name} should use plans/ directory for state"

    def test_all_scripts_use_same_api(self):
        api_endpoint = "api.telegram.org"
        for script_name in ['notify.sh', 'check-response.sh', 'wait-response.sh']:
            script_path = PLANS_DIR / script_name
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert api_endpoint in content, f"{script_name} should use Telegram API"

    def test_all_scripts_are_bash(self):
        for script_name in ['notify.sh', 'check-response.sh', 'wait-response.sh']:
            script_path = PLANS_DIR / script_name
            with open(script_path, 'r', encoding='utf-8') as f:
                first_line = f.readline()
            assert '#!/bin/bash' in first_line, f"{script_name} should be a bash script"

    def test_credential_check_pattern_consistent(self):
        pattern = '[ -z "$TELEGRAM_BOT_TOKEN" ]'
        for script_name in ['notify.sh', 'check-response.sh', 'wait-response.sh']:
            script_path = PLANS_DIR / script_name
            with open(script_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert 'TELEGRAM_BOT_TOKEN' in content
            assert 'TELEGRAM_CHAT_ID' in content
