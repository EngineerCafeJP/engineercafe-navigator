# 再利用パターン (SSOT)

> このファイルはプロジェクトで確立されたパターンを記録します。
> 新しいパターンは上部に追加してください。

---

## エージェント実装パターン

### Mastra エージェント (TypeScript)

```typescript
// frontend/src/mastra/agents/[agent-name].ts
import { Agent } from '@mastra/core';

export const myAgent = new Agent({
  name: 'MyAgent',
  instructions: `
    あなたは [役割] です。
    [責任範囲]
  `,
  model: {
    provider: 'google',
    name: 'gemini-2.5-flash-preview',
  },
  tools: [/* 使用するツール */],
});
```

### LangGraph ノード (Python)

```python
# backend/agents/[agent_name].py
from typing import TypedDict
from langgraph.graph import StateGraph

class AgentState(TypedDict):
    query: str
    language: str
    response: str | None

def agent_node(state: AgentState) -> dict:
    # 処理ロジック
    return {"response": "..."}
```

---

## API ルートパターン

### Next.js App Router

```typescript
// frontend/src/app/api/[endpoint]/route.ts
import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    // 処理
    return NextResponse.json({ success: true, data: result });
  } catch (error) {
    console.error('[API Error]:', error);
    return NextResponse.json(
      { success: false, error: 'Internal error' },
      { status: 500 }
    );
  }
}
```

---

## RAG 検索パターン

```typescript
const results = await enhancedRagSearch({
  query,
  language: 'ja',
  category: 'business-info',
  limit: 5,
});
```

---

## エラーハンドリングパターン

```typescript
try {
  // 処理
} catch (error) {
  console.error(`[${AgentName}] Error:`, error);
  return {
    success: false,
    error: error instanceof Error ? error.message : 'Unknown error',
  };
}
```

---

## テストパターン

### Python (pytest)

```python
# backend/tests/test_[agent].py
import pytest
from agents.[agent] import agent_node

def test_agent_basic():
    state = {"query": "テスト", "language": "ja"}
    result = agent_node(state)
    assert "response" in result
```

---

## コミットメッセージパターン

```
feat(agent:router): Add context-aware routing

- Implement memory integration for follow-up queries
- Add support for "も" particles in Japanese
- Improve routing accuracy to 94%

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```
