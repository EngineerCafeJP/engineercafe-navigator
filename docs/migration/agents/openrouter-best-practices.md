# OpenRouter API ベストプラクティス

> **目的**: OpenRouter APIを使用したエージェント実装の推奨パターンとアンチパターン

## 🎯 基本原則

### 1. 統一されたプロバイダー使用

**✅ Good: OpenRouterProviderを使用**
```python
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import MODEL_CONFIGS

# 統一されたプロバイダー
provider = OpenRouterProvider()
llm = provider.get_langchain_llm(MODEL_CONFIGS["router"])
```

**❌ Bad: Gemini直接APIを使用**
```python
# 使用禁止！
from langchain_google_genai import ChatGoogleGenerativeAI

llm = ChatGoogleGenerativeAI(model="gemini-pro")  # NG
```

### 2. 設定の一元管理

**✅ Good: MODEL_CONFIGSから取得**
```python
from backend.llm.models import MODEL_CONFIGS, get_model_config

# use caseに応じた設定を使用
config = MODEL_CONFIGS["qa_response"]
llm = provider.get_langchain_llm(config)
```

**❌ Bad: ハードコーディング**
```python
# アンチパターン
llm = ChatOpenAI(
    model="google/gemini-3-flash-preview",  # 直接指定はNG
    temperature=0.7,
    max_tokens=1024,
)
```

### 3. フォールバックモデルの設定

**✅ Good: フォールバック設定**
```python
from backend.llm.models import ModelConfig, SupportedModel

config = ModelConfig(
    model_id=SupportedModel.GEMINI_3_FLASH,
    temperature=0.7,
    max_tokens=1024,
    fallback_model=SupportedModel.GPT_4O,  # フォールバック設定
)
```

**❌ Bad: フォールバックなし**
```python
# リスクあり
config = ModelConfig(
    model_id=SupportedModel.GEMINI_3_FLASH,
    temperature=0.7,
    max_tokens=1024,
    # fallback_modelがないとAPI障害時に失敗する
)
```

## 🏗️ エージェント実装パターン

### RouterAgent実装例

```python
from typing import List
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import MODEL_CONFIGS

class RouterAgent:
    """
    RouterAgent implementation using OpenRouter API.

    Uses Gemini 3 Flash for fast, consistent routing decisions.
    """

    def __init__(self):
        self.provider = OpenRouterProvider()
        self.llm = self.provider.get_langchain_llm(
            MODEL_CONFIGS["router"]  # 低temperature、短いmax_tokens
        )

    async def route_query(self, query: str, context: dict) -> str:
        """
        Route user query to appropriate agent.

        Args:
            query: User's question
            context: Conversation context

        Returns:
            Agent name to handle the query
        """
        messages: List[BaseMessage] = [
            SystemMessage(content=self._get_system_prompt()),
            HumanMessage(content=query),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return self._parse_routing_decision(response.content)
        except Exception as e:
            # フォールバックは自動的に試行される
            print(f"[RouterAgent] Error: {e}")
            return "general_knowledge"  # デフォルト

    def _get_system_prompt(self) -> str:
        return """
        あなたはユーザーの質問を適切なエージェントにルーティングする
        ルーターエージェントです。

        利用可能なエージェント:
        - business_info: 営業時間、料金、場所
        - facility: 設備、Wi-Fi、会議室
        - event: イベント、カレンダー
        - memory: 過去の会話
        - general_knowledge: その他
        """

    def _parse_routing_decision(self, response: str) -> str:
        # レスポンスからエージェント名を抽出
        response = response.strip().lower()
        valid_agents = [
            "business_info",
            "facility",
            "event",
            "memory",
            "general_knowledge",
        ]

        for agent in valid_agents:
            if agent in response:
                return agent

        return "general_knowledge"  # デフォルト
```

### Q&Aエージェント実装例

```python
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import MODEL_CONFIGS

class QAAgent:
    """
    Q&A Agent using OpenRouter API.

    Uses Gemini 3 Flash with GPT-4o fallback for high-quality responses.
    """

    def __init__(self):
        self.provider = OpenRouterProvider()
        self.llm = self.provider.get_langchain_llm(
            MODEL_CONFIGS["qa_response"]
        )

    async def generate_response(
        self,
        query: str,
        context: str,
        language: str = "ja",
    ) -> str:
        """
        Generate response to user query with RAG context.

        Args:
            query: User's question
            context: Retrieved context from RAG
            language: Response language (ja/en)

        Returns:
            Generated response
        """
        system_prompt = self._build_system_prompt(language, context)

        messages: List[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=query),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            print(f"[QAAgent] Error: {e}")
            return self._get_error_message(language)

    def _build_system_prompt(self, language: str, context: str) -> str:
        if language == "ja":
            return f"""
            あなたはエンジニアカフェのナビゲーターです。
            以下のコンテキストを参考に、丁寧に回答してください。

            コンテキスト:
            {context}

            - 簡潔に1-2文で回答
            - コンテキストに基づいた正確な情報
            - 不明な点は正直に伝える
            """
        else:
            return f"""
            You are the Engineer Cafe Navigator.
            Please provide a helpful response based on the context below.

            Context:
            {context}

            - Keep responses concise (1-2 sentences)
            - Provide accurate information based on context
            - Be honest if information is unavailable
            """

    def _get_error_message(self, language: str) -> str:
        if language == "ja":
            return "申し訳ございません。現在応答できません。後ほどお試しください。"
        else:
            return "I apologize, but I'm unable to respond right now. Please try again later."
```

## ⚡ パフォーマンス最適化

### 1. 適切なモデル選択

```python
# 高速・低コストが必要な場合
router_config = MODEL_CONFIGS["router"]  # Gemini 3 Flash, 256 tokens

# 高品質な応答が必要な場合
qa_config = MODEL_CONFIGS["qa_response"]  # Gemini 3 Flash, 1024 tokens

# 複雑な推論が必要な場合
knowledge_config = MODEL_CONFIGS["general_knowledge"]  # Claude Sonnet 4
```

### 2. ストリーミング応答

```python
async def stream_response(self, query: str) -> AsyncGenerator[str, None]:
    """Stream response for better UX."""
    messages = [HumanMessage(content=query)]

    async for chunk in self.provider.stream(
        messages,
        MODEL_CONFIGS["qa_response"]
    ):
        yield chunk
```

### 3. コンテキスト最適化

```python
# ✅ Good: 必要な情報だけを含める
context = rag_results[:3]  # Top 3 results

# ❌ Bad: 冗長なコンテキスト
context = rag_results[:20]  # 多すぎる
```

## 🔒 エラーハンドリング

### 1. 構造化エラー処理

```python
from backend.llm.openrouter import OpenRouterError

async def safe_generate(self, messages: List[BaseMessage]) -> str:
    """
    Generate with comprehensive error handling.
    """
    try:
        response = await self.provider.generate(
            messages,
            MODEL_CONFIGS["qa_response"]
        )
        return response

    except OpenRouterError as e:
        # OpenRouter固有のエラー
        if e.status_code == 429:
            print("[OpenRouter] Rate limit exceeded")
            # レート制限時の処理
            await asyncio.sleep(1)
            return await self.safe_generate(messages)  # リトライ

        elif e.status_code == 401:
            print("[OpenRouter] Invalid API key")
            raise  # 認証エラーは再スローすべき

        else:
            print(f"[OpenRouter] API Error: {e.message}")
            # フォールバックは自動的に試行済み
            return self._get_fallback_response()

    except Exception as e:
        # その他のエラー
        print(f"[Error] Unexpected: {e}")
        return self._get_fallback_response()
```

### 2. タイムアウト設定

```python
from backend.llm.models import ModelConfig, SupportedModel

# カスタムタイムアウト
custom_config = ModelConfig(
    model_id=SupportedModel.GEMINI_3_FLASH,
    temperature=0.7,
    max_tokens=1024,
    timeout=45.0,  # 45秒タイムアウト
)
```

## 📊 モニタリング

### 1. ログ記録

```python
import time

async def generate_with_logging(self, messages: List[BaseMessage]) -> str:
    """Generate with performance logging."""
    start_time = time.time()
    model_name = MODEL_CONFIGS["qa_response"].model_id.value

    try:
        response = await self.provider.generate(
            messages,
            MODEL_CONFIGS["qa_response"]
        )

        duration = time.time() - start_time
        print(f"[OpenRouter] Model: {model_name}, Duration: {duration:.2f}s")

        return response

    except Exception as e:
        duration = time.time() - start_time
        print(f"[OpenRouter] Error after {duration:.2f}s: {e}")
        raise
```

### 2. コスト追跡

```python
from backend.llm.models import ModelConfig

def estimate_cost(config: ModelConfig, tokens_used: int) -> float:
    """
    Estimate API cost based on token usage.

    Args:
        config: Model configuration with cost metadata
        tokens_used: Number of tokens used

    Returns:
        Estimated cost in USD
    """
    # Input + Output コスト（概算）
    cost_per_1k = (config.input_cost_per_1k + config.output_cost_per_1k) / 2
    return (tokens_used / 1000) * cost_per_1k
```

## 🧪 テストパターン

### 1. モックテスト

```python
from unittest.mock import AsyncMock, patch
import pytest

@pytest.mark.asyncio
async def test_router_agent_with_mock():
    """Test RouterAgent with mocked OpenRouter."""

    with patch("backend.llm.openrouter.OpenRouterProvider") as mock_provider:
        # モックの設定
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value.content = "business_info"
        mock_provider.return_value.get_langchain_llm.return_value = mock_llm

        # テスト実行
        agent = RouterAgent()
        result = await agent.route_query("営業時間は？", {})

        assert result == "business_info"
        mock_llm.ainvoke.assert_called_once()
```

### 2. 統合テスト

```python
import pytest
from backend.llm.openrouter import OpenRouterProvider
from backend.llm.models import MODEL_CONFIGS

@pytest.mark.integration
@pytest.mark.asyncio
async def test_openrouter_real_api():
    """Test real OpenRouter API integration."""

    provider = OpenRouterProvider()

    try:
        llm = provider.get_langchain_llm(MODEL_CONFIGS["router"])

        messages = [HumanMessage(content="Hello")]
        response = await llm.ainvoke(messages)

        assert response.content
        assert len(response.content) > 0

    finally:
        await provider.close()
```

## 🚨 よくある間違い

### 1. API キーのハードコーディング

```python
# ❌ Bad
provider = OpenRouterProvider(api_key="sk-or-...")

# ✅ Good
provider = OpenRouterProvider()  # 環境変数から取得
```

### 2. 非同期処理の誤用

```python
# ❌ Bad: 同期的に呼び出し
response = provider.generate(messages)  # SyntaxError

# ✅ Good: await使用
response = await provider.generate(messages)
```

### 3. リソースリーク

```python
# ❌ Bad: クローズし忘れ
async def get_response():
    provider = OpenRouterProvider()
    return await provider.generate(messages)
    # providerがクローズされない

# ✅ Good: コンテキストマネージャー使用
async def get_response():
    async with OpenRouterProvider() as provider:
        return await provider.generate(messages)
    # 自動的にクローズされる
```

## 📚 参考リンク

- [OpenRouter公式ドキュメント](https://openrouter.ai/docs)
- [LangChain統合ガイド](https://python.langchain.com/docs/integrations/chat/openrouter)
- [backend/llm/openrouter.py](../../../backend/llm/openrouter.py) - 実装例
- [backend/llm/models.py](../../../backend/llm/models.py) - モデル設定
- [OpenRouter使用チェックリスト](./openrouter-checklist.md)

## 🔄 更新履歴

- 2025-12-27: 初版作成（2025/12最新モデル対応）
- 使用モデル: Gemini 3 Flash, Claude Sonnet 4, GPT-5.2
