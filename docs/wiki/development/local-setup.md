# ローカル開発環境セットアップ

## 前提条件

| ソフトウェア | バージョン | 確認コマンド |
|------------|-----------|-------------|
| Node.js | 20.x以上 | `node -v` |
| pnpm | 8.x以上 | `pnpm -v` |
| Python | 3.11以上 | `python --version` |
| Docker | 最新版 | `docker -v` |
| Supabase CLI | 2.x以上 | `supabase -v` |

## クイックスタート

### 1. リポジトリのクローン

```bash
git clone https://github.com/EngineerCafeJP/engineercafe-navigator.git
cd engineercafe-navigator
```

### 2. Frontendセットアップ

```bash
# 依存関係インストール
pnpm install

# 環境変数設定
cp .env.example .env.local
# .env.local を編集して必要なキーを設定

# 開発サーバー起動
pnpm dev
```

### 3. Backendセットアップ

```bash
cd backend

# Python仮想環境作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 依存関係インストール
pip install -r requirements.txt

# 環境変数設定
cp .env.example .env
# .env を編集

# サーバー起動
uvicorn main:app --reload
```

### 4. Supabaseローカル起動

```bash
# Docker起動確認
docker info

# Supabase起動
supabase start

# pgvector有効化（初回のみ）
PGPASSWORD=postgres psql -h 127.0.0.1 -p 54322 -U postgres -d postgres \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## 環境変数

### Frontend (.env.local)

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:54321
NEXT_PUBLIC_SUPABASE_ANON_KEY=<supabase start で表示されるキー>
SUPABASE_SERVICE_ROLE_KEY=<supabase start で表示されるキー>

# Google Cloud
GOOGLE_CLOUD_PROJECT_ID=your-project-id
GOOGLE_GENERATIVE_AI_API_KEY=your-gemini-key

# OpenAI (Embeddings)
OPENAI_API_KEY=sk-your-key
```

### Backend (.env)

```bash
# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-your-key

# Supabase
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_KEY=<service role key>

# Application
ENVIRONMENT=development
PORT=8000
APP_URL=http://localhost:3000
```

## Supabaseローカル環境

### 起動確認

```bash
supabase status
```

正常な場合の出力:
```
API URL: http://127.0.0.1:54321
Database URL: postgresql://postgres:postgres@127.0.0.1:54322/postgres
Studio URL: http://127.0.0.1:54323
```

### 管理画面アクセス

- **Supabase Studio**: http://127.0.0.1:54323
- **Mailpit (メール確認)**: http://127.0.0.1:54324

### 停止・リセット

```bash
# 停止
supabase stop

# データ保持して停止
supabase stop --backup

# 完全リセット
supabase stop --no-backup
supabase start
```

## トラブルシューティング

### Docker関連

```
エラー: Cannot connect to Docker daemon
対策:
1. Docker Desktopが起動しているか確認
2. `docker info` でステータス確認
3. Docker再起動
```

### ポート競合

```
エラー: Port 54321 is already in use
対策:
1. 既存のSupabaseを停止: supabase stop
2. ポート使用確認: lsof -i :54321
3. 該当プロセスを終了
```

### M1/M2 Mac固有

```
エラー: exec format error
対策:
1. Docker Desktopで "Use Rosetta" を有効化
2. Settings → General → "Use Rosetta for x86_64/amd64 emulation"
```

### WSL2 (Windows)

```
エラー: Cannot connect to Supabase
対策:
1. WSL2でDockerが動作しているか確認
2. ネットワーク設定を確認
3. Windows Firewallの設定確認
```

## 開発コマンド

### Frontend

| コマンド | 説明 |
|---------|------|
| `pnpm dev` | 開発サーバー起動 |
| `pnpm build` | プロダクションビルド |
| `pnpm lint` | ESLintチェック |
| `pnpm typecheck` | TypeScript型チェック |

### Backend

| コマンド | 説明 |
|---------|------|
| `uvicorn main:app --reload` | 開発サーバー起動 |
| `pytest` | テスト実行 |
| `black .` | コードフォーマット |
| `mypy .` | 型チェック |

## 検証済み環境

| 環境 | OS | Docker | 備考 |
|-----|-----|--------|------|
| macOS | Sonoma 15.x | Desktop 4.x | M1/M2対応 |
| Windows | 11 | WSL2 + Desktop | 推奨構成 |
| Linux | Ubuntu 22.04 | Docker Engine | サーバー用 |

## 関連ドキュメント

- [OpenRouter設定](../api-management/openrouter-setup.md)
- [ブランチ戦略](./branch-strategy.md)
- [CONTRIBUTING.md](../../CONTRIBUTING.md)
