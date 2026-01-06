# Ralph Wiggum Test Project

## Environment

You are operating in a **Ralph Wiggum autonomous development loop** with:
- **Claude-Mem** for persistent memory across sessions
- **Librarian** for up-to-date documentation search
- **DevContainer** isolation for secure unattended operation
- **Telegram notifications** for human-in-the-loop communication

## Workflow Rules

### Before Coding
1. Check `plans/prd.json` for the current task
2. Read `plans/progress.txt` for context from previous iterations
3. Use Librarian to search documentation when uncertain about APIs

### While Coding
1. Follow the acceptance criteria exactly
2. Write tests alongside implementation
3. Use TypeScript strict mode where applicable
4. Commit frequently with descriptive messages

### After Each Task
1. Run tests: `npm test` or `bun test`
2. Run type check if applicable: `npm run typecheck`
3. Update PRD: set `"passes": true` for completed task
4. Update progress.txt with detailed notes
5. Git commit with conventional commit message

### Asking for Human Input
When you need human guidance, use the Telegram notification system:
```bash
./plans/notify.sh "question" "What approach should I use for X?"
```
Then check for response:
```bash
./plans/check-response.sh
```

## Completion Signals
- `<PROMISE>COMPLETE</PROMISE>` - All PRD tasks done
- `<PROMISE>BLOCKED</PROMISE>` - Cannot proceed, needs human input
- `<PROMISE>WAITING</PROMISE>` - Awaiting human response via Telegram

## Code Quality Standards
- TypeScript preferred
- Tests required for non-trivial logic
- No `any` types without justification
- Clear variable/function names
