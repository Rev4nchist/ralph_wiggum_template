"""Tests for Project Memory System - Agent memory persistence and coordination."""

import json
import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from lib.memory.memory_protocol import (
    Memory, MemoryQuery, MemoryCategory, MemoryScope, MemoryProtocol
)
from lib.memory.project_memory import ProjectMemory


class TestMemory:
    """Tests for Memory dataclass."""

    def test_create_memory(self):
        memory = Memory(
            id="mem-123",
            content="Test content",
            category="learning",
            scope="project",
            project_id="proj-1"
        )
        assert memory.id == "mem-123"
        assert memory.content == "Test content"
        assert memory.category == "learning"
        assert memory.scope == "project"
        assert memory.project_id == "proj-1"

    def test_memory_defaults(self):
        memory = Memory(
            id="mem-123",
            content="Test",
            category="learning",
            scope="project",
            project_id="proj-1"
        )
        assert memory.agent_id is None
        assert memory.task_id is None
        assert memory.tags == []
        assert memory.metadata == {}
        assert memory.relevance_score == 0.0

    def test_memory_with_all_fields(self):
        memory = Memory(
            id="mem-456",
            content="Full memory",
            category="architecture",
            scope="task",
            project_id="proj-2",
            agent_id="agent-1",
            task_id="task-1",
            tags=["api", "design"],
            metadata={"importance": "high"},
            relevance_score=0.95
        )
        assert memory.agent_id == "agent-1"
        assert memory.task_id == "task-1"
        assert memory.tags == ["api", "design"]
        assert memory.metadata == {"importance": "high"}
        assert memory.relevance_score == 0.95


class TestMemoryQuery:
    """Tests for MemoryQuery dataclass."""

    def test_create_query(self):
        query = MemoryQuery(
            query="architecture decisions",
            project_id="proj-1"
        )
        assert query.query == "architecture decisions"
        assert query.project_id == "proj-1"
        assert query.limit == 10

    def test_query_with_filters(self):
        query = MemoryQuery(
            query="patterns",
            project_id="proj-1",
            category="pattern",
            scope="project",
            task_id="task-1",
            tags=["api"],
            limit=5,
            min_relevance=0.7
        )
        assert query.category == "pattern"
        assert query.scope == "project"
        assert query.task_id == "task-1"
        assert query.tags == ["api"]
        assert query.limit == 5
        assert query.min_relevance == 0.7


class TestMemoryEnums:
    """Tests for memory enums."""

    def test_memory_category_values(self):
        expected = [
            "architecture", "pattern", "decision", "blocker",
            "learning", "context", "handoff", "quality"
        ]
        actual = [c.value for c in MemoryCategory]
        assert set(expected) == set(actual)

    def test_memory_scope_values(self):
        expected = ["project", "task", "agent"]
        actual = [s.value for s in MemoryScope]
        assert set(expected) == set(actual)


class TestMemoryProtocol:
    """Tests for MemoryProtocol class constants."""

    def test_triggers_defined(self):
        assert "task_start" in MemoryProtocol.TRIGGERS
        assert "implementation" in MemoryProtocol.TRIGGERS
        assert "task_complete" in MemoryProtocol.TRIGGERS
        assert "blocked" in MemoryProtocol.TRIGGERS

    def test_categories_defined(self):
        expected_categories = [
            "architecture", "pattern", "decision", "blocker",
            "learning", "context", "handoff", "quality"
        ]
        for cat in expected_categories:
            assert cat in MemoryProtocol.CATEGORIES

    def test_standard_tags_defined(self):
        assert "frontend" in MemoryProtocol.STANDARD_TAGS
        assert "backend" in MemoryProtocol.STANDARD_TAGS
        assert "testing" in MemoryProtocol.STANDARD_TAGS


class TestProjectMemory:
    """Tests for ProjectMemory class."""

    @pytest.fixture
    def memory(self):
        return ProjectMemory(project_id="test-project", agent_id="test-agent")

    @pytest.fixture
    def mock_redis(self):
        return MagicMock()

    @pytest.fixture
    def memory_with_redis(self, mock_redis):
        return ProjectMemory(
            project_id="test-project",
            agent_id="test-agent",
            redis_client=mock_redis
        )

    def test_init_defaults(self):
        memory = ProjectMemory(project_id="proj-1")
        assert memory.project_id == "proj-1"
        assert memory.redis is None

    def test_init_with_agent_id(self):
        memory = ProjectMemory(project_id="proj-1", agent_id="agent-1")
        assert memory.agent_id == "agent-1"


class TestClaudeMemCmd:
    """Tests for _claude_mem_cmd method."""

    @pytest.fixture
    def memory(self):
        return ProjectMemory(project_id="test-project", agent_id="test-agent")

    @patch('lib.memory.project_memory.subprocess.run')
    def test_store_success(self, mock_run, memory):
        mock_run.return_value = MagicMock(returncode=0)

        result = memory._claude_mem_cmd("store", {
            "content": "test content",
            "tags": ["tag1", "tag2"]
        })

        assert result == {"success": True}
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "store" in cmd
        assert "--content" in cmd
        assert "test content" in cmd

    @patch('lib.memory.project_memory.subprocess.run')
    def test_store_failure(self, mock_run, memory):
        mock_run.return_value = MagicMock(returncode=1)

        result = memory._claude_mem_cmd("store", {
            "content": "test content",
            "tags": []
        })

        assert result == {"success": False}

    @patch('lib.memory.project_memory.subprocess.run')
    def test_search_success(self, mock_run, memory):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"results": [{"id": "1", "content": "test"}]}'
        )

        result = memory._claude_mem_cmd("search", {
            "query": "test query",
            "limit": 5
        })

        assert result is not None
        assert "results" in result
        assert len(result["results"]) == 1

    @patch('lib.memory.project_memory.subprocess.run')
    def test_search_empty_results(self, mock_run, memory):
        mock_run.return_value = MagicMock(returncode=0, stdout='')

        result = memory._claude_mem_cmd("search", {
            "query": "test",
            "limit": 10
        })

        assert result == {"results": []}

    @patch('lib.memory.project_memory.subprocess.run')
    def test_command_timeout(self, mock_run, memory):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=30)

        result = memory._claude_mem_cmd("store", {"content": "test", "tags": []})

        assert result is None

    @patch('lib.memory.project_memory.subprocess.run')
    def test_command_exception(self, mock_run, memory):
        mock_run.side_effect = Exception("Command failed")

        result = memory._claude_mem_cmd("store", {"content": "test", "tags": []})

        assert result is None


class TestRemember:
    """Tests for remember method."""

    @pytest.fixture
    def mock_redis(self):
        return MagicMock()

    @pytest.fixture
    def memory_with_redis(self, mock_redis):
        return ProjectMemory(
            project_id="test-project",
            agent_id="test-agent",
            redis_client=mock_redis
        )

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_remember_returns_id(self, mock_cmd, memory_with_redis):
        mock_cmd.return_value = {"success": True}

        memory_id = memory_with_redis.remember("Test memory content")

        assert memory_id.startswith("mem-")
        assert len(memory_id) == 12

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_remember_stores_in_redis(self, mock_cmd, memory_with_redis, mock_redis):
        mock_cmd.return_value = {"success": True}

        memory_id = memory_with_redis.remember(
            content="Test content",
            category="learning",
            scope="project"
        )

        mock_redis.hset.assert_called_once()
        call_args = mock_redis.hset.call_args
        assert call_args[0][0] == "ralph:memory:test-project"
        assert call_args[0][1] == memory_id

        stored_data = json.loads(call_args[0][2])
        assert stored_data["content"] == "Test content"
        assert stored_data["category"] == "learning"
        assert stored_data["scope"] == "project"

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_remember_builds_tags(self, mock_cmd, memory_with_redis):
        mock_cmd.return_value = {"success": True}

        memory_with_redis.remember(
            content="Test",
            category="architecture",
            scope="task",
            tags=["custom-tag"],
            task_id="task-123"
        )

        call_args = mock_cmd.call_args
        tags = call_args[0][1]["tags"]
        assert "project:test-project" in tags
        assert "category:architecture" in tags
        assert "scope:task" in tags
        assert "agent:test-agent" in tags
        assert "custom-tag" in tags
        assert "task:task-123" in tags


class TestRecall:
    """Tests for recall method."""

    @pytest.fixture
    def memory(self):
        return ProjectMemory(project_id="test-project", agent_id="test-agent")

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_recall_returns_memories(self, mock_cmd, memory):
        mock_cmd.return_value = {
            "results": [
                {"id": "1", "content": "Memory 1", "score": 0.9},
                {"id": "2", "content": "Memory 2", "score": 0.8}
            ]
        }

        memories = memory.recall("test query")

        assert len(memories) == 2
        assert all(isinstance(m, Memory) for m in memories)

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_recall_with_filters(self, mock_cmd, memory):
        mock_cmd.return_value = {"results": []}

        memory.recall(
            query="patterns",
            category="pattern",
            task_id="task-123",
            limit=5
        )

        call_args = mock_cmd.call_args
        search_data = call_args[0][1]
        assert "project:test-project" in search_data["query"]
        assert "category:pattern" in search_data["query"]
        assert "task:task-123" in search_data["query"]
        assert search_data["limit"] == 5

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_recall_empty_results(self, mock_cmd, memory):
        mock_cmd.return_value = {"results": []}

        memories = memory.recall("nonexistent")

        assert memories == []

    @patch.object(ProjectMemory, '_claude_mem_cmd')
    def test_recall_handles_none_response(self, mock_cmd, memory):
        mock_cmd.return_value = None

        memories = memory.recall("test")

        assert memories == []


class TestSpecializedMemories:
    """Tests for specialized memory methods."""

    @pytest.fixture
    def memory(self):
        return ProjectMemory(project_id="test-project", agent_id="test-agent")

    @patch.object(ProjectMemory, 'remember')
    def test_note_architecture(self, mock_remember, memory):
        mock_remember.return_value = "mem-123"

        result = memory.note_architecture(
            decision="Use event sourcing",
            rationale="Better audit trail",
            alternatives=["CRUD", "Document store"]
        )

        assert result == "mem-123"
        call_args = mock_remember.call_args
        assert "DECISION: Use event sourcing" in call_args[1]["content"]
        assert "RATIONALE: Better audit trail" in call_args[1]["content"]
        assert "CRUD" in call_args[1]["content"]
        assert call_args[1]["category"] == "architecture"

    @patch.object(ProjectMemory, 'remember')
    def test_note_pattern(self, mock_remember, memory):
        mock_remember.return_value = "mem-456"

        result = memory.note_pattern(
            pattern_name="Repository pattern",
            description="Abstracts data access",
            example="class UserRepo: ..."
        )

        assert result == "mem-456"
        call_args = mock_remember.call_args
        assert "PATTERN: Repository pattern" in call_args[1]["content"]
        assert "Abstracts data access" in call_args[1]["content"]
        assert "class UserRepo" in call_args[1]["content"]
        assert call_args[1]["category"] == "pattern"

    @patch.object(ProjectMemory, 'remember')
    def test_note_blocker_with_solution(self, mock_remember, memory):
        mock_remember.return_value = "mem-789"

        result = memory.note_blocker(
            problem="Import circular dependency",
            solution="Move shared types to separate module",
            attempts=["Lazy imports", "Type checking imports"]
        )

        call_args = mock_remember.call_args
        assert "PROBLEM: Import circular dependency" in call_args[1]["content"]
        assert "SOLUTION: Move shared types" in call_args[1]["content"]
        assert "Lazy imports" in call_args[1]["content"]
        assert call_args[1]["category"] == "blocker"

    @patch.object(ProjectMemory, 'remember')
    def test_note_blocker_unresolved(self, mock_remember, memory):
        mock_remember.return_value = "mem-000"

        memory.note_blocker(problem="Unknown error")

        call_args = mock_remember.call_args
        assert "STATUS: Unresolved" in call_args[1]["content"]

    @patch.object(ProjectMemory, 'remember')
    def test_handoff(self, mock_remember, memory):
        mock_remember.return_value = "mem-abc"

        result = memory.handoff(
            task_id="task-123",
            summary="Completed API endpoints",
            next_steps=["Add validation", "Write tests"],
            notes="Check auth middleware"
        )

        call_args = mock_remember.call_args
        assert "HANDOFF FOR TASK: task-123" in call_args[1]["content"]
        assert "Completed API endpoints" in call_args[1]["content"]
        assert "Add validation" in call_args[1]["content"]
        assert "Check auth middleware" in call_args[1]["content"]
        assert call_args[1]["category"] == "handoff"
        assert call_args[1]["task_id"] == "task-123"

    @patch.object(ProjectMemory, 'remember')
    def test_commit_task(self, mock_remember, memory):
        mock_remember.return_value = "mem-xyz"

        result = memory.commit_task(
            task_id="task-456",
            summary="Implemented user auth",
            learnings=["JWT works well", "Need to handle refresh tokens"],
            artifacts=["src/auth.py", "tests/test_auth.py"],
            quality_notes="All tests pass"
        )

        call_args = mock_remember.call_args
        assert "TASK COMPLETED: task-456" in call_args[1]["content"]
        assert "Implemented user auth" in call_args[1]["content"]
        assert "JWT works well" in call_args[1]["content"]
        assert "src/auth.py" in call_args[1]["content"]
        assert "All tests pass" in call_args[1]["content"]
        assert call_args[1]["category"] == "learning"


class TestContextMethods:
    """Tests for context retrieval methods."""

    @pytest.fixture
    def memory(self):
        return ProjectMemory(project_id="test-project", agent_id="test-agent")

    @patch.object(ProjectMemory, 'recall')
    def test_get_project_context_with_memories(self, mock_recall, memory):
        mock_recall.return_value = [
            Memory(
                id="1",
                content="Architecture decision",
                category="architecture",
                scope="project",
                project_id="test-project"
            ),
            Memory(
                id="2",
                content="Code pattern",
                category="pattern",
                scope="project",
                project_id="test-project"
            )
        ]

        context = memory.get_project_context()

        assert "## Project Memory Context" in context
        assert "### ARCHITECTURE" in context
        assert "Architecture decision" in context
        assert "### PATTERN" in context
        assert "Code pattern" in context

    @patch.object(ProjectMemory, 'recall')
    def test_get_project_context_empty(self, mock_recall, memory):
        mock_recall.return_value = []

        context = memory.get_project_context()

        assert "No project memories found" in context

    @patch.object(ProjectMemory, 'recall')
    def test_get_task_context_with_memories(self, mock_recall, memory):
        mock_recall.return_value = [
            Memory(
                id="1",
                content="Handoff notes from previous agent",
                category="handoff",
                scope="task",
                project_id="test-project",
                task_id="task-123"
            )
        ]

        context = memory.get_task_context("task-123")

        assert "## Context for Task task-123" in context
        assert "Handoff notes" in context

    @patch.object(ProjectMemory, 'recall')
    def test_get_task_context_empty(self, mock_recall, memory):
        mock_recall.return_value = []

        context = memory.get_task_context("task-999")

        assert "No previous context for task task-999" in context
