# Agent Quickstart Guide

> 新規エンジニアがエージェント実装を最短で開始するためのステップバイステップガイド

**目標**: 30分以内にエージェントの骨組みを実装できる

---

## 目次

1. [環境セットアップ (5分)](#1-環境セットアップ-5分)
2. [プロジェクト構造の理解 (5分)](#2-プロジェクト構造の理解-5分)
3. [エージェント実装テンプレート (10分)](#3-エージェント実装テンプレート-10分)
4. [ワークフロー統合 (5分)](#4-ワークフロー統合-5分)
5. [テストの書き方 (5分)](#5-テストの書き方-5分)
6. [よく使うコマンド一覧](#6-よく使うコマンド一覧)

---

## 1. 環境セットアップ (5分)

### 前提条件

- Docker Desktop がインストールされていること
- Git がインストールされていること

### クイックセットアップ

```bash
# 1. リポジトリをクローン
git clone https://github.com/your-org/engineer-cafe-navigator2025.git
cd engineer-cafe-navigator2025

# 2. 環境変数を設定
cp frontend/.env.example frontend/.env.local
cp backend/.env.example backend/.env

# 3. 初期セットアップ（mise + Docker build）
make setup

# 4. 開発サーバー起動
make dev
```

### 動作確認

| URL | サービス |
|-----|---------|
| http://localhost:3000 | Frontend（Next.js） |
| http://localhost:8000 | Backend（FastAPI） |
| http://localhost:8000/docs | Backend API ドキュメント |

---

## 2. プロジェクト構造の理解 (5分)

### バックエンドエージェント構造

```
backend/
├── agents/                      # エージェント実装
│   ├── __init__.py             # エクスポート定義
│   ├── router_agent.py         # ルーティングエージェント
│   ├── business_info_agent.py  # 営業情報エージェント ★参考実装
│   ├── event_agent.py          # イベントエージェント ★参考実装
│   ├── facility_agent.py       # 施設情報エージェント
│   ├── clarification_agent.py  # 曖昧性解消エージェント
│   ├── general_knowledge_agent.py # 一般知識エージェント
│   ├── slide_agent.py          # スライドエージェント
│   ├── memory_agent.py         # メモリエージェント
│   └── voice_agent.py          # 音声エージェント
├── tools/                       # 共有ツール
│   ├── enhanced_rag.py         # Enhanced RAG検索
│   └── calendar_service.py     # カレンダーサービス
├── workflows/                   # LangGraphワークフロー
│   └── main_workflow.py        # メインワークフロー ★統合先
├── llm.py                       # LLMプロバイダー
└── tests/                       # テスト
    └── templates/
        └── test_agent_template.py  # テストテンプレート ★参考
```

### エージェントアーキテクチャ

```
                    ┌─────────────────┐
                    │   User Query    │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Router Agent   │ ← クエリを分類
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
                    │  Response Node  │ ← 応答フォーマット
                    └─────────────────┘
```

---

## 3. エージェント実装テンプレート (10分)

### 3.1 新規エージェントの作成

新しいエージェントを作成する場合、以下のテンプレートを使用します。

**ファイル**: `backend/agents/your_new_agent.py`

```python
"""
YourNewAgent - [エージェントの説明]
[担当する機能の詳細]
"""

from typing import Dict, Optional
from backend.tools.enhanced_rag import EnhancedRAGSearch
from backend.llm import get_llm_provider, get_model_config


class YourNewAgent:
    """[エージェントの説明]"""

    def __init__(self):
        """初期化"""
        self.enhanced_rag = EnhancedRAGSearch()
        self.llm_provider = get_llm_provider()

    async def answer_your_query(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
        session_id: Optional[str] = None,
    ) -> Dict:
        """
        クエリに回答

        Args:
            query: ユーザークエリ
            request_type: リクエストタイプ
            language: 言語（ja or en）
            session_id: セッションID

        Returns:
            回答辞書 {answer, emotion, metadata}
        """
        print(f"[YourNewAgent] Processing query: {query}")

        # 1. Enhanced RAG検索
        rag_result = await self.enhanced_rag.search(
            query=query,
            category=self._get_category(request_type),
            language=language,
            include_advice=True,
            max_results=10
        )

        if not rag_result.get("success"):
            return self._get_default_response(language)

        # 2. コンテキスト取得
        context = rag_result.get("data", {}).get("context", "")

        if not context:
            return self._get_default_response(language)

        # 3. プロンプト構築
        prompt = self._build_prompt(query, context, language)

        # 4. LLM応答生成
        try:
            response_text = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}],
                config=get_model_config("facility_info"),
            )

            return {
                "answer": response_text,
                "emotion": self._determine_emotion(response_text),
                "metadata": {
                    "agent": "YourNewAgent",
                    "confidence": 0.85,
                    "sources": ["enhanced_rag"],
                },
            }

        except Exception as e:
            print(f"[YourNewAgent] LLM error: {e}")
            return self._get_default_response(language)

    def _get_category(self, request_type: Optional[str]) -> str:
        """カテゴリマッピング"""
        category_mapping = {
            "type1": "category1",
            "type2": "category2",
        }
        return category_mapping.get(request_type or "", "general")

    def _build_prompt(self, query: str, context: str, language: str) -> str:
        """プロンプト構築"""
        if language == "en":
            return f"""Answer the question using the provided information.

Question: {query}
Information: {context}

Provide a brief and helpful answer. Maximum 2-3 sentences.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news."""
        else:
            return f"""提供された情報を使って質問に答えてください。

質問: {query}
情報: {context}

簡潔で役立つ回答を提供してください。最大2-3文。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""

    def _determine_emotion(self, response_text: str) -> str:
        """感情タグを決定"""
        if "[happy]" in response_text.lower():
            return "happy"
        elif "[sad]" in response_text.lower():
            return "sad"
        return "relaxed"

    def _get_default_response(self, language: str) -> Dict:
        """デフォルト応答（情報が見つからない場合）"""
        if language == "en":
            text = "[sad]I'm sorry, I couldn't find the information you're looking for."
        else:
            text = "[sad]申し訳ございません。お探しの情報が見つかりませんでした。"

        return {
            "answer": text,
            "emotion": "sad",
            "metadata": {
                "agent": "YourNewAgent",
                "confidence": 0.3,
                "sources": ["fallback"],
            },
        }
```

### 3.2 既存エージェントの参照

実装の参考として、以下のエージェントを確認してください。

#### BusinessInfoAgent (`backend/agents/business_info_agent.py`)

**特徴**:
- Enhanced RAG検索の使用
- requestTypeに基づくカテゴリマッピング
- 感情タグの動的決定

**参照ポイント**:
```python
# カテゴリマッピングの実装
def _map_request_type_to_category(self, request_type: Optional[str]) -> str:
    category_mapping = {
        "hours": "hours",
        "price": "pricing",
        "location": "location",
    }
    return category_mapping.get(request_type or "", "general")
```

#### EventAgent (`backend/agents/event_agent.py`)

**特徴**:
- CalendarServiceとの連携
- 時間範囲の抽出と処理
- イベントリストのフォーマット

**参照ポイント**:
```python
# 外部サービスとの連携
from backend.tools.calendar_service import CalendarService

class EventAgent:
    def __init__(self):
        self.calendar_service = CalendarService()
        self.llm_provider = get_llm_provider()
```

---

## 4. ワークフロー統合 (5分)

### 4.1 main_workflow.py への追加

新しいエージェントをワークフローに統合する手順:

**ファイル**: `backend/workflows/main_workflow.py`

#### Step 1: ノードの追加

```python
class MainWorkflow:
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(WorkflowState)

        # 既存ノード
        workflow.add_node("memory", self._memory_node)
        workflow.add_node("router", self._router_node)
        # ...

        # 新しいエージェントノードを追加
        workflow.add_node("your_new_agent", self._your_new_agent_node)
```

#### Step 2: ノード関数の実装

```python
async def _your_new_agent_node(self, state: WorkflowState) -> dict:
    """新しいエージェントノード"""
    from backend.agents.your_new_agent import YourNewAgent

    agent = YourNewAgent()
    query = state.get("query", "")
    language = state.get("language", "ja")
    session_id = state.get("session_id", "")
    request_type = state.get("metadata", {}).get("routing", {}).get("request_type")

    result = await agent.answer_your_query(query, request_type, language, session_id)

    return {
        "answer": result.get("answer", ""),
        "emotion": result.get("emotion", "neutral"),
        "metadata": {**state.get("metadata", {}), **result.get("metadata", {})},
    }
```

#### Step 3: ルーティング条件の追加

```python
# router_agent.py で新しいルーティングルールを追加
workflow.add_conditional_edges(
    "router",
    self._route_decision,
    {
        # 既存ルート
        "business_info": "business_info",
        "facility": "facility",
        # ...
        # 新しいルートを追加
        "your_new_agent": "your_new_agent",
    },
)
```

#### Step 4: エッジの追加

```python
# 新しいエージェントからformat_responseへのエッジを追加
workflow.add_edge("your_new_agent", "format_response")
```

### 4.2 エクスポートの更新

**ファイル**: `backend/agents/__init__.py`

```python
from backend.agents.business_info_agent import BusinessInfoAgent
from backend.agents.event_agent import EventAgent
from backend.agents.your_new_agent import YourNewAgent  # 追加

__all__ = ["BusinessInfoAgent", "EventAgent", "YourNewAgent"]  # 追加
```

---

## 5. テストの書き方 (5分)

### 5.1 テストテンプレートの使用

**テンプレート**: `backend/tests/templates/test_agent_template.py`

このテンプレートをコピーして、新しいエージェントのテストを作成します。

```bash
cp backend/tests/templates/test_agent_template.py backend/tests/test_your_new_agent.py
```

### 5.2 基本テストの実装

```python
"""YourNewAgentのテスト"""

import pytest
from unittest.mock import Mock, AsyncMock
from tests.utils.test_helpers import (
    create_mock_agent_response,
    assert_agent_response,
)
from tests.utils.mock_helpers import create_mock_openrouter_provider
from agents.your_new_agent import YourNewAgent


class TestYourNewAgent:
    """YourNewAgentのテストクラス"""

    def test_initialization_default(self):
        """デフォルト設定での初期化テスト"""
        agent = YourNewAgent()
        assert agent is not None
        assert hasattr(agent, "enhanced_rag")
        assert hasattr(agent, "llm_provider")

    @pytest.mark.asyncio
    async def test_basic_query(self):
        """基本的なクエリ処理テスト"""
        agent = YourNewAgent()

        # モックを設定
        agent.enhanced_rag.search = AsyncMock(return_value={
            "success": True,
            "data": {"context": "テストコンテキスト"}
        })
        agent.llm_provider.generate = AsyncMock(return_value="[relaxed]テスト回答です。")

        result = await agent.answer_your_query(
            query="テストクエリ",
            language="ja",
            session_id="test-session"
        )

        # アサーション
        assert result["answer"] is not None
        assert result["emotion"] in ["relaxed", "happy", "sad"]
        assert result["metadata"]["agent"] == "YourNewAgent"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """エラーハンドリングテスト"""
        agent = YourNewAgent()

        # RAG検索失敗をシミュレート
        agent.enhanced_rag.search = AsyncMock(return_value={"success": False})

        result = await agent.answer_your_query(
            query="テストクエリ",
            language="ja"
        )

        # デフォルトレスポンスが返されることを確認
        assert result["metadata"]["sources"] == ["fallback"]
```

### 5.3 テストの実行

```bash
# 特定のテストファイルを実行
cd backend
mise exec -- pytest tests/test_your_new_agent.py -v

# すべてのテストを実行
make test
```

---

## 6. よく使うコマンド一覧

### 開発コマンド

| コマンド | 説明 |
|---------|------|
| `make setup` | 初回セットアップ（mise + Docker build） |
| `make dev` | 開発サーバー起動（Docker Compose） |
| `make dev:frontend` | フロントエンドのみ起動 |
| `make dev:backend` | バックエンドのみ起動 |

### ビルド・テスト

| コマンド | 説明 |
|---------|------|
| `make build` | ビルド実行 |
| `make test` | テスト実行 |
| `make lint` | リンター実行（frontend + backend） |

### バックエンド固有

```bash
cd backend

# Pythonリンター
mise exec -- ruff check .
mise exec -- ruff check . --fix  # 自動修正
mise exec -- black .             # フォーマット

# テスト
mise exec -- pytest tests/ -v
mise exec -- pytest tests/test_your_agent.py -v  # 特定ファイル
mise exec -- pytest -k "test_basic" -v           # パターンマッチ

# 型チェック（設定されているモジュールのみ）
mise exec -- mypy src/module
```

### クリーンアップ

| コマンド | 説明 |
|---------|------|
| `make clean` | コンテナ停止・ボリューム削除 |
| `make clean:all` | ディープクリーンアップ（イメージも削除） |

---

## 参考ドキュメント

### 詳細ガイド

- [LOCAL-DEVELOPMENT-SETUP.md](./LOCAL-DEVELOPMENT-SETUP.md) - 環境セットアップの詳細
- [LANGGRAPH-DEVELOPMENT-GUIDE.md](./LANGGRAPH-DEVELOPMENT-GUIDE.md) - LangGraph開発の詳細

### 移行ガイド

エージェント別の詳細な移行ガイドは以下を参照:

| エージェント | ガイド |
|------------|--------|
| BusinessInfoAgent | [MIGRATION-GUIDE.md](../migration/agents/business-info-agent/MIGRATION-GUIDE.md) |
| EventAgent | [MIGRATION-GUIDE.md](../migration/agents/event-agent/MIGRATION-GUIDE.md) |
| FacilityAgent | [MIGRATION-GUIDE.md](../migration/agents/facility-agent/MIGRATION-GUIDE.md) |
| RouterAgent | [MIGRATION-GUIDE.md](../migration/agents/router-agent/MIGRATION-GUIDE.md) |
| ClarificationAgent | [MIGRATION-GUIDE.md](../migration/agents/clarification-agent/MIGRATION-GUIDE.md) |
| GeneralKnowledgeAgent | [MIGRATION-GUIDE.md](../migration/agents/general-knowledge-agent/MIGRATION-GUIDE.md) |

---

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| Docker が起動しない | Docker Desktop 未起動 | Docker Desktop を起動 |
| make コマンドが見つからない | make 未インストール | `brew install make` |
| mise が見つからない | mise 未インストール | `brew install mise` |
| Enhanced RAG結果が空 | エンベディング次元不一致 | 1536次元を確認 |
| LLM応答がない | API Key未設定 | `.env` ファイルを確認 |

### デバッグ方法

```python
# エージェント内でデバッグログを追加
print(f"[YourAgent] Query: {query}")
print(f"[YourAgent] RAG Result: {rag_result}")
print(f"[YourAgent] Context length: {len(context)}")
```

### サポート

問題が解決しない場合は、以下を確認してください:

1. 環境変数が正しく設定されているか
2. Docker コンテナが正常に起動しているか
3. 依存関係が正しくインストールされているか

---

**Next Steps**: このガイドに従ってエージェントの骨組みを実装したら、[LANGGRAPH-DEVELOPMENT-GUIDE.md](./LANGGRAPH-DEVELOPMENT-GUIDE.md) で詳細な実装パターンを学習してください。
