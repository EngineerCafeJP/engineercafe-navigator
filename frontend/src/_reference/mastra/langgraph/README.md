# LangGraph統合

このディレクトリには、LangGraphを使用したAIエージェントワークフローの実装が含まれています。

## 概要

LangGraphは、状態を持つ長期実行エージェントを構築するための低レベルオーケストレーションフレームワークです。既存のMastraベースのエージェントをLangGraphのグラフ構造で統合することで、より柔軟で拡張可能なAIエージェントシステムを実現します。

## 主な特徴

- **グラフベースのワークフロー**: エージェント間の複雑なルーティングと状態管理
- **永続的な実行**: 失敗から自動的に回復し、長時間実行可能
- **人間の介入**: 実行中の任意の時点で状態を検査・変更可能
- **包括的なメモリ**: 短期作業メモリと長期永続メモリの両方をサポート
- **デバッグと可視化**: LangSmithとの統合による詳細な実行トレース

## アーキテクチャ

```
START
  ↓
Memory Node (会話履歴とコンテキスト取得)
  ↓
Router Node (クエリのルーティング決定)
  ↓
  ├─→ Clarification Agent (曖昧なクエリの明確化)
  ├─→ BusinessInfo Agent (営業情報)
  ├─→ Facility Agent (施設情報)
  ├─→ Event Agent (イベント情報)
  └─→ GeneralKnowledge Agent (一般的な知識)
  ↓
Format Response Node (応答のフォーマット)
  ↓
END
```

## 使用方法

```typescript
import { getEngineerCafeNavigator } from '@/mastra';
import { Config } from '@/mastra/types/config';

const config: Config = {
  gemini: {
    apiKey: process.env.GEMINI_API_KEY!,
    model: 'gemini-2.0-flash-exp',
  },
  external: {
    // 外部API設定
  },
};

const navigator = getEngineerCafeNavigator(config);
const langGraphWorkflow = navigator.getLangGraphWorkflow();

if (langGraphWorkflow) {
  const result = await langGraphWorkflow.invoke({
    query: '営業時間を教えてください',
    sessionId: 'session-123',
    language: 'ja',
  });

  console.log(result.answer);
  console.log(result.emotion);
  console.log(result.metadata);
}
```

## 既存のMastraエージェントとの統合

LangGraphワークフローは、既存のMastraエージェントを再利用しています：

- `RouterAgent`: クエリのルーティング
- `BusinessInfoAgent`: 営業情報の処理
- `FacilityAgent`: 施設情報の処理
- `MemoryAgent`: 会話履歴の管理
- `EventAgent`: イベント情報の処理
- `GeneralKnowledgeAgent`: 一般的な知識の処理
- `ClarificationAgent`: 曖昧なクエリの明確化

## 今後の拡張

- [ ] ストリーミング応答の完全サポート
- [ ] LangSmithとの統合による可視化
- [ ] チェックポイント機能による永続的な実行
- [ ] 人間の介入機能の実装
- [ ] サブグラフによる複雑なワークフローの構築

## 参考資料

- [LangGraph公式ドキュメント](https://langchain-ai.github.io/langgraph/)
- [LangGraph JS版](https://github.com/langchain-ai/langgraphjs)

