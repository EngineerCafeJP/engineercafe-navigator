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
| Cerebras GPT OSS 120B | `gpt-oss-120b` | native Cerebras first pass、短文・軽量回答 |
| Gemini 3.1 Flash Lite | `google/gemini-3.1-flash-lite-preview` | OpenRouter fallback、日常会話・ルーティング |
| Gemini 2.5 Flash-Lite | `google/gemini-2.5-flash-lite` | 安定版 fallback |
| Gemini 3.1 Pro | `google/gemini-3.1-pro-preview` | 高度な推論候補 |
| Gemini 2.5 Pro | `google/gemini-2.5-pro` | 高度な推論の安定版 fallback |
| GPT-5.4 Nano | `openai/gpt-5.4-nano` | OpenAI 側の高速・低コスト候補 |

## Cerebras fast primary

`FAST_LLM_PRIMARY_PROVIDER=cerebras` と `CEREBRAS_API_KEY` が設定されている場合、
`CEREBRAS_PRIMARY_USE_CASES` で許可された軽量レスポンス設定だけが Cerebras を先に試します。
既定値は `qa_response,general_knowledge,event_info,facility_info` です。
失敗時は既存の OpenRouter primary/fallback に戻ります。`none` で primary 利用を無効化できます。

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
    model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
    temperature=0.5,
    max_tokens=512,
    fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
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
    model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,  # プライマリ
    fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,  # 安定版フォールバック
    temperature=0.7,
)
```

### フォールバック動作の詳細

OpenRouterProviderは以下のエラーケースで自動的にフォールバックを試行します:

1. **HTTPステータスエラー**（500, 503など）:
   - プライマリモデルのAPI呼び出しが失敗
   - ログに `[OpenRouter] HTTP error (status XXX), trying fallback: ...` を出力
   - フォールバックモデルで再試行

2. **ネットワークエラー**（タイムアウト、接続エラーなど）:
   - ネットワーク障害でリクエストが完了しない
   - ログに `[OpenRouter] Network error, trying fallback: ...` を出力
   - フォールバックモデルで再試行

3. **無限ループ防止**:
   - 各リクエストで最大1回のフォールバック試行
   - `_fallback_count` パラメータで再帰呼び出しを制限
   - フォールバック後も失敗した場合は `OpenRouterError` を発生

### フォールバックの例

```python
# 例: Gemini 3.1 Flash-Lite preview → Gemini 2.5 Flash-Lite stable（OpenRouter フォールバック）
config = ModelConfig(
    model_id=SupportedModel.GEMINI_3_1_FLASH_LITE,
    fallback_model=SupportedModel.GEMINI_2_5_FLASH_LITE,
)

# プライマリモデル失敗時、自動的にフォールバックが試行される
try:
    response = await provider.generate(messages, config)
    # フォールバック成功 → レスポンスが返る
except OpenRouterError as e:
    # フォールバックも失敗 → エラーが発生
    print(f"Both primary and fallback failed: {e}")
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
