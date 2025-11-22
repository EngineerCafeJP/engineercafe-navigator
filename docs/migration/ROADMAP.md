# 移行ロードマップ

## 概要

Mastra → LangGraph移行プロジェクトの全体スケジュールとマイルストーンを定義します。

## 全体スケジュール

**期間**: 約8-10週間（2-2.5ヶ月）

## Phase 1: 基盤整備（1-2週間）

### Week 1: ドキュメント整備

- [x] ドキュメント構造の作成
- [x] 基盤ドキュメントの作成
  - [x] TEAM-ASSIGNMENTS.md
  - [x] OVERVIEW.md
  - [x] BRANCH-STRATEGY.md
  - [x] INTEGRATION-GUIDE.md
  - [x] COWORKING-SYSTEM-ANALYSIS.md
  - [x] MASTRA-AGENT-ANALYSIS.md
  - [x] ROADMAP.md
- [ ] エージェント別ドキュメントテンプレートの作成

### Week 2: 開発環境セットアップ

- [ ] Python開発環境のセットアップ
- [ ] LangGraphのインストールと設定
- [ ] データベース接続の確認
- [ ] テストフレームワークの構築
- [ ] CI/CDパイプラインの設定

## Phase 2: 基盤エージェント実装（2週間）

### Week 3: RouterAgent（統合エージェント）

**担当者**: 寺田@terisuke, YukitoLyn

- [ ] State定義の拡張
- [ ] RouterAgentノードの実装
- [ ] ルーティングロジックの実装
- [ ] 言語検出の実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

### Week 4: MemoryAgent（記憶機能）

**担当者**: 江口@takegg0311, Chie@chie0349ja

- [ ] MemoryAgentノードの実装
- [ ] チェックポインターとの統合
- [ ] メモリー検索ツールの実装
- [ ] 会話履歴取得の実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

## Phase 3: 情報提供エージェント実装（3週間）

### Week 5: BusinessInfoAgent

**担当者**: Kem198, 寺田@terisuke（補完）

- [ ] BusinessInfoAgentノードの実装
- [ ] Enhanced RAG検索ツールの実装
- [ ] 文脈継承の実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

### Week 6: FacilityAgent

**担当者**: Natsumi, jun

- [ ] FacilityAgentノードの実装
- [ ] Enhanced RAG検索ツールの実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

### Week 7: EventAgent

**担当者**: jun, 寺田@terisuke（補完）

- [ ] EventAgentノードの実装
- [ ] カレンダー統合ツールの実装
- [ ] Google Calendar API統合
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

## Phase 4: 補助エージェント実装（1週間）

### Week 8: GeneralKnowledgeAgent & ClarificationAgent

**担当者**: 各エージェント担当者

- [ ] GeneralKnowledgeAgentノードの実装
- [ ] Web検索ツールの実装
- [ ] ClarificationAgentノードの実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

## Phase 5: 特殊エージェント実装（2週間）

### Week 9: 音声・キャラクター制御エージェント

**担当者**: 各エージェント担当者

- [ ] VoiceOutputAgentノードの実装
- [ ] CharacterControlAgentノードの実装
- [ ] RealtimeAgentノードの実装
- [ ] WelcomeAgentノードの実装
- [ ] SlideNarratorノードの実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

### Week 10: OCRAgent（新規実装）

**担当者**: けいてぃー, たけがわ

- [ ] 要件定義の確定
- [ ] OCRライブラリの選定
- [ ] OCRAgentノードの実装
- [ ] 画像前処理の実装
- [ ] OCR処理ツールの実装
- [ ] 単体テストの作成
- [ ] ドキュメントの更新

## Phase 6: 統合と最適化（1-2週間）

### Week 11: 統合テスト

**担当者**: 統合エージェント担当者（寺田@terisuke, YukitoLyn）

- [ ] 全エージェントの統合
- [ ] 統合テストの実行
- [ ] コンフリクト解決
- [ ] パフォーマンステスト
- [ ] エラーハンドリングの強化

### Week 12: 最適化とドキュメント

**担当者**: 全員

- [ ] パフォーマンス最適化
- [ ] コードレビュー
- [ ] ドキュメントの最終確認
- [ ] 本番環境へのデプロイ準備

## マイルストーン

### Milestone 1: 基盤完成（Week 4終了時）

- RouterAgentとMemoryAgentが動作
- 基本的なワークフローが動作
- 統合テストが通過

### Milestone 2: 情報提供エージェント完成（Week 7終了時）

- BusinessInfoAgent, FacilityAgent, EventAgentが動作
- Enhanced RAGが動作
- カレンダー統合が動作

### Milestone 3: 全エージェント完成（Week 10終了時）

- すべてのエージェントが実装済み
- OCRAgentが動作
- 統合テストが通過

### Milestone 4: 本番準備完了（Week 12終了時）

- すべてのテストが通過
- パフォーマンスが基準を満たしている
- ドキュメントが完全
- 本番環境へのデプロイ準備完了

## リスク管理

### 高リスク項目

1. **OCRAgentの新規実装**
   - リスク: 要件が不明確、実装が複雑
   - 対策: 早期に要件定義、プロトタイプ作成

2. **統合時のコンフリクト**
   - リスク: 複数エージェントの同時開発によるコンフリクト
   - 対策: 統合エージェント担当者による早期介入

3. **パフォーマンス問題**
   - リスク: 統合後のパフォーマンス低下
   - 対策: 早期のパフォーマンステスト、最適化

### 中リスク項目

1. **外部API統合**
   - リスク: Google Calendar API等の統合が複雑
   - 対策: モックの作成、段階的な統合

2. **データベーススキーマ変更**
   - リスク: 既存データとの互換性
   - 対策: マイグレーションスクリプトの作成

## 成功基準

### 機能要件

- [ ] すべてのエージェントが動作
- [ ] 統合テストが100%通過
- [ ] パフォーマンスが基準を満たしている（レスポンスタイム < 3秒）
- [ ] エラー率 < 1%

### 非機能要件

- [ ] ドキュメントが完全
- [ ] コードカバレッジ > 80%
- [ ] コードレビューが完了
- [ ] セキュリティチェックが通過

## 次のステップ

1. **Week 1-2**: ドキュメント整備と開発環境セットアップ
2. **Week 3**: RouterAgentの実装開始
3. **Week 4**: MemoryAgentの実装開始
4. **以降**: 各エージェントの順次実装

## 参考

- [OVERVIEW.md](./OVERVIEW.md): 移行の概要
- [BRANCH-STRATEGY.md](./BRANCH-STRATEGY.md): ブランチ戦略
- [TEAM-ASSIGNMENTS.md](./TEAM-ASSIGNMENTS.md): チーム担当者一覧
- [INTEGRATION-GUIDE.md](./INTEGRATION-GUIDE.md): 統合ガイド

