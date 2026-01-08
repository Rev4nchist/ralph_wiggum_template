# Taskmaster Skill

## Trigger Patterns
- New project PRD document received
- "parse requirements", "break down tasks", "create subtasks"
- PRD file detected: `*.prd.md`, `prd.txt`, `requirements.md`
- User provides feature specification

## Purpose
Convert high-level PRDs into executable subtasks with dependencies.

## Prerequisites
- `task-master` CLI installed globally (`npm i -g task-master-ai`)
- `.taskmaster-template/` config in project or home directory
- `scripts/generate-prd.sh` available for format conversion

## Workflow

### 1. Initialize Taskmaster (if needed)
```bash
# Check if .taskmaster exists
ls .taskmaster/ 2>/dev/null || task-master init -y
```

### 2. Prepare PRD Document
```yaml
Location: .taskmaster/docs/prd.txt
Format: Plain text or markdown

Required Sections:
- Project Overview
- Goals/Objectives
- Features/Requirements
- Technical Constraints
- Acceptance Criteria (optional but recommended)
```

### 3. Parse PRD to Tasks
```bash
task-master parse-prd \
  --input .taskmaster/docs/prd.txt \
  --num-tasks 10 \
  --model claude-3-sonnet-20240229

# Output: .taskmaster/tasks/tasks.json
```

### 4. Convert to Ralph Format
```bash
./scripts/generate-prd.sh . --from-taskmaster

# Output: plans/prd.json
```

## Task Structure

### Taskmaster Format (.taskmaster/tasks/tasks.json)
```json
{
  "tasks": [
    {
      "id": 1,
      "title": "Set up project structure",
      "description": "Initialize monorepo...",
      "status": "pending",
      "dependencies": [],
      "priority": "high",
      "details": "..."
    }
  ]
}
```

### Ralph Format (plans/prd.json)
```json
{
  "project": "feature-name",
  "tasks": [
    {
      "id": "ARCH-001",
      "title": "Set up project structure",
      "description": "Initialize monorepo...",
      "type": "architecture",
      "agent": "architect",
      "deps": [],
      "files": ["package.json", "tsconfig.json"],
      "acceptance_criteria": ["Monorepo builds", "All packages link"],
      "passes": false
    }
  ]
}
```

## Dependency Mapping

### Auto-Detection Rules
```yaml
Architecture tasks: No dependencies (always first)
Backend tasks: Depend on architecture
Frontend tasks: Depend on architecture, may depend on backend APIs
Integration tasks: Depend on both frontend and backend
QA tasks: Depend on implementation tasks they test
Docs tasks: Depend on implementation being complete
```

### Manual Override
If auto-detection is wrong, edit `plans/prd.json` directly:
```json
{
  "id": "FE-002",
  "deps": ["BE-001", "FE-001"]  // Explicit dependencies
}
```

## Commands Reference

### task-master CLI
```bash
# Initialize
task-master init -y

# Parse PRD (recommended: 8-15 tasks for features)
task-master parse-prd --input <file> --num-tasks <n>

# List tasks
task-master list

# Show task details
task-master show <task-id>

# Update task status
task-master update <task-id> --status done

# Add subtask
task-master add-subtask --parent <id> --title "Subtask"
```

### generate-prd.sh Flags
```bash
./scripts/generate-prd.sh <project-dir> [options]

Options:
  --from-taskmaster    Convert .taskmaster/tasks/tasks.json
  --from-prd <file>    Parse new PRD file first
  --validate           Validate existing prd.json
  --dry-run            Show output without writing
```

## Quality Gates

### Before Parsing
- [ ] PRD has clear objectives
- [ ] Requirements are specific enough
- [ ] Technical constraints documented
- [ ] Acceptance criteria defined

### After Parsing
- [ ] Tasks are atomic (single responsibility)
- [ ] Dependencies form valid DAG (no cycles)
- [ ] Agent types correctly assigned
- [ ] Files to modify identified
- [ ] ~8-15 tasks for medium features

## Error Handling

### Parse Failures
```yaml
Error: "PRD too vague"
Fix: Add specific requirements, examples, constraints

Error: "Circular dependency detected"
Fix: Review task order, break cycles manually

Error: "Task too large"
Fix: Run with higher --num-tasks, split manually
```

### Integration Issues
```yaml
Error: "generate-prd.sh not found"
Fix: Check scripts/ directory, ensure executable

Error: "Invalid tasks.json format"
Fix: Validate JSON, check task-master version
```

## Example Session

```
User: "Parse this PRD for the authentication feature"

1. Copy PRD to .taskmaster/docs/prd.txt

2. task-master parse-prd --input .taskmaster/docs/prd.txt --num-tasks 8
   Output: Created 8 tasks in .taskmaster/tasks/tasks.json

3. ./scripts/generate-prd.sh . --from-taskmaster
   Output: Generated plans/prd.json with:
   - AUTH-001: Set up auth database schema (backend)
   - AUTH-002: Implement JWT service (backend)
   - AUTH-003: Create login API endpoints (backend)
   - AUTH-004: Build login form component (frontend)
   - AUTH-005: Add protected route wrapper (frontend)
   - AUTH-006: Implement auth context (frontend)
   - AUTH-007: Write auth API tests (qa)
   - AUTH-008: Write login E2E tests (qa)

4. Hand off to Orchestrator:
   "PRD parsed. 8 tasks ready in plans/prd.json. Execute orchestration."
```

## Integration with Orchestrator

After taskmaster completes:
1. Orchestrator loads `plans/prd.json`
2. Builds dependency graph
3. Creates execution waves
4. Spawns agents per wave
5. Tracks completion status

Taskmaster does NOT spawn agents - it only prepares the task list.
