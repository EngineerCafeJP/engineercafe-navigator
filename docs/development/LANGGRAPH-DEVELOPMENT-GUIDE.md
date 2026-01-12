# LangGraph 開発ガイド

このガイドでは、Engineer Cafe Navigator プロジェクトで LangGraph エージェントを開発する方法を説明します。

## 目次

1. [LangGraph の概要](#langgraph-の概要)
2. [プロジェクト構成](#プロジェクト構成)
3. [エージェントアーキテクチャ](#エージェントアーキテクチャ)
4. [新しいエージェントの作成](#新しいエージェントの作成)
5. [ワークフローの実装](#ワークフローの実装)
6. [Supabase との連携](#supabase-との連携)
7. [テストとデバッグ](#テストとデバッグ)
8. [参考実装](#参考実装)

---

## LangGraph の概要

LangGraph は LangChain をベースとしたワークフローエンジンで、複雑な AI エージェントワークフローを構築するためのフレームワークです。

### 主要概念

| 概念 | 説明 |
|------|------|
| **StateGraph** | ワークフロー全体を管理するグラフ |
| **Node** | グラフ内の処理ステップ |
| **Edge** | ノード間の遷移 |
| **Conditional Edge** | 条件に基づく分岐 |
| **State** | ワークフロー全体で共有される状態 |

### LangGraph vs Mastra

| 機能 | Mastra (現在) | LangGraph (移行後) |
|------|--------------|-------------------|
| 言語 | TypeScript | Python |
| 状態管理 | エージェント内部 | 明示的な State オブジェクト |
| ワークフロー | 暗黙的 | 明示的なグラフ構造 |
| デバッグ | 限定的 | 可視化可能 |
| テスト | 難しい | ノード単位で可能 |

---

## プロジェクト構成

```
backend/
├── src/
│   ├── main.py              # FastAPI エントリーポイント
│   ├── agents/              # エージェント実装
│   │   ├── __init__.py
│   │   ├── router_agent.py  # ルーターエージェント
│   │   ├── business_info_agent.py
│   │   ├── facility_agent.py
│   │   ├── event_agent.py
│   │   ├── memory_agent.py
│   │   ├── clarification_agent.py
│   │   ├── general_knowledge_agent.py
│   │   └── nodes/           # 共有ノード
│   │       ├── __init__.py
│   │       ├── rag_search.py
│   │       └── llm_response.py
│   ├── models/              # Pydantic モデル
│   │   ├── __init__.py
│   │   ├── state.py         # ワークフロー状態
│   │   ├── request.py       # API リクエスト
│   │   └── response.py      # API レスポンス
│   ├── tools/               # LangChain ツール
│   │   ├── __init__.py
│   │   ├── rag_search.py    # RAG 検索ツール
│   │   └── supabase.py      # Supabase クライアント
│   └── config/              # 設定
│       ├── __init__.py
│       └── settings.py
├── tests/                   # テスト
│   ├── __init__.py
│   ├── test_router.py
│   └── test_agents/
├── requirements.txt
├── .env.example
└── README.md
```

---

## エージェントアーキテクチャ

### 全体構成

```
                    ┌─────────────────┐
                    │   User Query    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Router Agent   │
                    └────────┬────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│ BusinessInfo │    │   Facility   │    │    Event     │
│    Agent     │    │    Agent     │    │    Agent     │
└──────────────┘    └──────────────┘    └──────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Response Node  │
                    └─────────────────┘
```

### エージェント一覧

| エージェント | 責務 | 担当者 |
|------------|------|--------|
| **RouterAgent** | クエリルーティング | テリスケ, YukitoLyn |
| **BusinessInfoAgent** | 営業情報 | テリスケ |
| **FacilityAgent** | 設備情報 | Natsumi, けいてぃー |
| **EventAgent** | イベント情報 | テリスケ |
| **MemoryAgent** | 会話履歴 | takegg0311, YukitoLyn, Natsumi, Jun |
| **ClarificationAgent** | 曖昧性解消 | Chie, Jun |
| **GeneralKnowledgeAgent** | 一般知識 | テリスケ |

---

## 新しいエージェントの作成

### 1. 状態定義（State）

```python
# src/models/state.py
from typing import TypedDict, Optional, List
from langchain_core.messages import BaseMessage

class WorkflowState(TypedDict):
    """ワークフロー全体で共有される状態"""
    # 入力
    query: str
    language: str  # "ja" or "en"
    session_id: str

    # 処理中
    messages: List[BaseMessage]
    route: Optional[str]
    context: Optional[str]

    # 出力
    response: Optional[str]
    emotion: Optional[str]
    metadata: dict
```

### 2. エージェント実装

```python
# src/agents/business_info_agent.py
from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import OpenAIEmbeddings

from src.models.state import WorkflowState
from src.tools.rag_search import search_knowledge_base

# LLM の初期化
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-preview-05-20",
    temperature=0.7
)

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small"
)


def rag_search_node(state: WorkflowState) -> dict:
    """RAG 検索ノード"""
    query = state["query"]
    language = state["language"]

    # ナレッジベース検索
    results = search_knowledge_base(
        query=query,
        language=language,
        category="基本情報",
        limit=5
    )

    context = "\n".join([r.content for r in results])

    return {"context": context}


def llm_response_node(state: WorkflowState) -> dict:
    """LLM 応答生成ノード"""
    query = state["query"]
    context = state["context"]
    language = state["language"]

    # プロンプト構築
    if language == "ja":
        prompt = f"""
あなたはエンジニアカフェの案内アシスタントです。
以下のコンテキストを使用して、ユーザーの質問に答えてください。

コンテキスト:
{context}

質問: {query}

回答:
"""
    else:
        prompt = f"""
You are an Engineer Cafe guide assistant.
Answer the user's question using the following context.

Context:
{context}

Question: {query}

Answer:
"""

    # LLM 呼び出し
    response = llm.invoke(prompt)

    return {
        "response": response.content,
        "emotion": "helpful",
        "metadata": {"agent": "BusinessInfoAgent"}
    }


def create_business_info_graph() -> StateGraph:
    """BusinessInfoAgent のグラフを作成"""
    graph = StateGraph(WorkflowState)

    # ノードの追加
    graph.add_node("rag_search", rag_search_node)
    graph.add_node("llm_response", llm_response_node)

    # エッジの追加
    graph.add_edge("rag_search", "llm_response")
    graph.add_edge("llm_response", END)

    # エントリーポイント
    graph.set_entry_point("rag_search")

    return graph.compile()


# エージェントインスタンス
business_info_agent = create_business_info_graph()
```

### 3. ルーターへの統合

```python
# src/agents/router_agent.py
from langgraph.graph import StateGraph, END
from src.agents.business_info_agent import business_info_agent
from src.agents.facility_agent import facility_agent
from src.agents.event_agent import event_agent


def route_query(state: WorkflowState) -> str:
    """クエリを適切なエージェントにルーティング"""
    query = state["query"].lower()

    # ルーティングルール
    if any(kw in query for kw in ["営業", "時間", "開いて", "hours", "open"]):
        return "business_info"
    elif any(kw in query for kw in ["設備", "Wi-Fi", "会議室", "equipment", "facility"]):
        return "facility"
    elif any(kw in query for kw in ["イベント", "予定", "event", "schedule"]):
        return "event"
    else:
        return "general"


def create_router_graph() -> StateGraph:
    """RouterAgent のグラフを作成"""
    graph = StateGraph(WorkflowState)

    # ルーティングノード
    graph.add_node("router", lambda state: {"route": route_query(state)})

    # エージェントノード
    graph.add_node("business_info", business_info_agent)
    graph.add_node("facility", facility_agent)
    graph.add_node("event", event_agent)
    graph.add_node("general", general_agent)

    # 条件分岐
    graph.add_conditional_edges(
        "router",
        lambda state: state["route"],
        {
            "business_info": "business_info",
            "facility": "facility",
            "event": "event",
            "general": "general"
        }
    )

    # 全エージェントから終了へ
    graph.add_edge("business_info", END)
    graph.add_edge("facility", END)
    graph.add_edge("event", END)
    graph.add_edge("general", END)

    graph.set_entry_point("router")

    return graph.compile()
```

---

## ワークフローの実装

### 条件分岐

```python
from langgraph.graph import StateGraph, END

def should_clarify(state: WorkflowState) -> str:
    """曖昧性があるかチェック"""
    query = state["query"]

    # 曖昧なクエリのパターン
    ambiguous_patterns = ["カフェ", "cafe", "ここ", "here"]

    if any(p in query.lower() for p in ambiguous_patterns):
        return "clarify"
    return "continue"


graph = StateGraph(WorkflowState)

graph.add_node("check_ambiguity", lambda s: s)
graph.add_node("clarify", clarification_agent)
graph.add_node("process", main_agent)

graph.add_conditional_edges(
    "check_ambiguity",
    should_clarify,
    {
        "clarify": "clarify",
        "continue": "process"
    }
)
```

### 並列処理

```python
from langgraph.graph import StateGraph
from langgraph.pregel import Pregel

def create_parallel_graph():
    graph = StateGraph(WorkflowState)

    # 並列で実行するノード
    graph.add_node("rag_search", rag_search_node)
    graph.add_node("memory_search", memory_search_node)
    graph.add_node("merge", merge_results_node)

    # 並列エッジ（同時に両方へ）
    graph.add_edge("start", "rag_search")
    graph.add_edge("start", "memory_search")

    # マージノードへ
    graph.add_edge("rag_search", "merge")
    graph.add_edge("memory_search", "merge")

    return graph.compile()
```

---

## Supabase との連携

### クライアント設定

```python
# src/tools/supabase.py
from supabase import create_client, Client
from src.config.settings import settings

supabase: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_KEY
)
```

### RAG 検索の実装

```python
# src/tools/rag_search.py
from typing import List, Optional
from langchain_openai import OpenAIEmbeddings
from src.tools.supabase import supabase

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")


def search_knowledge_base(
    query: str,
    language: str = "ja",
    category: Optional[str] = None,
    limit: int = 5
) -> List[dict]:
    """ナレッジベースを検索"""

    # クエリをベクトル化
    query_embedding = embeddings.embed_query(query)

    # RPC 関数を呼び出し
    result = supabase.rpc(
        "search_knowledge_base",
        {
            "query_embedding": query_embedding,
            "match_count": limit,
            "filter_language": language,
            "filter_category": category
        }
    ).execute()

    return result.data


def add_to_memory(
    session_id: str,
    key: str,
    value: str,
    agent_name: str,
    ttl_seconds: int = 180  # 3分
) -> None:
    """エージェントメモリに追加"""

    supabase.table("agent_memory").upsert({
        "session_id": session_id,
        "key": key,
        "value": value,
        "agent_name": agent_name,
        "expires_at": f"now() + interval '{ttl_seconds} seconds'"
    }).execute()


def get_from_memory(
    session_id: str,
    key: str
) -> Optional[str]:
    """エージェントメモリから取得"""

    result = supabase.table("agent_memory").select("value").eq(
        "session_id", session_id
    ).eq(
        "key", key
    ).gt(
        "expires_at", "now()"
    ).execute()

    if result.data:
        return result.data[0]["value"]
    return None
```

### 会話履歴の保存

```python
def save_conversation(
    session_id: str,
    role: str,
    content: str,
    language: str,
    metadata: dict = None
) -> None:
    """会話履歴を保存"""

    supabase.table("conversation_history").insert({
        "session_id": session_id,
        "role": role,
        "content": content,
        "language": language,
        "metadata": metadata or {}
    }).execute()
```

---

## テストとデバッグ

### ユニットテスト

```python
# tests/test_agents/test_business_info.py
import pytest
from src.agents.business_info_agent import business_info_agent
from src.models.state import WorkflowState

@pytest.fixture
def initial_state():
    return WorkflowState(
        query="エンジニアカフェの営業時間は？",
        language="ja",
        session_id="test-session-001",
        messages=[],
        route=None,
        context=None,
        response=None,
        emotion=None,
        metadata={}
    )


def test_business_info_agent(initial_state):
    """BusinessInfoAgent の基本テスト"""
    result = business_info_agent.invoke(initial_state)

    assert result["response"] is not None
    assert "営業" in result["response"] or "時間" in result["response"]
    assert result["metadata"]["agent"] == "BusinessInfoAgent"


def test_business_info_agent_english():
    """英語クエリのテスト"""
    state = WorkflowState(
        query="What are the opening hours?",
        language="en",
        session_id="test-session-002",
        messages=[],
        route=None,
        context=None,
        response=None,
        emotion=None,
        metadata={}
    )

    result = business_info_agent.invoke(state)

    assert result["response"] is not None
    assert result["language"] == "en" or "hours" in result["response"].lower()
```

### グラフの可視化

```python
from langgraph.graph import StateGraph
from IPython.display import Image, display

def visualize_graph(graph: StateGraph, filename: str = "graph.png"):
    """グラフを可視化"""
    try:
        display(Image(graph.get_graph().draw_mermaid_png()))
    except Exception:
        # Mermaid がない場合はテキスト出力
        print(graph.get_graph().draw_mermaid())


# 使用例
from src.agents.router_agent import create_router_graph
graph = create_router_graph()
visualize_graph(graph)
```

### デバッグログ

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def rag_search_node(state: WorkflowState) -> dict:
    logger.debug(f"RAG search query: {state['query']}")

    results = search_knowledge_base(state["query"])

    logger.debug(f"RAG results count: {len(results)}")
    logger.debug(f"Top result: {results[0] if results else 'None'}")

    return {"context": "\n".join([r["content"] for r in results])}
```

---

## 参考実装

### langgraph-reference ディレクトリ

プロジェクト内の `langgraph-reference/coworking-space-system/` に完全な参考実装があります：

```
langgraph-reference/coworking-space-system/
├── docker-compose.yml       # ローカル DB 環境
├── .env.example             # 環境変数テンプレート
├── database/
│   ├── schema.sql           # DB スキーマ
│   └── demo_data.sql        # デモデータ
├── backend/
│   ├── main.py              # FastAPI エントリー
│   ├── agents/              # エージェント実装
│   │   ├── router.py
│   │   ├── business_info.py
│   │   └── facility.py
│   └── tools/
│       └── rag.py           # RAG ツール
└── README.md
```

### 参考実装の起動

```bash
cd langgraph-reference/coworking-space-system

# Docker 起動
docker-compose up -d

# バックエンド起動
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

---

## リソース

- [LangGraph 公式ドキュメント](https://langchain-ai.github.io/langgraph/)
- [LangChain Python ドキュメント](https://python.langchain.com/)
- [Supabase Python クライアント](https://supabase.com/docs/reference/python)
- [FastAPI ドキュメント](https://fastapi.tiangolo.com/)
- [エージェント移行ドキュメント](./migration/agents/)
