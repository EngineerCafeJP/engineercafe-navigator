# OpenRouter API 使用チェックリスト

> **目的**: 全エージェントでOpenRouter APIを使用する統一実装の確認

## 📋 実装前チェック

### 環境設定
- [ ] `OPENROUTER_API_KEY`環境変数が設定されている
- [ ] `.env`ファイルに`OPENROUTER_API_KEY`が含まれている
- [ ] `langchain-google-genai`パッケージが削除されている（Gemini直接APIは使用禁止）
- [ ] `GOOGLE_API_KEY`環境変数の記述が削除されている

### 依存関係
- [ ] `requirements.txt`に`langchain-openai>=0.2.0`が含まれている
- [ ] `requirements.txt`に`httpx>=0.27.0`が含まれている
- [ ] `pyproject.toml`に適切なバージョン指定がある

## 🔧 実装チェック

### OpenRouterProvider使用
- [ ] `backend.llm.openrouter.OpenRouterProvider`をインポートしている
- [ ] `backend.llm.models.MODEL_CONFIGS`から適切な設定を取得している
- [ ] エージェント初期化時に`OpenRouterProvider`を使用している

### モデル設定
- [ ] `MODEL_CONFIGS`から適切なuse caseの設定を使用
  - `"router"`: RouterAgent用
  - `"qa_response"`: Q&A応答用
  - `"clarification"`: 曖昧さ解消用
  - `"facility_info"`: 施設情報用
  - `"event_info"`: イベント情報用
  - `"general_knowledge"`: 一般知識用
- [ ] カスタム設定が必要な場合、`ModelConfig`を使用している
- [ ] **2025/12最新モデル**を使用している（古いモデルIDは使用禁止）
  - ✅ `google/gemini-3-flash-preview` (推奨)
  - ✅ `google/gemini-2.5-flash-preview`
  - ❌ `google/gemini-2.0-flash-exp:free` (古い)
  - ❌ `google/gemini-flash-1.5` (古い)

### エラーハンドリング
- [ ] `OpenRouterError`例外を適切にキャッチしている
- [ ] フォールバックモデルが設定されている
- [ ] ネットワークエラー時のリトライロジックがある

### LangGraph統合
- [ ] `get_langchain_llm()`メソッドでLangChain互換LLMを取得
- [ ] LangGraphワークフローでChatOpenAIインスタンスを使用
- [ ] メッセージ変換が正しく動作している

## ✅ テストチェック

### 単体テスト
- [ ] OpenRouterProvider初期化テスト
- [ ] API呼び出しテスト（モック使用）
- [ ] エラーハンドリングテスト
- [ ] フォールバックテスト

### 統合テスト
- [ ] 実際のOpenRouter APIとの疎通確認
- [ ] 各use caseでの応答品質確認
- [ ] レスポンス時間測定

### 動作確認
- [ ] 開発環境での動作確認
- [ ] ログに適切な情報が出力されている
- [ ] エラー時のフォールバックが動作している

## 📝 ドキュメントチェック

### コード内ドキュメント
- [ ] docstringにOpenRouter使用が明記されている
- [ ] 使用するモデルが記載されている
- [ ] エラーハンドリングの説明がある

### README/ドキュメント
- [ ] `backend/README.md`の環境変数セクションが更新されている
- [ ] Gemini直接APIの記述が削除されている
- [ ] OpenRouter APIの設定手順が記載されている

## 🚀 デプロイ前チェック

### CI/CD
- [ ] `ruff check .`がパスする
- [ ] `black --check .`がパスする
- [ ] 型チェック（mypy）がパスする
- [ ] 全テストがパスする

### 環境変数
- [ ] 本番環境に`OPENROUTER_API_KEY`が設定されている
- [ ] `GOOGLE_API_KEY`が削除されている（または未使用）
- [ ] `APP_URL`が正しく設定されている

### モニタリング
- [ ] OpenRouter API呼び出しのログが適切に記録される
- [ ] エラー率のモニタリングが設定されている
- [ ] コスト追跡が有効になっている

## ⚠️ 禁止事項

### 使用禁止
- ❌ `langchain-google-genai`パッケージの使用
- ❌ Gemini APIへの直接アクセス
- ❌ `GOOGLE_API_KEY`環境変数の使用
- ❌ 古いモデルID（`gemini-flash-1.5`など）の使用

### 非推奨パターン
- ⚠️ ハードコーディングされたモデルID（`MODEL_CONFIGS`を使用すること）
- ⚠️ エラーハンドリングなしのAPI呼び出し
- ⚠️ フォールバックモデルの未設定

## 📊 完了基準

以下の全てが満たされていることを確認:

1. ✅ 全ての依存関係チェックが完了
2. ✅ OpenRouterProvider実装が正しい
3. ✅ 全てのテストがパス
4. ✅ CI/CDがグリーン
5. ✅ ドキュメントが最新
6. ✅ 本番環境変数が設定済み

## 🔗 参考リンク

- [OpenRouter公式ドキュメント](https://openrouter.ai/docs)
- [OpenRouterモデル一覧](https://openrouter.ai/docs#models)
- [backend/llm/openrouter.py](../../../backend/llm/openrouter.py) - 実装例
- [backend/llm/models.py](../../../backend/llm/models.py) - モデル設定
- [OpenRouter APIベストプラクティス](./openrouter-best-practices.md)
