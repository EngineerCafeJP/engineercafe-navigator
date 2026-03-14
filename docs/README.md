# Documentation Map

> 2026-03-14 時点での「どの文書を読めばよいか」を整理したインデックスです。古い Mastra 移行期の文書が残っているため、まずこのページから参照してください。

## まず読む文書

- [../README.md](../README.md): プロジェクト全体の現在地
- [STATUS.md](STATUS.md): 実装状況、既知リスク、production gap、GitHub の open items
- [plans/production-hardening-session-2026-03-14.md](plans/production-hardening-session-2026-03-14.md): 次セッション用の修正計画
- [../frontend/README.md](../frontend/README.md): フロントエンドの現況
- [../backend/README.md](../backend/README.md): バックエンドの現況
- [DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md): 現在の開発導線

## 現役ドキュメント

### プロジェクト全体

- [STATUS.md](STATUS.md)
- [CHANGELOG.md](CHANGELOG.md)

### 実装と運用

- [DEVELOPER-GUIDE.md](DEVELOPER-GUIDE.md)
- [testing/TESTING-GUIDE.md](testing/TESTING-GUIDE.md)

### コンポーネント別

- [../frontend/README.md](../frontend/README.md)
- [../backend/README.md](../backend/README.md)

## 読むときに注意が必要な文書

以下は内容の一部が現行実装とずれており、参照時に [STATUS.md](STATUS.md) で現況確認が必要です。

- `docs/api/`
- `docs/architecture/`
- `docs/DEPLOYMENT.md`
- `docs/SECURITY.md`
- `docs/development/` 配下の多くの文書
- `docs/PRESENTATION-MODE-GUIDE.md`
- `frontend/VOICE_UI_PLAN.md`

主なズレ:

- Mastra 前提の構成説明
- RouterAgent / MemoryAgent / ClarificationAgent を現役として扱う説明
- 2024-2025 時点の予定表や migration plan
- 実際には未接続の env validation / auth / monitoring の説明不足

## アーカイブ

- [archive/README.md](archive/README.md): 履歴資料の入口
- `archive/migration/`: Mastra -> LangGraph 移行期の詳細資料
- `archive/frontend-docs-old/`: 旧 frontend 文書群

## 今回の整理方針

- README 群と `docs/STATUS.md` を現況ベースに更新
- 現役 docs と履歴 docs の境界を明示
- 重複ファイルを削除
- 大規模な legacy docs は一括で書き直す前に、まず「現役ではない」ことを明示

## 直近の次アクション

- `docs/development/` 配下の legacy 文書を「更新」「縮退」「archive 移動」に分類
- API / architecture / security / deployment 文書を現行コードと現行インフラへ合わせる
- 運用 runbook と production checklist を追加する
