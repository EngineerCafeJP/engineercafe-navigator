# LLM Provider Abstraction

OpenRouter を通じた統一 AI モデルアクセスインターフェース。

## 概要

このモジュールは、OpenRouter API を使用して複数の AI プロバイダー（OpenAI, Google, Anthropic 等）を統一インターフェースで利用できるようにします。

## クイックスタート

### 1. 環境設定

```bash
# .env ファイルに API キーを設定
OPENROUTER_API_KEY=sk-or-v1-your-key-here
```

### 2. 基本的な使い方

```python
from llm import get_llm_provider, MODEL_CONFIGS
from langchain_core.messages import HumanMessage

# プロバイダーを取得
provider = get_llm_provider()

# レスポンスを生成
response = await provider.generate(
    messages=[HumanMessage(content="こんにちは！")],
    config=MODEL_CONFIGS["router"]
)
print(response)
```

### 3. LangGraph との統合

```python
from llm import get_llm_provider, MODEL_CONFIGS

# LangChain 互換の LLM を取得
provider = get_llm_provider()
llm = provider.get_langchain_llm(MODEL_CONFIGS["qa_response"])

# LangGraph ワークフローで使用
async def my_agent_node(state):
    messages = state["messages"]
    response = await llm.ainvoke(messages)
    return {"answer": response.content}
```

## 利用可能なモデル

| モデル | ID | 推奨用途 |
|--------|-----|----------|
| Gemini 2.5 Flash | `google/gemini-2.5-flash-preview` | 高速応答、ルーティング |
| GPT-4o | `openai/gpt-4o` | 複雑な推論 |
| GPT-4o Mini | `openai/gpt-4o-mini` | コスト効率の良いフォールバック |
| Claude 3.5 Sonnet | `anthropic/claude-3.5-sonnet` | 高品質応答 |
| Llama 3.2 90B | `meta-llama/llama-3.2-90b-vision-instruct` | ビジョンタスク |

## モデル設定

用途別に事前設定されたコンフィグ:

```python
from llm import MODEL_CONFIGS, get_model_config

# 利用可能な設定
# - "router": ルーティング用（低温度）
# - "qa_response": Q&A応答用
# - "clarification": 明確化用
# - "general_knowledge": 一般知識用
# - "event_info": イベント情報用
# - "facility_info": 施設情報用

config = get_model_config("router")
```

## チームメンバー向け: 新しいエージェントでの使用方法

### オプション 1: デフォルト設定を使用

```python
from llm import get_llm_provider

provider = get_llm_provider()
llm = provider.get_langchain_llm()  # デフォルト: qa_response
```

### オプション 2: カスタム設定

```python
from llm import get_llm_provider, ModelConfig, SupportedModel

provider = get_llm_provider()

my_config = ModelConfig(
    model_id=SupportedModel.GPT_4O,
    temperature=0.5,
    max_tokens=512,
    fallback_model=SupportedModel.GPT_4O_MINI,
)

llm = provider.get_langchain_llm(my_config)
```

### オプション 3: 直接 API 呼び出し

```python
from llm import get_llm_provider, MODEL_CONFIGS
from langchain_core.messages import HumanMessage, SystemMessage

provider = get_llm_provider()

messages = [
    SystemMessage(content="あなたはEngineer Cafeの案内AIです。"),
    HumanMessage(content="営業時間を教えてください"),
]

# 通常の生成
response = await provider.generate(messages, MODEL_CONFIGS["qa_response"])

# ストリーミング生成
async for chunk in provider.stream(messages):
    print(chunk, end="", flush=True)
```

## フォールバック機能

プライマリモデルが失敗した場合、自動的にフォールバックモデルに切り替わります:

```python
from llm import ModelConfig, SupportedModel

config = ModelConfig(
    model_id=SupportedModel.GEMINI_2_5_FLASH,  # プライマリ
    fallback_model=SupportedModel.GPT_4O_MINI,  # フォールバック
    temperature=0.7,
)
```

## エラーハンドリング

```python
from llm import get_llm_provider, OpenRouterError

provider = get_llm_provider()

try:
    response = await provider.generate(messages)
except OpenRouterError as e:
    print(f"API エラー: {e.message}")
    print(f"ステータスコード: {e.status_code}")
```

## API キー情報の確認

```python
from llm import get_llm_provider

provider = get_llm_provider()

# 利用可能なモデル一覧
models = await provider.list_models()

# API キー情報（レート制限等）
key_info = await provider.check_key_info()
```

## ディレクトリ構成

```
backend/llm/
├── __init__.py      # モジュールエクスポート
├── models.py        # SupportedModel, ModelConfig, MODEL_CONFIGS
├── provider.py      # LLMProvider 抽象クラス, get_llm_provider()
├── openrouter.py    # OpenRouterProvider 実装
└── README.md        # このファイル
```

## 環境変数

| 変数名 | 必須 | 説明 |
|--------|------|------|
| `OPENROUTER_API_KEY` | ✅ | OpenRouter API キー |
| `APP_URL` | ❌ | アプリケーション URL（トラッキング用） |
| `OPENAI_API_KEY` | ❌ | OpenAI 直接アクセス用（オプション） |
| `GOOGLE_API_KEY` | ❌ | Google 直接アクセス用（オプション） |

## トラブルシューティング

### 401 Unauthorized

- API キーが正しいか確認
- 環境変数が読み込まれているか確認

```bash
echo $OPENROUTER_API_KEY
```

### Rate Limit エラー

- レート制限に達した場合は待機
- `fallback_model` を設定して別モデルにフォールバック

### モデルが見つからない

```python
# 利用可能なモデルを確認
models = await provider.list_models()
for m in models:
    print(m["id"])
```

## 参考リンク

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [OpenRouter Models](https://openrouter.ai/docs#models)
- [LangChain ChatOpenAI](https://python.langchain.com/docs/integrations/chat/openai)
