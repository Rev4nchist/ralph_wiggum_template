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

## Librarian Documentation Search

### When to Use Librarian
Use Librarian MCP tools BEFORE implementing code when:
- Working with external libraries (React, Prisma, Zod, etc.)
- Encountering unfamiliar APIs or patterns
- Debugging errors related to third-party code
- Implementing integrations with documented systems

### Available MCP Tools

| Tool | Purpose | Required Args |
|------|---------|---------------|
| `librarian_find_library` | Find library ID for searching | `name` (e.g., "react") |
| `librarian_search` | General documentation search | `query`, `library` |
| `librarian_search_api` | Find API/function docs | `api_name`, `library` |
| `librarian_search_error` | Find error solutions | `error_message` |
| `librarian_list_sources` | List indexed libraries | none |
| `librarian_get_document` | Get full document | `library`, `doc_id`, `slice` |

### Search Modes
- `hybrid` (default): Combines keyword + semantic search
- `word`: Fast keyword-based (BM25) search
- `vector`: Semantic similarity search

### Usage Examples

```yaml
# Step 1: Find the library ID first
librarian_find_library:
  name: "react"
# Returns: reactjs/react.dev

# Step 2: Search documentation
librarian_search:
  query: "useState useEffect custom hooks"
  library: "reactjs/react.dev"
  mode: "hybrid"

# When encountering an error
librarian_search_error:
  error_message: "Cannot read property 'map' of undefined"
  library: "reactjs/react.dev"

# Looking up specific API
librarian_search_api:
  api_name: "useCallback"
  library: "reactjs/react.dev"

# Get full document content
librarian_get_document:
  library: "reactjs/react.dev"
  doc_id: "123"
  slice: "13:29"  # from search results
```

### Indexed Libraries
Use `librarian_list_sources` to see available libraries. Standard sources:
- `reactjs/react.dev` - React documentation
- `tailwindlabs/tailwindcss.com` - Tailwind CSS
- `vercel/next.js` - Next.js
- `prisma/docs` - Prisma ORM
- `colinhacks/zod` - Zod validation

### Best Practices
1. **Search first, code second** - Always check docs before implementing
2. **Use specific queries** - "useState array update" > "react state"
3. **Combine tools** - Use `librarian_search` then `librarian_get_document` for details
4. **Check for errors** - If stuck on an error, use `librarian_search_error`
5. **Verify current APIs** - Library docs may be more current than training data
