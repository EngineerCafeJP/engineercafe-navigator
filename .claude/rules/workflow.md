# 2-Agent ワークフロールール

## 役割定義

### Cursor (PM)
- 要件定義とプラン作成
- コードレビュー
- 本番デプロイの承認
- Plans.md の管理

### Claude Code (Worker)
- 実装とテスト
- CI/CD グリーン確保
- staging デプロイ
- ドキュメント更新

---

## コミュニケーションルール

### PM → Worker への依頼
1. Plans.md にタスクを追加
2. `pm:依頼中` マーカーを付与
3. `/handoff-to-claude` で引き継ぎ

### Worker → PM への報告
1. 実装完了後、CI/CD グリーンを確認
2. `cc:DONE` マーカーに更新
3. `/handoff-to-cursor` で報告

---

## CI/CD 必須チェック

Claude Code は以下を必ず確認:

```bash
# Frontend
cd frontend
pnpm lint
pnpm typecheck
pnpm build

# Backend
cd backend
ruff check .
black --check .
```

**失敗時のフロー:**
1. エラーを分析
2. 自動修正を試行
3. 修正できない場合は PM に報告

---

## コミット規約

```
<type>(<scope>): <subject>

<body>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

### Type
- `feat`: 新機能
- `fix`: バグ修正
- `docs`: ドキュメント
- `refactor`: リファクタリング
- `test`: テスト
- `chore`: その他

### Scope
- `frontend`, `backend`, `agent:*`, `docs`

---

## PR ルール

- main/develop へのマージは PM が実行
- Claude Code は PR 作成まで
- CI グリーンが必須
- レビュー承認が必須

---

## 禁止事項

Claude Code は以下を実行しない:
- `git push --force` (main/develop)
- 本番環境への直接デプロイ
- 機密情報のコミット
- PM 未承認の破壊的変更
