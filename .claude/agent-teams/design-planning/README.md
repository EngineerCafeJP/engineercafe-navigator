# Agent Teams テンプレート

このディレクトリには、Claude Code CLI の Agent Teams 機能を使用するための汎用テンプレート集が含まれています。

## 概要

Agent Teams は、Claude Code CLI の実験的機能で、4つの専門エージェントが協調して複雑な設計タスクに取り組みます。

### 4つのエージェント

1. **Requirements Agent** - ユーザー要望の聞き取り・要件明確化
2. **Planning Agent** - タスク分解・実装計画作成
3. **Architect Agent** - 技術設計・アーキテクチャ提案
4. **Reviewer Agent** - 批判的レビュー・品質チェック

## ディレクトリ構成

```
design-planning/
├── README.md                       # このファイル
├── prompts/                        # チーム作成プロンプト
│   └── create-team.md
├── agent-roles/                    # 各エージェントの役割定義
│   ├── requirements-agent.md
│   ├── planning-agent.md
│   ├── architect-agent.md
│   └── reviewer-agent.md
└── output-templates/               # ドキュメントテンプレート
    ├── requirement-doc.md
    ├── plan-doc.md
    ├── architecture-doc.md
    └── review-doc.md
```

## 使い方

### 1. Agent Teams を有効化

`.claude/settings.json` に以下を追加：

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### 2. チームを作成

[prompts/create-team.md](prompts/create-team.md) の内容をClaude Code CLIで実行します。

```bash
# Claude Code CLI でファイル内容を実行
# または、内容をコピーしてClaude Codeに貼り付け
```

### 3. ワークフロー

```
複雑な設計タスク・新機能開発
    ↓
prompts/create-team.md のプロンプトでチーム作成
    ↓
Requirements Agent: ユーザーヒアリング → requirement-doc.md 作成
Planning Agent: タスク分解・計画 → plan-doc.md 作成 (並行作業)
Architect Agent: 技術設計 → architecture-doc.md 作成 (並行作業)
    ↓
Reviewer Agent: 全体レビュー → review-doc.md 作成
    ↓
フィードバックループ（必要に応じて繰り返し）
    ↓
成果物を確認・承認 → 実装開始
```

## 適用シーン

Agent Teams は以下のようなシーンで活用できます：

- **新機能の設計**: 複雑な機能を多角的に検討
- **アーキテクチャ変更**: 影響範囲の大きい変更の事前設計
- **リファクタリング計画**: 大規模なコード改善の計画立案
- **技術選定**: 複数の技術選択肢を比較検討
- **要件整理**: 曖昧な要求を明確化

## ファイルの役割

### `prompts/create-team.md`

4つのエージェントチームを作成するための自然言語プロンプトです。このファイルの内容を実行することで、Agent Teams が起動します。

### `agent-roles/` ディレクトリ

各エージェントの詳細な役割定義が含まれています。

- **requirements-agent.md**: 質問テンプレート、要件定義のチェックリスト
- **planning-agent.md**: タスク分解のガイドライン、計画作成のチェックリスト
- **architect-agent.md**: 設計の観点、アーキテクチャパターン
- **reviewer-agent.md**: レビュー観点、批判的質問のテンプレート

### `output-templates/` ディレクトリ

各エージェントが作成する成果物のテンプレートです。

- **requirement-doc.md**: 要件ドキュメントのテンプレート
- **plan-doc.md**: 実装計画のテンプレート
- **architecture-doc.md**: アーキテクチャ設計のテンプレート
- **review-doc.md**: レビューレポートのテンプレート

## 注意事項

### Agent Teams は実験的機能です

- **セッション再開不可**: チームセッションは再開できません
- **トークン使用量が大きい**: 4つのエージェントが同時に動作するため
- **複雑なタスク専用**: 単純なタスクには不向き

### 適切な使い分け

- **Agent Teams**: 複雑な設計タスク（新機能、アーキテクチャ変更など）
- **通常のClaude Code**: 日常的な実装、バグ修正、ドキュメント更新

## 成果物の保存

Agent Teams が生成する成果物は `.claude/project/<プロジェクト名>/` に保存されます。

```
.claude/project/<プロジェクト名>/
├── requirement-doc.md      # Requirements Agent が作成
├── plan-doc.md            # Planning Agent が作成
├── architecture-doc.md    # Architect Agent が作成
└── review-doc.md          # Reviewer Agent が作成
```

**注意**:
- `<プロジェクト名>` はプロジェクトごとに動的に決定されます
- 各エージェントは `output-templates/` のテンプレートを参考に成果物を作成します

## カスタマイズ

このテンプレート集はプロジェクトに合わせてカスタマイズできます：

1. **役割定義の調整**: `agent-roles/` 内のファイルを編集
2. **テンプレートの拡張**: `output-templates/` にプロジェクト固有のセクションを追加
3. **エージェント数の変更**: `prompts/create-team.md` でエージェント構成を変更

---

詳細は各ファイルを参照してください。
