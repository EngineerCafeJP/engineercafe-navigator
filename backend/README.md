# Engineer Cafe Navigator Backend

Python版LangGraphを使用したAIエージェントバックエンドシステムです。

## セットアップ

### Poetryを使用する場合

```bash
cd backend
poetry install
poetry shell
```

### pipを使用する場合

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 環境変数の設定

`.env`ファイルを作成し、以下の環境変数を設定してください：

```env
# OpenRouter API (Required - Primary AI Provider)
# All AI models (Router, QA, etc.) use OpenRouter API
# Get your key at: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# その他
ENVIRONMENT=development
PORT=8000
APP_URL=http://localhost:3000
```

### フォールバック戦略

OpenRouter APIは自動フォールバック機能を持っています：

1. **HTTPエラー時**（500, 503など）:
   - プライマリモデル失敗 → フォールバックモデルに自動切り替え
   - 例: `GEMINI_3_FLASH` → `GEMINI_2_5_FLASH`

2. **ネットワークエラー時**（タイムアウト、接続エラーなど）:
   - フォールバックモデルを自動的に試行
   - 無限ループ防止のため、フォールバック試行は1回まで

3. **フォールバック回数制限**:
   - 各リクエストで最大1回のフォールバック試行
   - ログ出力でフォールバック発生を記録

詳細は `backend/llm/README.md` を参照してください。

## 実行

### 開発サーバーの起動

```bash
poetry run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

または

```bash
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## APIエンドポイント

- `GET /health` - ヘルスチェック
- `POST /api/chat` - チャットエンドポイント
- `POST /api/agent/invoke` - LangGraphエージェントの実行

## プロジェクト構造

```
backend/
├── main.py                 # FastAPIアプリケーション
├── agents/                 # LangGraphエージェント
│   ├── __init__.py
│   ├── router_agent.py
│   ├── business_info_agent.py
│   └── ...
├── workflows/              # LangGraphワークフロー
│   ├── __init__.py
│   └── main_workflow.py
├── tools/                  # エージェントツール
│   ├── __init__.py
│   └── ...
├── models/                 # データモデル
│   ├── __init__.py
│   └── ...
├── utils/                  # ユーティリティ
│   ├── __init__.py
│   └── ...
└── tests/                  # テスト
    └── ...
```

