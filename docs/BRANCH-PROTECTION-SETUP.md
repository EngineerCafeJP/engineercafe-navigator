# ブランチ保護設定ガイド

このドキュメントでは、GitHub Branch Rulesets を使用したブランチ保護の設定方法を説明します。

## 推奨: Branch Rulesets vs Classic Branch Protection

**Branch Rulesets を使用してください。** Classic Branch Protection は非推奨となりつつあります。

| 機能 | Classic | Rulesets (推奨) |
|-----|---------|----------------|
| 複数ルール適用 | 1つのみ | 複数レイヤー可能 |
| バイパス制御 | 限定的 | 細かく設定可能 |
| 将来サポート | メンテナンスモード | アクティブ開発中 |

## 設定手順

### 1. Rulesets ページにアクセス

1. リポジトリの **Settings** を開く
2. 左メニューから **Rules** → **Rulesets** を選択
3. **New ruleset** → **New branch ruleset** をクリック

### 2. Main ブランチ用ルールセット

**Ruleset name**: `main-branch-protection`

**Enforcement status**: `Active`

**Target branches**:
- **Add target** → **Include by pattern**
- パターン: `main` (⚠️ `Default` ではなく明示的に指定)

**Rules**:

| ルール | 設定 | 説明 |
|-------|------|------|
| **Restrict deletions** | ✅ ON | ブランチ削除を禁止 |
| **Require a pull request before merging** | ✅ ON | 直接プッシュを禁止 |
| → Required approvals | `1` | 最低1人の承認が必要 |
| → Dismiss stale reviews | ✅ ON | 新コミット時に古いレビューを無効化 |
| **Require status checks to pass** | ✅ ON | CI チェック必須 |
| → Required checks | `ci-success` | CI ワークフローの最終ジョブ |
| **Block force pushes** | ✅ ON | 強制プッシュを禁止 |
| **Require linear history** | ⚡ 任意 | Squash/Rebase を強制 |

**Bypass list** (オプション):
- GitHub Actions (自動リリース用)

### 3. Develop ブランチ用ルールセット

**Ruleset name**: `develop-branch-protection`

**Enforcement status**: `Active`

**Target branches**:
- パターン: `develop`

**Rules**:

| ルール | 設定 | 説明 |
|-------|------|------|
| **Restrict deletions** | ✅ ON | ブランチ削除を禁止 |
| **Require a pull request before merging** | ✅ ON | 直接プッシュを禁止 |
| → Required approvals | `1` | 最低1人の承認 |
| **Require status checks to pass** | ✅ ON | CI チェック必須 |
| → Required checks | `ci-success` | |
| **Block force pushes** | ✅ ON | 強制プッシュを禁止 |

**Bypass list**:
- チームリード
- CI/CD ボットアカウント

## ターゲティング方法の違い

### Default ターゲティング

```yaml
Target: ~DEFAULT_BRANCH
```

- リポジトリのデフォルトブランチ（通常 `main`）のみを対象
- `develop` ブランチは**保護されない**
- 組織全体で統一ポリシーを適用する場合に便利

### 明示的ターゲティング（推奨）

```yaml
Target: main
Target: develop
```

- 特定のブランチを明示的に指定
- ブランチごとに異なるルールを設定可能
- 本プロジェクトではこちらを推奨

### パターンターゲティング

```yaml
Target: refs/heads/feature/*
Target: releases/**/*
```

- ワイルドカードで複数ブランチを対象
- Feature ブランチの軽いルール適用に便利

## Status Checks の設定

### 必須チェック

CI ワークフロー (`.github/workflows/ci.yml`) で定義された `ci-success` ジョブを必須チェックとして設定します。

**設定手順**:
1. **Require status checks to pass** を ON
2. **Add checks** をクリック
3. `ci-success` を検索して追加

### チェック一覧

| チェック名 | 説明 |
|-----------|------|
| `ci-success` | 全 CI ジョブの成功を確認 |
| `frontend-lint` | ESLint チェック |
| `frontend-typecheck` | TypeScript 型チェック |
| `frontend-build` | Next.js ビルド |
| `backend-lint` | Python リンター |

## よくある質問

### Q: "Default" を選ぶとどうなりますか？

`Default` はリポジトリの**デフォルトブランチのみ**（通常 `main`）を対象とします。`develop` ブランチには適用されません。

本プロジェクトでは `main` と `develop` 両方を保護する必要があるため、明示的なパターン指定を推奨します。

### Q: Required approvals を 0 にできますか？

はい、可能です。ただし最低 1 人の承認を推奨します。

- **main**: 1-2 人（本番環境のため厳格に）
- **develop**: 1 人（開発速度とのバランス）

### Q: 管理者もルールに従う必要がありますか？

**Bypass list** に追加しない限り、管理者もルールに従います。

セキュリティのため、**Do not allow bypassing** を ON にすることを推奨します。

## 設定完了後の確認

1. Feature ブランチを作成
2. 変更をコミット・プッシュ
3. `develop` ブランチへの PR を作成
4. 以下を確認:
   - CI チェックが実行される
   - 承認なしでマージできない
   - 直接プッシュがブロックされる

## トラブルシューティング

### Status check が表示されない

- CI ワークフローが少なくとも1回実行されている必要があります
- ワークフローファイルが正しいブランチにプッシュされているか確認

### 直接プッシュができてしまう

- Ruleset の **Enforcement status** が `Active` になっているか確認
- **Target branches** が正しく設定されているか確認

### バイパスが必要な場合

緊急時のみ、**Bypass list** に一時的に追加してください。作業完了後は必ず削除してください。

## 参考リンク

- [GitHub Rulesets ドキュメント](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [Branch Protection ベストプラクティス](https://dev.to/n3wt0n/best-practices-for-branch-protection-2pe3)
