# オンボーディングガイド - 新規メンバー向け

## はじめに

Engineer Cafe Navigatorプロジェクトへようこそ！このガイドは、新規メンバーがプロジェクトに参加し、すぐに開発を始められるように設計されています。

## 📋 目次

1. [プロジェクトの現状](#プロジェクトの現状)
2. [初回セットアップ](#初回セットアップ)
3. [自分の担当を確認](#自分の担当を確認)
4. [開発を始める](#開発を始める)
5. [よくある質問](#よくある質問)

## プロジェクトの現状

### アーキテクチャの移行中

このプロジェクトは現在、**Mastra版からLangGraph版への移行**が進行中です。

- **Frontend (NextJS)**: Mastra版が本番稼働中（`frontend/`）
- **Backend (Python)**: LangGraph版を実装中（`backend/`）
- **移行ドキュメント**: `docs/migration/` に詳細があります

### プロジェクト構造

```
engineer-cafe-navigator2025/
├── frontend/              # NextJS + Mastra（本番稼働中）
├── backend/              # Python + LangGraph（移行中）
├── docs/
│   └── migration/        # 移行プロジェクトのドキュメント
├── langgraph-reference/  # 参考リポジトリ（git submodule）
└── README.md
```

## 初回セットアップ

### 1. リポジトリのクローン

```bash
# 参考リポジトリ（langgraph-reference）も含めてクローン
git clone --recurse-submodules <repository-url>
cd engineer-cafe-navigator2025

# 既存リポジトリの場合
git submodule update --init --recursive
```

### 2. 環境のセットアップ

#### Frontend（NextJS）

```bash
cd frontend
pnpm install
cp .env.example .env.local
# .env.localを編集して必要なAPIキーを設定
```

#### Backend（Python）

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# .envを編集して必要なAPIキーを設定
```

### 3. 開発サーバーの起動

```bash
# Frontend
cd frontend
pnpm dev

# Backend（別ターミナル）
cd backend
python -m uvicorn main:app --reload
```

## 自分の担当を確認

### 1. チーム担当者一覧を確認

[TEAM-ASSIGNMENTS.md](docs/migration/TEAM-ASSIGNMENTS.md) で自分の担当エージェントを確認してください。

### 2. 担当エージェントのドキュメントを読む

`docs/migration/agents/{agent-name}/` に各エージェントの詳細ドキュメントがあります：

- `README.md`: エージェントの概要・役割・責任範囲
- `MIGRATION-GUIDE.md`: Mastra→LangGraph移行手順
- `CI-CD.md`: CI/CD設定・ブランチ戦略
- `TESTING.md`: テスト戦略・テストケース

### 3. 参考実装を確認

`langgraph-reference/coworking-space-system/` に参考実装があります：

```bash
# 参考実装の構造を確認
ls -la langgraph-reference/coworking-space-system/
```

## 開発を始める

### 1. ブランチ戦略を理解する

開発は以下のフローで進めます：

```
main (本番)
  ↑
develop (統合・テスト)
  ↑
feature/{agent-name} (各エージェント開発)
```

詳細: [BRANCH-STRATEGY.md](docs/migration/BRANCH-STRATEGY.md)

### 2. featureブランチを作成

```bash
# developブランチから最新を取得
git checkout develop
git pull origin develop

# featureブランチを作成
git checkout -b feature/{agent-name}
# 例: git checkout -b feature/router-agent
```

### 3. 開発を開始

1. **エージェントのドキュメントを読む**
   - `docs/migration/agents/{agent-name}/README.md`
   - `docs/migration/agents/{agent-name}/MIGRATION-GUIDE.md`

2. **参考実装を確認**
   - `langgraph-reference/coworking-space-system/`
   - `docs/migration/COWORKING-SYSTEM-ANALYSIS.md`

3. **実装を開始**
   - `backend/agents/{agent_name}.py` を作成
   - `backend/workflows/main_workflow.py` に統合

4. **テストを作成**
   - `backend/tests/agents/test_{agent_name}.py` を作成

### 4. PRを作成

```bash
# featureブランチをpush
git push origin feature/{agent-name}

# GitHubでPRを作成
# - base: develop
# - compare: feature/{agent-name}
```

## よくある質問

### Q: どのエージェントから始めればいいですか？

A: 自分の担当エージェントから始めてください。担当が決まっていない場合は、統合エージェント担当者（寺田@terisuke, YukitoLyn）に相談してください。

### Q: Mastra版のコードはどこにありますか？

A: `frontend/src/mastra/agents/` にMastra版のエージェント実装があります。移行の参考にしてください。

### Q: 参考リポジトリ（langgraph-reference）が空です

A: 以下のコマンドで取得できます：

```bash
git submodule update --init --recursive
```

### Q: エラーが発生しました

A: 以下のドキュメントを確認してください：
- [トラブルシューティング](docs/DEVELOPMENT.md#トラブルシューティング)
- [統合ガイド](docs/migration/INTEGRATION-GUIDE.md#トラブルシューティング)

### Q: 質問や相談はどこにすればいいですか？

A: 
- **技術的な質問**: GitHub Issues
- **担当エージェントに関する質問**: 担当エージェントの他の担当者
- **全体に関する質問**: 統合エージェント担当者（寺田@terisuke, YukitoLyn）

## 次のステップ

1. ✅ [移行概要](docs/migration/OVERVIEW.md) を読む
2. ✅ [チーム担当者一覧](docs/migration/TEAM-ASSIGNMENTS.md) で自分の担当を確認
3. ✅ [ブランチ戦略](docs/migration/BRANCH-STRATEGY.md) を理解する
4. ✅ 担当エージェントのドキュメントを読む
5. ✅ featureブランチを作成して開発を開始

## 参考リンク

- [移行概要](docs/migration/OVERVIEW.md)
- [チーム担当者一覧](docs/migration/TEAM-ASSIGNMENTS.md)
- [ブランチ戦略](docs/migration/BRANCH-STRATEGY.md)
- [ロードマップ](docs/migration/ROADMAP.md)
- [統合ガイド](docs/migration/INTEGRATION-GUIDE.md)
- [開発標準](docs/migration/DEVELOPMENT-STANDARDS.md)
- [コードレビューガイド](docs/migration/CODE-REVIEW-GUIDE.md)
- [準備チェックリスト](docs/migration/PREPARATION-CHECKLIST.md)

---

**質問や問題があれば、遠慮なく統合エージェント担当者に連絡してください！**

