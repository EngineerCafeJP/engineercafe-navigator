# Plans.md（リダイレクト）

> ⚠️ 2026-05-05: このファイルは **stub（リダイレクト用）** です。  
> 旧 `Plans.md`（Wave 1 era / 2026-03-07）は [`docs/archive/Plans-2026-03-07-wave1.md`](docs/archive/Plans-2026-03-07-wave1.md) に移しました。

## 現行の参照先

| 用途 | リンク |
| --- | --- |
| 運用ゲート / alpha 状態の正本 | [`docs/STATUS.md`](docs/STATUS.md) |
| 構造リファクタの計画 | [`docs/plans/comprehensive-refactoring-plan-2026-05-05.md`](docs/plans/comprehensive-refactoring-plan-2026-05-05.md) |
| ADR 一覧 | [`docs/adr/README.md`](docs/adr/README.md) |
| ドキュメント索引 | [`docs/README.md`](docs/README.md) |
| 旧 Wave 1 era 計画（履歴） | [`docs/archive/Plans-2026-03-07-wave1.md`](docs/archive/Plans-2026-03-07-wave1.md) |

本 PR ではドキュメントの不整合修正のみを行い、以下の動線張り替えは別 PR に分けます:

- `.cursor/commands/*.md` および `frontend/.cursor/commands/*.md` 配下の `Plans.md` 参照（2-Agent ワークフロー記述）
- `docs/development/AGENTS.md`、`docs/development/CODE-REVIEW-GUIDELINES.md`、`docs/development/repo-structure.md` に残る「ルートに `Plans.md` を置いてタスク管理する」前提の記述（リンク自体は本 stub で resolve するが、説明されている運用は今は使われていない）

これらの参照先は、ファイル自体は本 stub の存在で resolve しますが、説明されている運用フロー自体は `docs/STATUS.md` / `docs/plans/comprehensive-refactoring-plan-2026-05-05.md` に置き換わっています。
