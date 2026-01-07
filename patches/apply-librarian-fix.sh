#!/bin/bash
# Apply Librarian Bun crash fixes
# Run this after: npm install -g @iannuttall/librarian

set -e

LIBRARIAN_PATH="${APPDATA}/npm/node_modules/@iannuttall/librarian/src"

if [ ! -d "$LIBRARIAN_PATH" ]; then
    echo "Error: Librarian not found at $LIBRARIAN_PATH"
    echo "Install first: npm install -g @iannuttall/librarian"
    exit 1
fi

echo "Applying Librarian Bun crash fixes..."

# Fix 1: embeddings.ts - DELETE before INSERT for vec0 tables
cat > "$LIBRARIAN_PATH/store/embeddings.ts" << 'EOF'
import type { Database } from "bun:sqlite";

export function markChunkEmbedded(db: Database, chunkId: number, model: string): void {
  const now = new Date().toISOString();
  db.prepare(
    "INSERT OR REPLACE INTO chunk_vectors (chunk_id, model, embedded_at) VALUES (?, ?, ?)"
  ).run(chunkId, model, now);
}

export function insertEmbedding(db: Database, chunkId: number, embedding: Float32Array, model: string): void {
  // vec0 virtual tables don't support INSERT OR REPLACE - must DELETE first then INSERT
  // See: https://github.com/asg017/sqlite-vec/issues/127
  try {
    db.prepare("DELETE FROM vectors_vec WHERE chunk_id = ?").run(chunkId);
    db.prepare("INSERT INTO vectors_vec (chunk_id, embedding) VALUES (?, ?)").run(chunkId, embedding);
  } catch (error) {
    // If insert fails (e.g., table doesn't exist yet), log and continue
    const message = error instanceof Error ? error.message : String(error);
    if (!message.includes("no such table")) {
      console.error(`Failed to insert embedding for chunk ${chunkId}: ${message}`);
    }
    throw error;
  }
  markChunkEmbedded(db, chunkId, model);
}

export function clearAllEmbeddings(db: Database): void {
  db.exec("DELETE FROM chunk_vectors");
  db.exec("DROP TABLE IF EXISTS vectors_vec");
}
EOF

echo "  ✓ Fixed embeddings.ts"

# Fix 2: Add disposeEmbedding to embed.ts - using sed to insert after modelUri line
if ! grep -q "disposeEmbedding" "$LIBRARIAN_PATH/llm/embed.ts"; then
    sed -i '/^let modelUri = DEFAULT_EMBED_MODEL;$/a\
\
// Cleanup function to properly dispose llama resources before exit\
// Prevents segfault in llama-addon.node during Bun shutdown\
export async function disposeEmbedding(): Promise<void> {\
  if (embedContext) {\
    try {\
      await embedContext.dispose();\
    } catch { /* ignore cleanup errors */ }\
    embedContext = null;\
  }\
  if (embedModel) {\
    try {\
      await embedModel.dispose();\
    } catch { /* ignore cleanup errors */ }\
    embedModel = null;\
  }\
  if (llamaInstance) {\
    try {\
      await llamaInstance.dispose();\
    } catch { /* ignore cleanup errors */ }\
    llamaInstance = null;\
  }\
}' "$LIBRARIAN_PATH/llm/embed.ts"
    echo "  ✓ Added disposeEmbedding to llm/embed.ts"
else
    echo "  ✓ llm/embed.ts already patched"
fi

# Fix 3: Update cli/embed.ts import and add cleanup call
if ! grep -q "disposeEmbedding" "$LIBRARIAN_PATH/cli/embed.ts"; then
    sed -i 's/import { embedText, formatDocForEmbedding, getDefaultEmbedModel, type EmbeddingUsage } from "..\/llm\/embed";/import { embedText, formatDocForEmbedding, getDefaultEmbedModel, disposeEmbedding, type EmbeddingUsage } from "..\/llm\/embed";/' "$LIBRARIAN_PATH/cli/embed.ts"
    sed -i '/^  if (totalQueued === 0) {$/i\  // Dispose llama resources to prevent segfault on exit\n  await disposeEmbedding();\n' "$LIBRARIAN_PATH/cli/embed.ts"
    echo "  ✓ Fixed cli/embed.ts"
else
    echo "  ✓ cli/embed.ts already patched"
fi

# Fix 4: Update services/search-run.ts
if ! grep -q "disposeEmbedding" "$LIBRARIAN_PATH/services/search-run.ts"; then
    sed -i '/^import { searchHybridRows/a import { disposeEmbedding } from "../llm/embed";' "$LIBRARIAN_PATH/services/search-run.ts"
    sed -i 's/libraryStore.close();$/libraryStore.close();\n    \/\/ Dispose llama resources to prevent segfault on exit after vector\/hybrid search\n    await disposeEmbedding();/' "$LIBRARIAN_PATH/services/search-run.ts"
    echo "  ✓ Fixed services/search-run.ts"
else
    echo "  ✓ services/search-run.ts already patched"
fi

echo ""
echo "All Librarian fixes applied successfully!"
echo "Test with: librarian embed --source 1 --force"
