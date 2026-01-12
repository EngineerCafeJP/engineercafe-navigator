# 意思決定記録 (SSOT)

> このファイルはプロジェクトの重要な意思決定を記録します。
> 新しい決定は上部に追加してください。

---

## 2025-12-27: 2-Agent モード導入

**決定**: Cursor (PM) + Claude Code (Worker) の 2-Agent モードを採用

**理由**:
- 役割分担による品質向上
- レビュープロセスの明確化
- CI/CD 遵守の徹底

**影響**:
- AGENTS.md, Plans.md の導入
- .cursor/commands/ の追加
- ワークフロールールの策定

---

## 2025-12-06: LangGraph 移行計画

**決定**: Mastra (TypeScript) から LangGraph (Python) へ移行

**理由**:
- Python エコシステムとの統合
- LangGraph の高度なワークフロー機能
- チームのスキルセット

**影響**:
- 12 エージェントの移行
- backend/ ディレクトリの新設
- 担当者割り当て

---

## 既存の決定事項 (Serena から継承)

### Tailwind CSS バージョン
- **決定**: v3.4.17 を使用、v4 は禁止
- **理由**: v4 は破壊的変更あり

### Embedding 次元数
- **決定**: OpenAI text-embedding-3-small (1536 次元)
- **理由**: 768 次元は非推奨

### 会話メモリ TTL
- **決定**: 3 分間
- **理由**: 短期記憶の最適バランス
