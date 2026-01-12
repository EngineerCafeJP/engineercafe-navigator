# /handoff-to-claude - Claude Code への引き継ぎ

## 概要
PM (Cursor) から Worker (Claude Code) へタスクを引き継ぎます。

## 実行内容

1. **タスクの明確化**
   - Plans.md から該当タスクを抽出
   - 完了条件を明示
   - 必要なコンテキストを整理

2. **Plans.md の更新**
   - タスクに `pm:依頼中` マーカーを追加
   - 依頼日時を記録

3. **引き継ぎドキュメント生成**
   - Claude Code が実行すべきコマンド
   - 参照すべきファイル
   - 完了後の報告形式

## 出力形式

```
📤 Claude Code への依頼

## タスク
[タスク名]

## 完了条件
- [ ] [条件1]
- [ ] [条件2]
- [ ] CI/CD オールグリーン

## 参照ファイル
- `frontend/src/mastra/agents/router-agent.ts`
- `docs/migration/agents/router-agent/`

## コンテキスト
[必要な背景情報]

## 実行コマンド
```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm build
```

## 完了後
`/handoff-to-cursor` で報告してください
```

## 使用例

Cursor で「RouterAgent の実装を依頼して」と言うと実行
