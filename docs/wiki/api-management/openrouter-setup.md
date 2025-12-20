# OpenRouter API 設定ガイド

## 概要

Engineer Cafe NavigatorはOpenRouter APIを使用して、複数のAIプロバイダー（OpenAI, Google, Anthropic等）を統一インターフェースで利用しています。

## APIキーの取得

### 1. OpenRouterアカウント作成

1. [OpenRouter](https://openrouter.ai/) にアクセス
2. GitHubまたはGoogleアカウントでログイン
3. ダッシュボードに移動

### 2. APIキーの生成

1. [API Keys](https://openrouter.ai/keys) ページに移動
2. 「Create Key」をクリック
3. キー名を入力（例: `engineer-cafe-navigator-dev`）
4. 生成されたキー（`sk-or-v1-...`）をコピー

### 3. 使用量制限の設定（推奨）

1. 「Settings」→「Billing」に移動
2. 月間予算を設定（推奨: $50〜100）
3. アラート閾値を設定（予算の80%でアラート）

## 環境変数の設定

### ローカル開発

```bash
# backend/.env
OPENROUTER_API_KEY=sk-or-v1-your-key-here
APP_URL=http://localhost:3000
```

### 本番環境

Vercel/Renderなどの環境変数設定画面で以下を設定:

| 変数名 | 値 | 説明 |
|--------|-----|------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | OpenRouter APIキー |
| `APP_URL` | `https://your-domain.com` | アプリケーションURL |

## 利用可能なモデル

| モデルID | 推奨用途 | コスト |
|----------|---------|-------|
| `google/gemini-2.5-flash-preview` | 高速応答、ルーティング | 低 |
| `openai/gpt-4o` | 複雑な推論 | 中 |
| `openai/gpt-4o-mini` | フォールバック | 低 |
| `anthropic/claude-3.5-sonnet` | 高品質応答 | 高 |

## 使用例

```python
from llm import get_llm_provider, MODEL_CONFIGS
from langchain_core.messages import HumanMessage

# プロバイダーを取得
provider = get_llm_provider()

# レスポンスを生成
response = await provider.generate(
    messages=[HumanMessage(content="こんにちは！")],
    config=MODEL_CONFIGS["qa_response"]
)
```

## フォールバック設定

プライマリモデルが失敗した場合、自動的にフォールバックモデルに切り替わります:

```python
from llm import ModelConfig, SupportedModel

config = ModelConfig(
    model_id=SupportedModel.GEMINI_2_5_FLASH,  # プライマリ
    fallback_model=SupportedModel.GPT_4O_MINI,  # フォールバック
    temperature=0.7,
)
```

## コスト管理

### 月間コスト目安

| 用途 | 想定リクエスト数 | 月間コスト |
|------|----------------|-----------|
| 開発環境 | 1,000/月 | $5〜10 |
| ステージング | 5,000/月 | $20〜40 |
| 本番環境 | 50,000/月 | $100〜200 |

### コスト削減のヒント

1. **ルーティングにはGemini Flash**を使用（高速・低コスト）
2. **フォールバックを設定**して高コストモデルの過剰使用を防止
3. **max_tokensを適切に設定**して不要な出力を制限
4. **キャッシュを活用**して重複リクエストを削減

## トラブルシューティング

### 401 Unauthorized

```
原因: APIキーが無効
対策:
1. キーが正しくコピーされているか確認
2. キーが有効期限内か確認
3. 環境変数が読み込まれているか確認
```

### 429 Rate Limit

```
原因: レート制限に達した
対策:
1. フォールバックモデルが設定されているか確認
2. リクエスト頻度を調整
3. プランのアップグレードを検討
```

### 500 Internal Server Error

```
原因: OpenRouterサービス側の問題
対策:
1. https://status.openrouter.ai/ でステータス確認
2. 数分待ってリトライ
3. 直接API（OpenAI等）への切り替えを検討
```

## セキュリティ

### 重要

- APIキーは絶対にGitにコミットしない
- `.env`ファイルは`.gitignore`に含める
- 本番キーと開発キーを分離する
- 定期的にキーをローテーションする

## 関連リンク

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [OpenRouter Models](https://openrouter.ai/docs#models)
- [OpenRouter Pricing](https://openrouter.ai/docs#pricing)
- [backend/llm/README.md](../../backend/llm/README.md)
