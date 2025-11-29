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
# OpenAI API
OPENAI_API_KEY=your_openai_api_key

# Google Gemini API
GOOGLE_API_KEY=your_google_api_key

# Supabase
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

# その他
ENVIRONMENT=development
```

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

