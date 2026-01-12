# Troubleshooting Guide

> エージェント実装時に遭遇する典型的な問題と解決方法の完全ガイド

**最終更新**: 2026-01-13

---

## 目次

1. [環境構築関連](#1-環境構築関連)
2. [API/外部サービス関連](#2-api外部サービス関連)
3. [エージェント実装関連](#3-エージェント実装関連)
4. [テスト関連](#4-テスト関連)
5. [ビルド/デプロイ関連](#5-ビルドデプロイ関連)
6. [デバッグツール活用](#6-デバッグツール活用)
7. [よくあるエラーメッセージ集](#7-よくあるエラーメッセージ集)

---

## 1. 環境構築関連

### 1.1 mise のインストール/セットアップエラー

#### 症状
```bash
$ make setup
mise: command not found
```

#### 原因
mise がインストールされていないか、PATHが通っていない。

#### 解決方法

**macOS (Homebrew)**:
```bash
brew install mise
```

**Linux/WSL**:
```bash
curl https://mise.run | sh
echo 'eval "$(mise activate bash)"' >> ~/.bashrc
source ~/.bashrc
```

**確認コマンド**:
```bash
mise --version
# Expected: mise 2024.x.x
```

#### 参考資料
- [mise 公式ドキュメント](https://mise.jdx.dev/)

---

### 1.2 Python/Node.js バージョンミスマッチ

#### 症状
```bash
$ cd backend && mise exec -- python --version
Python 3.12.0  # Expected: 3.11.10
```

#### 原因
`.mise.toml` で指定されたバージョンがインストールされていない、または mise の自動切り替えが有効になっていない。

#### 解決方法

**Step 1: 必要なバージョンをインストール**
```bash
cd /path/to/engineer-cafe-navigator2025
mise install
```

**Step 2: バージョン確認**
```bash
mise current
# Expected output:
# node    18.20.0  ~/.local/share/mise/installs/node/18.20.0/bin/node
# python  3.11.10  ~/.local/share/mise/installs/python/3.11.10/bin/python
# pnpm    10.12.1  ~/.local/share/mise/installs/pnpm/10.12.1/bin/pnpm
```

**Step 3: mise の自動有効化設定**
```bash
# ~/.bashrc または ~/.zshrc に追加
echo 'eval "$(mise activate bash)"' >> ~/.bashrc  # bash の場合
# または
echo 'eval "$(mise activate zsh)"' >> ~/.zshrc   # zsh の場合

# 再読み込み
source ~/.bashrc  # or ~/.zshrc
```

**確認コマンド**:
```bash
cd backend
python --version  # 3.11.10
cd ../frontend
node --version    # 18.20.0
pnpm --version    # 10.12.1
```

#### 参考資料
- [.mise.toml](../../.mise.toml)

---

### 1.3 Docker のセットアップエラー

#### 症状
```bash
$ make dev
Cannot connect to the Docker daemon at unix:///var/run/docker.sock.
Is the docker daemon running?
```

#### 原因
Docker Desktop が起動していない、またはインストールされていない。

#### 解決方法

**Step 1: Docker Desktop のインストール確認**
```bash
# macOS
brew install --cask docker

# または Docker 公式サイトからダウンロード
# https://www.docker.com/products/docker-desktop/
```

**Step 2: Docker Desktop の起動**
- アプリケーションから「Docker」を起動
- メニューバーに Docker アイコンが表示されるまで待つ

**Step 3: Docker 動作確認**
```bash
docker --version
# Docker version 24.x.x

docker ps
# CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```

**確認コマンド**:
```bash
make dev
# Frontend/Backend コンテナが起動すれば成功
```

---

### 1.4 依存関係のインストール失敗

#### 症状 (Backend)
```bash
$ cd backend && mise exec -- pip install -r requirements.txt
ERROR: Could not find a version that satisfies the requirement langgraph>=0.2.0
```

#### 原因
- Python バージョンが古い
- pip が最新でない
- ネットワークエラー

#### 解決方法

**Step 1: Python バージョン確認**
```bash
cd backend
mise exec -- python --version
# Should be: 3.11.10
```

**Step 2: pip のアップグレード**
```bash
mise exec -- python -m pip install --upgrade pip
```

**Step 3: 依存関係の再インストール**
```bash
mise exec -- pip install -r requirements.txt
```

**プロキシ環境の場合**:
```bash
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
mise exec -- pip install -r requirements.txt
```

**確認コマンド**:
```bash
mise exec -- python -c "import langgraph; print(langgraph.__version__)"
# Expected: 0.2.x
```

---

#### 症状 (Frontend)
```bash
$ cd frontend && pnpm install
ERR_PNPM_OUTDATED_LOCKFILE
```

#### 原因
- `pnpm-lock.yaml` が古い
- pnpm バージョンミスマッチ

#### 解決方法

**Step 1: pnpm バージョン確認**
```bash
mise exec -- pnpm --version
# Should be: 10.12.1
```

**Step 2: lockfile の更新**
```bash
cd frontend
mise exec -- pnpm install --no-frozen-lockfile
```

**それでも失敗する場合 (クリーンインストール)**:
```bash
cd frontend
rm -rf node_modules pnpm-lock.yaml
mise exec -- pnpm install
```

---

### 1.5 環境変数の設定ミス

#### 症状
```bash
$ make dev
ValueError: OpenRouter API key not found.
```

#### 原因
`.env` ファイルが存在しない、または必須の環境変数が設定されていない。

#### 解決方法

**Step 1: .env ファイルの作成**
```bash
# Backend
cd backend
cp .env.example .env

# Frontend (必要な場合)
cd ../frontend
cp .env.example .env.local
```

**Step 2: 必須環境変数の設定**

backend/.env:
```bash
# 必須
OPENROUTER_API_KEY=sk-or-v1-your-actual-key
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=your-service-role-key
OPENAI_API_KEY=sk-your-openai-key

# オプション
GOOGLE_API_KEY=your-google-api-key  # EventAgent で使用
GOOGLE_CALENDAR_ID=xxx@group.calendar.google.com  # EventAgent で使用

ENVIRONMENT=development
PORT=8000
APP_URL=http://localhost:3000
```

**Step 3: 環境変数の読み込み確認**
```bash
cd backend
mise exec -- python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('OPENROUTER_API_KEY:', os.getenv('OPENROUTER_API_KEY')[:20])"
# Should output: OPENROUTER_API_KEY: sk-or-v1-xxxxxxxxxxxx
```

**確認コマンド**:
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
load_dotenv()

required_vars = ['OPENROUTER_API_KEY', 'SUPABASE_URL', 'SUPABASE_KEY', 'OPENAI_API_KEY']
for var in required_vars:
    value = os.getenv(var)
    if value:
        masked = value[:8] + '...' + value[-4:] if len(value) > 12 else '***'
        print(f'{var}: {masked}')
    else:
        print(f'{var}: NOT SET ⚠️')
"
```

#### 参考資料
- [ENVIRONMENT-VARIABLES.md](./ENVIRONMENT-VARIABLES.md)
- [backend/.env.example](../../backend/.env.example)

---

### 1.6 ポート競合エラー

#### 症状
```bash
$ make dev
Error starting userland proxy: listen tcp4 0.0.0.0:3000: bind: address already in use
```

#### 原因
既に別のプロセスが同じポートを使用している。

#### 解決方法

**Step 1: ポート使用状況の確認**
```bash
# macOS/Linux
lsof -i :3000  # Frontend
lsof -i :8000  # Backend

# 出力例:
# COMMAND   PID  USER   FD   TYPE DEVICE SIZE/OFF NODE NAME
# node    12345  user   21u  IPv4 123456      0t0  TCP *:3000 (LISTEN)
```

**Step 2: プロセスの終了**
```bash
# PID を使って終了
kill -9 12345

# または、ポート番号で一括終了 (macOS/Linux)
lsof -ti :3000 | xargs kill -9
lsof -ti :8000 | xargs kill -9
```

**Step 3: Docker コンテナのクリーンアップ**
```bash
make clean
# または
docker-compose down
```

**確認コマンド**:
```bash
lsof -i :3000  # 何も出力されなければOK
lsof -i :8000  # 何も出力されなければOK
make dev
```

---

## 2. API/外部サービス関連

### 2.1 OpenRouter API エラー

#### 症状 1: 認証エラー
```
openrouter.exceptions.AuthenticationError: Invalid API key
```

#### 原因
- API キーが間違っている
- API キーの形式が不正 (`sk-or-v1-` で始まっていない)
- キーの有効期限切れ

#### 解決方法

**Step 1: API キーの確認**
```bash
cd backend
grep OPENROUTER_API_KEY .env
# Expected format: OPENROUTER_API_KEY=sk-or-v1-xxxxxxxx
```

**Step 2: API キーの再取得**
1. [OpenRouter](https://openrouter.ai/keys) にアクセス
2. GitHubまたはGoogleでサインイン
3. 既存のキーを確認、または新規作成
4. `.env` ファイルを更新

**Step 3: 接続テスト**
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
import httpx

load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')

headers = {
    'Authorization': f'Bearer {api_key}',
    'HTTP-Referer': 'http://localhost:3000',
}

response = httpx.get('https://openrouter.ai/api/v1/models', headers=headers)
print(f'Status: {response.status_code}')
if response.status_code == 200:
    print('✓ API Key is valid')
else:
    print('✗ API Key is invalid:', response.text)
"
```

---

#### 症状 2: レート制限エラー
```
openrouter.exceptions.RateLimitError: Rate limit exceeded
```

#### 原因
- 無料枠のクレジットを使い果たした
- 短時間に大量のリクエストを送信

#### 解決方法

**Step 1: 使用状況の確認**
1. [OpenRouter Dashboard](https://openrouter.ai/activity) にアクセス
2. Usage タブでクレジット残高を確認

**Step 2: 対処方法**
- 無料クレジットが尽きた場合: 有料プランへのアップグレード
- レート制限の場合: リクエスト間隔を調整

**Step 3: リトライロジックの実装 (開発時)**
```python
import time
from openrouter import OpenRouterError, RateLimitError

max_retries = 3
for attempt in range(max_retries):
    try:
        response = await llm_provider.generate(...)
        break
    except RateLimitError:
        if attempt < max_retries - 1:
            wait_time = 2 ** attempt  # Exponential backoff
            print(f"Rate limited. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise
```

---

#### 症状 3: モデル選択エラー
```
ValueError: Model 'google/gemini-2.5-flash-preview' not found
```

#### 原因
- モデル名が間違っている
- モデルが OpenRouter で利用不可

#### 解決方法

**Step 1: 利用可能なモデルの確認**
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
import httpx

load_dotenv()
api_key = os.getenv('OPENROUTER_API_KEY')

headers = {
    'Authorization': f'Bearer {api_key}',
}

response = httpx.get('https://openrouter.ai/api/v1/models', headers=headers)
models = response.json()

# Google モデルのみ表示
google_models = [m for m in models.get('data', []) if 'google' in m.get('id', '').lower()]
for model in google_models[:10]:
    print(f\"{model.get('id')}\")
"
```

**Step 2: backend/llm/models.py を確認**
```bash
cat backend/llm/models.py | grep -A5 "MODEL_CONFIGS"
```

**Step 3: .env でモデルをオーバーライド (オプション)**
```bash
# backend/.env
DEFAULT_ROUTER_MODEL=google/gemini-2.0-flash-exp
DEFAULT_QA_MODEL=google/gemini-2.0-flash-exp
```

#### 参考資料
- [OpenRouter Models](https://openrouter.ai/models)
- [backend/llm/models.py](../../backend/llm/models.py)

---

### 2.2 Supabase 接続エラー

#### 症状
```
supabase.exceptions.AuthApiError: Invalid API key
```

#### 原因
- Supabase が起動していない (ローカル開発)
- SUPABASE_KEY が間違っている
- Service Role Key ではなく Anon Key を使用している

#### 解決方法 (ローカル開発)

**Step 1: Supabase CLI のインストール**
```bash
npm install -g supabase
# または
brew install supabase/tap/supabase
```

**Step 2: Supabase の起動**
```bash
cd /path/to/engineer-cafe-navigator2025
supabase start
```

**Step 3: 表示された接続情報を .env に設定**
```
Started supabase local development setup.

         API URL: http://127.0.0.1:54321
     GraphQL URL: http://127.0.0.1:54321/graphql/v1
  S3 Storage URL: http://127.0.0.1:54321/storage/v1/s3
          DB URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
      Studio URL: http://127.0.0.1:54323
    Inbucket URL: http://127.0.0.1:54324
      JWT secret: xxx
        anon key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
service_role key: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # これを使う!
   S3 Access Key: xxx
   S3 Secret Key: xxx
       S3 Region: local
```

backend/.env:
```bash
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...  # service_role key
```

**確認コマンド**:
```bash
cd backend
mise exec -- python -c "
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
url = os.getenv('SUPABASE_URL')
key = os.getenv('SUPABASE_KEY')

client = create_client(url, key)
response = client.table('conversation_sessions').select('*').limit(1).execute()
print('✓ Supabase connection successful')
print(f'Response: {response}')
"
```

---

#### 解決方法 (クラウド Supabase)

**Step 1: Supabase プロジェクトの作成**
1. [Supabase](https://supabase.com/) にアクセス
2. 新しいプロジェクトを作成

**Step 2: 接続情報の取得**
1. Settings → API
2. Project URL → `SUPABASE_URL`
3. Project API keys → service_role (secret) → `SUPABASE_KEY`

**注意**: `service_role` キーは強力な権限を持つため、**絶対に公開リポジトリにコミットしない**こと！

---

### 2.3 OpenAI Embeddings エラー

#### 症状
```
openai.error.AuthenticationError: Incorrect API key provided
```

#### 原因
- OpenAI API キーが設定されていない
- キーが間違っている
- クレジットがない

#### 解決方法

**Step 1: API キーの取得**
1. [OpenAI Platform](https://platform.openai.com/) にログイン
2. [API Keys](https://platform.openai.com/api-keys) にアクセス
3. "Create new secret key" をクリック
4. キーをコピー (`sk-` で始まる)

**Step 2: .env に設定**
```bash
# backend/.env
OPENAI_API_KEY=sk-proj-your-actual-key-here
```

**Step 3: クレジット残高の確認**
1. [Usage](https://platform.openai.com/usage) ページにアクセス
2. クレジットが残っているか確認
3. 残高がない場合: [Billing](https://platform.openai.com/account/billing) で支払い設定

**確認コマンド**:
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# テストクエリ
response = client.embeddings.create(
    input='test query',
    model='text-embedding-3-small'
)

print('✓ OpenAI Embeddings working')
print(f'Embedding dimension: {len(response.data[0].embedding)}')  # Should be 1536
"
```

---

### 2.4 Google Cloud API エラー

#### 症状 1: Calendar API エラー
```
[CalendarService] Calendar ID or API Key not configured
```

#### 原因
- Google Calendar API キーが設定されていない
- Calendar API が有効化されていない

#### 解決方法

**Step 1: Google Cloud プロジェクトの作成**
1. [Google Cloud Console](https://console.cloud.google.com/) にアクセス
2. 新しいプロジェクトを作成

**Step 2: Calendar API の有効化**
1. APIs & Services → Library
2. "Google Calendar API" を検索
3. "Enable" をクリック

**Step 3: API キーの作成**
1. APIs & Services → Credentials
2. "Create Credentials" → "API Key"
3. 生成されたキーをコピー

**Step 4: Calendar ID の取得**
1. [Google Calendar](https://calendar.google.com/) にアクセス
2. 対象カレンダーの設定を開く
3. "Integrate calendar" → "Calendar ID" をコピー

**Step 5: .env に設定**
```bash
# backend/.env
GOOGLE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
GOOGLE_CALENDAR_ID=xxx@group.calendar.google.com
```

**確認コマンド**:
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
from tools.calendar_service import CalendarService

load_dotenv()
service = CalendarService()
events = service.get_upcoming_events(max_results=5)
print(f'✓ Found {len(events)} events')
for event in events:
    print(f'  - {event.get(\"summary\")}: {event.get(\"start\", {}).get(\"dateTime\")}')
"
```

---

#### 症状 2: 認証エラー (Service Account)
```
google.auth.exceptions.DefaultCredentialsError: Could not automatically determine credentials.
```

#### 原因
- `GOOGLE_APPLICATION_CREDENTIALS` が設定されていない
- サービスアカウントキーのJSONファイルが存在しない

#### 解決方法

**Step 1: サービスアカウントの作成**
1. [Google Cloud Console](https://console.cloud.google.com/)
2. IAM & Admin → Service Accounts
3. "Create Service Account"
4. 必要なロールを付与:
   - Cloud Speech-to-Text API User
   - Cloud Text-to-Speech API User
   - Cloud Vision API User

**Step 2: JSONキーのダウンロード**
1. 作成したサービスアカウントの詳細ページ
2. "Keys" タブ → "Add Key" → "Create new key" → "JSON"
3. ダウンロードされた JSON ファイルを安全な場所に保存

**Step 3: 環境変数の設定**
```bash
# backend/.env
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

**Step 4: 必要なAPIの有効化**
```bash
# gcloud CLI がインストールされている場合
gcloud services enable speech.googleapis.com
gcloud services enable texttospeech.googleapis.com
gcloud services enable vision.googleapis.com
```

**確認コマンド**:
```bash
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
from google.cloud import speech

load_dotenv()
client = speech.SpeechClient()
print('✓ Google Cloud credentials are valid')
"
```

#### 参考資料
- [ENVIRONMENT-VARIABLES.md](./ENVIRONMENT-VARIABLES.md)

---

## 3. エージェント実装関連

### 3.1 RAG検索結果が空

#### 症状
```python
rag_result = await self.enhanced_rag.search(query="営業時間は？")
# {'success': True, 'data': {'context': '', 'totalResults': 0}}
```

#### 原因
- Supabase の knowledge_base テーブルにデータがない
- エンベディング次元の不一致 (1536 dimensions expected)
- クエリと知識ベースの言語ミスマッチ

#### 解決方法

**Step 1: knowledge_base テーブルの確認**
```bash
cd backend
mise exec -- python -c "
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

response = client.table('knowledge_base').select('count').execute()
print(f'Knowledge base entries: {len(response.data)}')

# サンプルデータを表示
sample = client.table('knowledge_base').select('*').limit(3).execute()
for item in sample.data:
    print(f\"  - {item.get('title')} ({item.get('language')})\")
"
```

**Step 2: データがない場合 (知識ベースのセットアップ)**

データインポート方法については、プロジェクトのセットアップガイドを参照してください。

**Step 3: エンベディング次元の確認**
```bash
cd backend
mise exec -- python -c "
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

sample = client.table('knowledge_base').select('embedding').limit(1).execute()
if sample.data:
    embedding = sample.data[0].get('embedding')
    print(f'Embedding dimension: {len(embedding)}')
    if len(embedding) != 1536:
        print('⚠️ WARNING: Expected 1536 dimensions for OpenAI text-embedding-3-small')
else:
    print('⚠️ No data in knowledge_base')
"
```

**Step 4: 検索クエリのデバッグ**
```bash
make debug-agent AGENT=business_info QUERY="営業時間は？" VERBOSE=1
```

#### 参考資料
- [AGENT-QUICKSTART.md](./AGENT-QUICKSTART.md#3-エージェント実装テンプレート-10分)

---

### 3.2 LLMレスポンスが期待と異なる

#### 症状
- 応答が短すぎる/長すぎる
- 感情タグが正しく付いていない
- 関係ない情報を含んでいる

#### 原因
- プロンプトが不適切
- モデル設定 (temperature, max_tokens) が不適切
- コンテキストに不要な情報が含まれている

#### 解決方法

**Step 1: プロンプトの改善**

悪い例:
```python
prompt = f"質問に答えて。質問: {query} 情報: {context}"
```

良い例:
```python
prompt = f"""提供された情報を使って質問に答えてください。

質問: {query}
情報: {context}

簡潔で役立つ回答を提供してください。最大2-3文。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""
```

**Step 2: モデル設定の調整**

backend/llm/models.py:
```python
MODEL_CONFIGS = {
    "qa_response": ModelConfig(
        provider="openrouter",
        model_name="google/gemini-2.5-flash-preview",
        temperature=0.3,  # 低い値 = 一貫性重視、高い値 = 創造性重視
        max_tokens=300,   # 応答の最大長
        top_p=0.9,
    ),
}
```

**Step 3: コンテキストフィルタリング**

```python
# RAG結果から不要な情報を除外
def _filter_context(self, context: str, request_type: str) -> str:
    """リクエストタイプに基づいてコンテキストをフィルタリング"""
    if request_type == "hours":
        # 営業時間に関する情報のみ抽出
        relevant_lines = [
            line for line in context.split('\n')
            if any(keyword in line for keyword in ['営業時間', '開店', '閉店', 'hours', 'open', 'close'])
        ]
        return '\n'.join(relevant_lines)
    return context
```

**確認コマンド**:
```bash
# デバッグモードでプロンプトとレスポンスを確認
make debug-agent AGENT=business_info QUERY="営業時間は？" VERBOSE=1
```

---

### 3.3 エージェントの応答が遅い

#### 症状
- レスポンスタイムが 5秒以上
- タイムアウトエラーが発生

#### 原因
- RAG検索に時間がかかっている (max_results が多すぎる)
- LLM の max_tokens が大きすぎる
- 並列処理が適切でない

#### 解決方法

**Step 1: RAG検索の最適化**

```python
# 悪い例: max_results=50 は遅い
rag_result = await self.enhanced_rag.search(
    query=query,
    max_results=50  # Too many!
)

# 良い例: 必要最小限の結果数
rag_result = await self.enhanced_rag.search(
    query=query,
    max_results=5  # Optimal for most cases
)
```

**Step 2: タイムアウトの設定**

```python
import asyncio

async def answer_query_with_timeout(self, query: str, timeout: int = 10):
    """タイムアウト付きでクエリに回答"""
    try:
        return await asyncio.wait_for(
            self.answer_query(query),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        print(f"[Agent] Timeout after {timeout}s")
        return self._get_default_response()
```

**Step 3: LLM設定の最適化**

```python
config = ModelConfig(
    provider="openrouter",
    model_name="google/gemini-2.5-flash-preview",  # Fast model
    temperature=0.3,
    max_tokens=200,  # 短い応答で高速化
    top_p=0.9,
)
```

**Step 4: パフォーマンス測定**

```python
import time

async def answer_query(self, query: str):
    start_time = time.time()

    # RAG検索
    rag_start = time.time()
    rag_result = await self.enhanced_rag.search(query)
    rag_time = time.time() - rag_start
    print(f"[Perf] RAG search: {rag_time:.2f}s")

    # LLM生成
    llm_start = time.time()
    response = await self.llm_provider.generate(...)
    llm_time = time.time() - llm_start
    print(f"[Perf] LLM generation: {llm_time:.2f}s")

    total_time = time.time() - start_time
    print(f"[Perf] Total: {total_time:.2f}s")

    return response
```

**確認コマンド**:
```bash
# 複数回実行して平均時間を確認
for i in {1..5}; do
  echo "=== Run $i ==="
  make test-agent AGENT=business_info QUERY="営業時間は？"
done
```

---

### 3.4 メモリ/セッション管理の問題

#### 症状
- 同じセッションで前の会話が参照されない
- `session_id` が正しく伝播されない
- メモリが保存されない

#### 原因
- `session_id` が各関数呼び出しで欠落している
- メモリの TTL (有効期限) が切れている
- Supabase の `agent_memory` テーブルへの書き込み失敗

#### 解決方法

**Step 1: session_id の伝播確認**

```python
# ワークフローノード内で session_id を確実に渡す
async def _business_info_node(self, state: WorkflowState) -> dict:
    agent = BusinessInfoAgent()

    # session_id の取得
    session_id = state.get("session_id", "")

    # ログで確認
    print(f"[WorkflowNode] session_id: {session_id}")

    result = await agent.answer_business_query(
        query=state.get("query", ""),
        session_id=session_id,  # 確実に渡す
    )

    return result
```

**Step 2: メモリの確認**

```bash
cd backend
mise exec -- python -c "
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv()
client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# 最近のメモリエントリを表示
response = client.table('agent_memory') \
    .select('*') \
    .order('created_at', desc=True) \
    .limit(10) \
    .execute()

print(f'Recent memory entries: {len(response.data)}')
for entry in response.data:
    print(f\"  - {entry.get('agent_name')}: {entry.get('key')[:30]}...\")
"
```

**Step 3: メモリのTTL延長 (必要な場合)**

デフォルトのTTLは3分です。これを変更したい場合:

```python
# SimplifiedMemorySystem の初期化時
from lib.simplified_memory import SimplifiedMemorySystem

memory = SimplifiedMemorySystem(
    agent_name="YourAgent",
    ttl_seconds=600  # 10分に延長
)
```

**確認コマンド**:
```bash
# セッション継続のテスト
SESSION_ID="test-session-$(date +%s)"

# 1回目の質問
make test-agent AGENT=business_info QUERY="営業時間は？" SESSION_ID="$SESSION_ID"

# 2回目の質問 (メモリを参照するはず)
make test-agent AGENT=business_info QUERY="さっき何を聞いた？" SESSION_ID="$SESSION_ID"
```

---

## 4. テスト関連

### 4.1 pytest 実行エラー

#### 症状
```bash
$ cd backend && mise exec -- pytest
ModuleNotFoundError: No module named 'pytest'
```

#### 原因
- pytest がインストールされていない
- mise の Python 環境が正しくない

#### 解決方法

**Step 1: pytest のインストール確認**
```bash
cd backend
mise exec -- pip list | grep pytest
# Expected:
# pytest             8.x.x
# pytest-asyncio     0.23.x
```

**Step 2: インストールされていない場合**
```bash
cd backend
mise exec -- pip install pytest pytest-asyncio
```

**Step 3: テスト実行**
```bash
mise exec -- pytest tests/ -v
```

---

### 4.2 モックの設定ミス

#### 症状
```python
# テストコード
agent.enhanced_rag.search = AsyncMock(return_value={...})

# エラー
AttributeError: 'EnhancedRAGSearch' object attribute 'search' is read-only
```

#### 原因
- モックの設定方法が間違っている
- `unittest.mock` の使い方が不適切

#### 解決方法

**正しいモックの設定方法**:

```python
import pytest
from unittest.mock import AsyncMock, patch
from agents.business_info_agent import BusinessInfoAgent

class TestBusinessInfoAgent:
    @pytest.mark.asyncio
    async def test_answer_business_query(self):
        agent = BusinessInfoAgent()

        # 方法1: patch デコレータ
        with patch.object(agent.enhanced_rag, 'search', new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {
                "success": True,
                "data": {"context": "テストコンテキスト"}
            }

            result = await agent.answer_business_query("営業時間は？")

            # アサーション
            assert result["answer"] is not None
            mock_search.assert_called_once()

        # 方法2: 直接設定 (推奨)
        agent.enhanced_rag.search = AsyncMock(return_value={
            "success": True,
            "data": {"context": "テストコンテキスト"}
        })

        agent.llm_provider.generate = AsyncMock(
            return_value="[relaxed]営業時間は9:00〜22:00です。"
        )

        result = await agent.answer_business_query("営業時間は？")
        assert "9:00" in result["answer"]
```

---

### 4.3 カバレッジが上がらない

#### 症状
```bash
$ mise exec -- pytest --cov=agents tests/
Coverage: 45%
```

#### 原因
- テストケースが不足している
- エラーハンドリングのパスがテストされていない

#### 解決方法

**Step 1: カバレッジレポートの詳細確認**
```bash
cd backend
mise exec -- pytest --cov=agents --cov-report=html tests/
open htmlcov/index.html  # ブラウザで詳細を確認
```

**Step 2: 未カバーの箇所を特定**

赤くハイライトされている行がテストされていない箇所です。

**Step 3: エラーケースのテスト追加**

```python
@pytest.mark.asyncio
async def test_answer_business_query_rag_failure(self):
    """RAG検索失敗時のテスト"""
    agent = BusinessInfoAgent()

    # RAG検索が失敗するようモック
    agent.enhanced_rag.search = AsyncMock(return_value={"success": False})

    result = await agent.answer_business_query("営業時間は？")

    # デフォルトレスポンスが返されることを確認
    assert result["metadata"]["sources"] == ["fallback"]
    assert result["emotion"] == "sad"

@pytest.mark.asyncio
async def test_answer_business_query_llm_error(self):
    """LLMエラー時のテスト"""
    agent = BusinessInfoAgent()

    agent.enhanced_rag.search = AsyncMock(return_value={
        "success": True,
        "data": {"context": "テスト"}
    })

    # LLM生成が失敗するようモック
    agent.llm_provider.generate = AsyncMock(side_effect=Exception("LLM Error"))

    result = await agent.answer_business_query("営業時間は？")

    # エラーハンドリングされていることを確認
    assert result["metadata"]["sources"] == ["fallback"]
```

**確認コマンド**:
```bash
mise exec -- pytest --cov=agents --cov-report=term-missing tests/
# Missing lines が減っていることを確認
```

---

### 4.4 CI/CD 失敗 (ruff, black, mypy)

#### 症状 (GitHub Actions)
```
Run ruff check .
backend/agents/your_agent.py:42:81: E501 Line too long (105 > 100 characters)
Error: Process completed with exit code 1.
```

#### 原因
- コードが ruff/black のルールに従っていない
- 型ヒントが不足している (mypy)

#### 解決方法

**Step 1: ローカルでリンターを実行**
```bash
cd backend

# Ruff チェック
mise exec -- ruff check .

# 自動修正
mise exec -- ruff check . --fix

# Black フォーマット
mise exec -- black .

# 型チェック (設定されているモジュールのみ)
mise exec -- mypy agents/
```

**Step 2: よくあるエラーと修正**

**E501: Line too long**
```python
# 悪い例 (105文字)
prompt = f"""提供された情報を使って質問に答えてください。質問: {query} 情報: {context} 簡潔に回答してください。"""

# 良い例 (複数行に分割)
prompt = f"""提供された情報を使って質問に答えてください。

質問: {query}
情報: {context}

簡潔に回答してください。"""
```

**F401: Unused import**
```python
# 悪い例
from typing import Dict, Optional, List  # List が未使用

# 良い例
from typing import Dict, Optional
```

**Type hints missing**
```python
# 悪い例
def process_query(query):
    return query.lower()

# 良い例
def process_query(query: str) -> str:
    return query.lower()
```

**Step 3: pre-commit hook のセットアップ (オプション)**

```bash
# .git/hooks/pre-commit を作成
cat > .git/hooks/pre-commit << 'EOF'
#!/bin/bash
cd backend
mise exec -- ruff check . --fix
mise exec -- black .
git add -u
EOF

chmod +x .git/hooks/pre-commit
```

**確認コマンド**:
```bash
# CI と同じチェックをローカルで実行
cd backend
mise exec -- ruff check .
mise exec -- black --check .
echo "✓ All lint checks passed!"
```

#### 参考資料
- [.github/workflows/ci.yml](../../.github/workflows/ci.yml)
- [backend/pyproject.toml](../../backend/pyproject.toml)

---

## 5. ビルド/デプロイ関連

### 5.1 TypeScript ビルドエラー

#### 症状
```bash
$ cd frontend && pnpm build
Error: Type error: Property 'xxx' does not exist on type 'YYY'
```

#### 原因
- TypeScript の型定義が不足/不正確
- 依存関係のバージョンミスマッチ

#### 解決方法

**Step 1: 型エラーの詳細確認**
```bash
cd frontend
mise exec -- pnpm typecheck
```

**Step 2: 型定義の追加/修正**

```typescript
// 悪い例
const data = response.data;
data.someProperty  // エラー!

// 良い例: 型を明示
interface ResponseData {
  someProperty: string;
}

const data = response.data as ResponseData;
data.someProperty  // OK
```

**Step 3: 依存関係の再インストール**
```bash
cd frontend
rm -rf node_modules pnpm-lock.yaml
mise exec -- pnpm install
```

**確認コマンド**:
```bash
cd frontend
mise exec -- pnpm typecheck
mise exec -- pnpm build
```

---

### 5.2 Next.js 起動エラー

#### 症状
```bash
$ cd frontend && pnpm dev
Error: Cannot find module 'next/dist/...'
```

#### 原因
- Next.js のビルドキャッシュが壊れている
- node_modules が不完全

#### 解決方法

**Step 1: キャッシュのクリア**
```bash
cd frontend
rm -rf .next node_modules pnpm-lock.yaml
```

**Step 2: 依存関係の再インストール**
```bash
mise exec -- pnpm install
```

**Step 3: 開発サーバーの起動**
```bash
mise exec -- pnpm dev
```

**確認コマンド**:
```bash
# ブラウザで http://localhost:3000 にアクセスして確認
curl http://localhost:3000
```

---

### 5.3 Docker Compose 起動エラー

#### 症状
```bash
$ make dev
ERROR: Service 'backend' failed to build
```

#### 原因
- Dockerfile の構文エラー
- ベースイメージが取得できない
- ビルドコンテキストに不要なファイルが含まれている

#### 解決方法

**Step 1: ビルドログの詳細確認**
```bash
docker-compose build --no-cache backend
```

**Step 2: .dockerignore の確認**

backend/.dockerignore:
```
__pycache__
*.pyc
.env
.venv
*.log
.pytest_cache
.ruff_cache
```

**Step 3: ベースイメージの確認**

backend/Dockerfile:
```dockerfile
# 正しいPythonバージョンを使用
FROM python:3.11-slim

WORKDIR /app

# 依存関係のインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードのコピー
COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
```

**Step 4: クリーンビルド**
```bash
make clean
docker-compose build --no-cache
make dev
```

**確認コマンド**:
```bash
docker ps
# backend と frontend のコンテナが Running になっているか確認
```

---

### 5.4 ポート競合 (再掲)

前述の [1.6 ポート競合エラー](#16-ポート競合エラー) を参照してください。

---

## 6. デバッグツール活用

### 6.1 debug_agent.py の使い方

`backend/debug_agent.py` は、エージェントの動作をステップごとに確認できる強力なツールです。

#### 基本的な使い方

**対話モード (推奨)**:
```bash
make debug-agent
# または
cd backend && mise exec -- python debug_agent.py
```

対話モードでは以下のコマンドが使えます:
```
> test 営業時間は？          # エージェント全体をテスト
> rag 営業時間は？           # RAG検索のみテスト
> llm <prompt>              # LLM生成のみテスト
> verbose                   # 詳細ログのON/OFF切り替え
> quit                      # 終了
```

**クエリ直接実行モード**:
```bash
# BusinessInfoAgent のテスト
make test-agent AGENT=business_info QUERY="営業時間は？"

# EventAgent のテスト
make test-agent AGENT=event QUERY="今週のイベントは？"

# 詳細ログ付き
make test-agent AGENT=business_info QUERY="営業時間は？" VERBOSE=1

# request_type 指定
make test-agent AGENT=business_info QUERY="いくらですか？" REQUEST_TYPE=price
```

#### 出力の見方

```
============================================================
              BusinessInfoAgent Debug: 営業時間は？
============================================================

Parameters:
  Request Type: auto
  Language: ja

[STEP] 1
RAG検索実行

  Query: 営業時間は？
  Category: general
  Language: ja

✓ Found 5 results

Top Entity: Engineer Cafe

Context:
エンジニアカフェの営業時間は平日9:00〜22:00、土日祝日10:00〜20:00です...

[STEP] 2
LLM応答生成

  Config: qa_response
  Prompt length: 485 characters

✓ Generated 87 characters

Response:
[relaxed]エンジニアカフェの営業時間は平日9:00〜22:00、土日祝日10:00〜20:00です。

[STEP] 3
エージェント実行

✓ Agent execution completed

Answer:
[relaxed]エンジニアカフェの営業時間は平日9:00〜22:00、土日祝日10:00〜20:00です。

Emotion: relaxed
```

#### ログファイルの確認

デバッグログは `logs/agent-debug/` に保存されます:

```bash
# 最近のログを表示
make show-logs

# または直接確認
ls -lt logs/agent-debug/
cat logs/agent-debug/20260113_150432_rag_search_general.json
```

---

### 6.2 ログレベルの調整

#### backend/.env での設定
```bash
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

#### Python コード内でのデバッグ出力

```python
# エージェント内でのデバッグログ
class YourAgent:
    async def answer_query(self, query: str):
        print(f"[YourAgent] Query: {query}")  # 基本ログ

        rag_result = await self.enhanced_rag.search(query)
        print(f"[YourAgent] RAG success: {rag_result.get('success')}")
        print(f"[YourAgent] Context length: {len(rag_result.get('data', {}).get('context', ''))}")

        # 詳細ログ (開発時のみ)
        import json
        print(f"[YourAgent] RAG result: {json.dumps(rag_result, indent=2, ensure_ascii=False)}")
```

---

## 7. よくあるエラーメッセージ集

### 7.1 環境変数関連

| エラーメッセージ | 原因 | 解決方法 |
|----------------|------|---------|
| `ValueError: OpenRouter API key not found` | OPENROUTER_API_KEY 未設定 | [2.1 OpenRouter API エラー](#21-openrouter-api-エラー) |
| `supabase.exceptions.AuthApiError: Invalid API key` | SUPABASE_KEY が間違っている | [2.2 Supabase 接続エラー](#22-supabase-接続エラー) |
| `openai.error.AuthenticationError` | OPENAI_API_KEY が間違っている | [2.3 OpenAI Embeddings エラー](#23-openai-embeddings-エラー) |
| `google.auth.exceptions.DefaultCredentialsError` | GOOGLE_APPLICATION_CREDENTIALS 未設定 | [2.4 Google Cloud API エラー](#24-google-cloud-api-エラー) |

---

### 7.2 依存関係関連

| エラーメッセージ | 原因 | 解決方法 |
|----------------|------|---------|
| `ModuleNotFoundError: No module named 'langgraph'` | 依存関係未インストール | `cd backend && mise exec -- pip install -r requirements.txt` |
| `mise: command not found` | mise 未インストール | [1.1 mise のインストール/セットアップエラー](#11-mise-のインストールセットアップエラー) |
| `ERR_PNPM_OUTDATED_LOCKFILE` | pnpm lockfile が古い | `cd frontend && mise exec -- pnpm install --no-frozen-lockfile` |

---

### 7.3 ランタイムエラー

| エラーメッセージ | 原因 | 解決方法 |
|----------------|------|---------|
| `AttributeError: 'NoneType' object has no attribute 'get'` | RAG結果が None | [3.1 RAG検索結果が空](#31-rag検索結果が空) |
| `asyncio.TimeoutError` | 処理時間が長すぎる | [3.3 エージェントの応答が遅い](#33-エージェントの応答が遅い) |
| `KeyError: 'context'` | RAG結果の構造が想定外 | RAG検索の戻り値を確認、エラーハンドリング追加 |

---

### 7.4 Docker/ビルド関連

| エラーメッセージ | 原因 | 解決方法 |
|----------------|------|---------|
| `bind: address already in use` | ポート競合 | [1.6 ポート競合エラー](#16-ポート競合エラー) |
| `Cannot connect to the Docker daemon` | Docker Desktop 未起動 | [1.3 Docker のセットアップエラー](#13-docker-のセットアップエラー) |
| `Service 'backend' failed to build` | Dockerfile エラー | [5.3 Docker Compose 起動エラー](#53-docker-compose-起動エラー) |

---

## クイックリファレンス

### 環境確認チェックリスト

```bash
# 1. mise がインストールされているか
mise --version

# 2. 必要なツールがインストールされているか
mise current

# 3. Docker が起動しているか
docker ps

# 4. 環境変数が設定されているか
cd backend
mise exec -- python -c "
import os
from dotenv import load_dotenv
load_dotenv()
for var in ['OPENROUTER_API_KEY', 'SUPABASE_URL', 'SUPABASE_KEY', 'OPENAI_API_KEY']:
    print(f'{var}: {'OK' if os.getenv(var) else 'NOT SET'}')
"

# 5. Supabase が起動しているか (ローカル開発)
supabase status

# 6. 依存関係がインストールされているか
cd backend && mise exec -- pip list | grep langgraph
cd ../frontend && mise exec -- pnpm list | grep next
```

---

### 緊急時のクリーンアップ手順

```bash
# 1. 全プロセスの停止
make clean

# 2. Docker の完全クリーンアップ
make clean:all

# 3. Node.js 依存関係のクリーンアップ
cd frontend
rm -rf node_modules pnpm-lock.yaml .next

# 4. Python 依存関係のクリーンアップ
cd ../backend
rm -rf __pycache__ .pytest_cache .ruff_cache

# 5. 再セットアップ
cd ..
make setup
```

---

### よく使うデバッグコマンド

```bash
# エージェントのインタラクティブデバッグ
make debug-agent

# 特定クエリのテスト
make test-agent AGENT=business_info QUERY="営業時間は？" VERBOSE=1

# RAG検索のテスト
cd backend
mise exec -- python -c "
import asyncio
from tools.enhanced_rag import EnhancedRAGSearch
from dotenv import load_dotenv

load_dotenv()

async def test():
    rag = EnhancedRAGSearch()
    result = await rag.search(query='営業時間は？', language='ja')
    print(result)

asyncio.run(test())
"

# LLMプロバイダーのテスト
cd backend
mise exec -- python -c "
import asyncio
from llm import get_llm_provider, get_model_config
from dotenv import load_dotenv

load_dotenv()

async def test():
    provider = get_llm_provider()
    response = await provider.generate(
        messages=[{'role': 'user', 'content': 'こんにちは'}],
        config=get_model_config('qa_response')
    )
    print(response)

asyncio.run(test())
"

# ログの確認
make show-logs
```

---

## サポートとリソース

### ドキュメント

- [AGENT-QUICKSTART.md](./AGENT-QUICKSTART.md) - エージェント実装の基本
- [ENVIRONMENT-VARIABLES.md](./ENVIRONMENT-VARIABLES.md) - 環境変数の詳細
- [LOCAL-DEVELOPMENT-SETUP.md](./LOCAL-DEVELOPMENT-SETUP.md) - 環境セットアップの詳細

### 外部リソース

- [OpenRouter Documentation](https://openrouter.ai/docs)
- [Supabase Documentation](https://supabase.com/docs)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [mise Documentation](https://mise.jdx.dev/)

### 問題が解決しない場合

1. `make debug-agent` で詳細ログを確認
2. `logs/agent-debug/` のログファイルを確認
3. 環境変数が正しく設定されているか再確認
4. Docker コンテナの状態を確認 (`docker ps`)
5. 依存関係を再インストール
6. プロジェクトの Issues で類似問題を検索

---

**最終更新**: 2026-01-13
**バージョン**: 1.0.0
