# Mastra版エージェント分析

## 概要

このドキュメントは、既存のMastra版エージェントの責任範囲と機能を分析し、LangGraph版への移行の参考にします。

## エージェント一覧

### 1. RouterAgent（統合エージェント）

**ファイル**: `frontend/src/mastra/agents/router-agent.ts`

**責任範囲**:
- クエリの言語検出（日本語/英語）
- メモリー関連の質問の検出
- クエリの分類（category）
- 特定リクエストタイプの抽出（requestType）
- 文脈依存クエリの処理（前回のrequestTypeの継承）
- 適切なエージェントへのルーティング

**主要メソッド**:
- `routeQuery(query: string, sessionId: string): Promise<RouteResult>`
- `selectAgent(category: string, requestType: string | null, query?: string): string`
- `isMemoryRelatedQuestion(query: string): boolean`
- `isContextDependentQuery(query: string): boolean`
- `extractRequestType(query: string): string | null`

**ルーティングロジック**:
- `category: 'business'` → `BusinessInfoAgent`
- `category: 'facility'` → `FacilityAgent`
- `category: 'event'` → `EventAgent`
- `category: 'general'` → `GeneralKnowledgeAgent`
- `category: 'clarification'` → `ClarificationAgent`
- メモリー関連 → `MemoryAgent`

**LangGraph版への移行ポイント**:
- Primary Assistantパターンで実装
- ツールベースのルーティング（`ToBusinessInfoAgent`, `ToFacilityAgent`等）
- 状態管理に`routed_to`フィールドを使用

### 2. BusinessInfoAgent（エンジニアカフェ情報）

**ファイル**: `frontend/src/mastra/agents/business-info-agent.ts`

**責任範囲**:
- 営業時間の提供
- 料金・費用情報の提供
- 場所・アクセス情報の提供
- 基本施設情報の提供

**主要機能**:
- Enhanced RAG検索（`enhancedRagSearchTool`）
- 文脈継承（前の会話からrequestTypeとエンティティを継承）
- 感情タグの付与（`[happy]`, `[sad]`, `[relaxed]`等）

**主要メソッド**:
- `answerBusinessQuery(query, category, requestType, language, sessionId): Promise<UnifiedAgentResponse>`
- `enhanceContextQuery(query, requestType, language, contextEntity): string`
- `isShortContextQuery(query: string): boolean`

**LangGraph版への移行ポイント**:
- ツール: `get_business_info`, `search_business_info`
- プロンプト: 営業情報専門家としての指示
- メモリー: 文脈継承の実装

### 3. FacilityAgent（施設機能説明）

**ファイル**: `frontend/src/mastra/agents/facility-agent.ts`

**責任範囲**:
- 設備・施設の詳細情報（Wi-Fi、電源コンセント等）
- 会議室・スペース情報
- 地下施設情報
- 技術設備情報（3Dプリンター等）

**主要機能**:
- Enhanced RAG検索
- 感情タグの付与

**主要メソッド**:
- `answerFacilityQuery(query, category, requestType, language, sessionId): Promise<UnifiedAgentResponse>`

**LangGraph版への移行ポイント**:
- ツール: `get_facility_info`, `search_facility_info`
- プロンプト: 施設情報専門家としての指示

### 4. MemoryAgent（記憶機能）

**ファイル**: `frontend/src/mastra/agents/memory-agent.ts`

**責任範囲**:
- 過去の会話履歴の取得
- 「以前何を聞いたか」への回答
- 会話コンテキストの提供

**主要機能**:
- `SimplifiedMemorySystem`を使用
- 3分間の会話ウィンドウ
- 感情タグの付与

**主要メソッド**:
- `handleMemoryQuery(query, sessionId, language): Promise<UnifiedAgentResponse>`
- `getConversationHistory(sessionId, language): Promise<string>`

**LangGraph版への移行ポイント**:
- ツール: `get_conversation_history`, `search_memory`
- チェックポインターとの統合
- メモリー検索の実装

### 5. EventAgent（イベント）

**ファイル**: `frontend/src/mastra/agents/event-agent.ts`

**責任範囲**:
- イベント情報の提供
- カレンダー統合
- イベントの検索・フィルタリング

**主要機能**:
- Google Calendar API統合
- Enhanced RAG検索
- 感情タグの付与

**主要メソッド**:
- `answerEventQuery(query, category, requestType, language, sessionId): Promise<UnifiedAgentResponse>`

**LangGraph版への移行ポイント**:
- ツール: `get_events`, `search_events`, `get_calendar`
- 外部API統合（Google Calendar）

### 6. GeneralKnowledgeAgent（一般知識）

**ファイル**: `frontend/src/mastra/agents/general-knowledge-agent.ts`

**責任範囲**:
- 一般的な知識への回答
- Web検索の活用
- エンジニアカフェの範囲外の質問への対応

**主要機能**:
- Web検索ツール（`GeneralWebSearchTool`）
- 感情タグの付与

**主要メソッド**:
- `answerGeneralQuery(query, language, sessionId): Promise<UnifiedAgentResponse>`

**LangGraph版への移行ポイント**:
- ツール: `web_search`, `general_search`
- プロンプト: 一般的な知識への対応

### 7. ClarificationAgent（明確化）

**ファイル**: `frontend/src/mastra/agents/clarification-agent.ts`

**責任範囲**:
- 曖昧なクエリの明確化
- 複数の解釈が可能な質問への対応
- ユーザーへの確認質問

**主要機能**:
- 曖昧性の検出
- 明確化質問の生成
- 感情タグの付与

**LangGraph版への移行ポイント**:
- ツール: `clarify_query`
- プロンプト: 明確化専門家としての指示

### 8. RealtimeAgent（リアルタイム音声）

**ファイル**: `frontend/src/mastra/agents/realtime-agent.ts`

**責任範囲**:
- リアルタイム音声対話の処理
- STT（音声認識）の処理
- 会話フローの管理
- 割り込み処理
- 感情タグの付与

**主要機能**:
- 音声入力の正規化
- 会話状態の管理
- `VoiceOutputAgent`と`CharacterControlAgent`との連携

**LangGraph版への移行ポイント**:
- 音声処理の統合
- 状態管理の実装
- 割り込み処理の実装

### 9. WelcomeAgent（ウェルカム）

**ファイル**: `frontend/src/mastra/agents/welcome-agent.ts`

**責任範囲**:
- 新規訪問者への挨拶
- 言語検出
- スライドプレゼンテーションの案内
- 登録やQ&Aへの誘導

**主要機能**:
- スライド制御ツール
- 言語検出

**LangGraph版への移行ポイント**:
- ツール: `welcome_user`, `detect_language`
- プロンプト: ウェルカム専門家としての指示

### 10. SlideNarrator（スライドナレーション）

**ファイル**: `frontend/src/mastra/agents/slide-narrator.ts`

**責任範囲**:
- スライドのナレーション提供
- スライドナビゲーションの処理
- スライドコンテンツに関する質問への回答
- プレゼンテーションフローの管理

**主要機能**:
- スライド制御（`SlideControlTool`）
- ナレーションデータの読み込み
- `VoiceOutputAgent`と`CharacterControlAgent`との連携

**LangGraph版への移行ポイント**:
- ツール: `narrate_slide`, `navigate_slide`, `get_slide_content`
- プロンプト: スライドナレーション専門家としての指示

### 11. VoiceOutputAgent（音声出力）

**ファイル**: `frontend/src/mastra/agents/voice-output-agent.ts`

**責任範囲**:
- TTS（音声合成）の統合管理
- テキストのクリーニング
- エラーハンドリング
- すべてのエージェントからの音声出力要求の処理

**主要機能**:
- Google Cloud TTS統合
- テキストの前処理
- 音声出力のキャッシュ

**LangGraph版への移行ポイント**:
- ツール: `text_to_speech`, `clean_text`
- 音声サービスとの統合

### 12. CharacterControlAgent（キャラクター制御）

**ファイル**: `frontend/src/mastra/agents/character-control-agent.ts`

**責任範囲**:
- 3Dキャラクターの表情制御
- アニメーション制御
- リップシンクの生成
- 感情タグの解析

**主要機能**:
- `LipSyncAnalyzer`によるリップシンク生成
- `LipSyncCache`によるキャッシュ
- 感情タグのマッピング

**LangGraph版への移行ポイント**:
- ツール: `control_character`, `set_emotion`, `generate_lip_sync`
- フロントエンドとの連携（API経由）

## 共通パターン

### 1. 感情タグ

すべてのエージェントが感情タグを使用:
- `[happy]`: 喜び、興奮、ポジティブな応答
- `[sad]`: 失望、悲しみ、謝罪
- `[angry]`: 怒り、フラストレーション（使用は控えめに）
- `[relaxed]`: 落ち着き、情報提供、説明
- `[surprised]`: 驚き、質問、明確化

**LangGraph版への適用**:
- 状態に`emotion`フィールドを追加
- プロンプトに感情タグの指示を含める

### 2. UnifiedAgentResponse

すべてのエージェントが統一された応答形式を使用:
```typescript
interface UnifiedAgentResponse {
  answer: string;
  emotion?: string;
  metadata?: any;
}
```

**LangGraph版への適用**:
- Python版の`UnifiedAgentResponse`クラスを定義
- すべてのエージェントがこの形式で応答

### 3. SimplifiedMemorySystem

複数のエージェントが`SimplifiedMemorySystem`を使用:
- 3分間の会話ウィンドウ
- 共有メモリー（`'shared'` namespace）
- 文脈継承

**LangGraph版への適用**:
- チェックポインターとの統合
- メモリー検索ツールの実装

### 4. Enhanced RAG

`BusinessInfoAgent`と`FacilityAgent`がEnhanced RAGを使用:
- より詳細な検索
- 文脈を考慮した検索

**LangGraph版への適用**:
- RAG検索ツールの実装
- ベクトル検索の統合

## 新規実装が必要なエージェント

### OCRAgent（OCR）

**現状**: Mastra版には実装されていない

**責任範囲**（想定）:
- 画像からのテキスト抽出
- OCR処理
- 抽出テキストの解析

**実装方針**:
- Python OCRライブラリの活用（Tesseract, EasyOCR等）
- Google Vision APIの統合
- 画像前処理の実装

## 移行の優先順位

### Phase 1: 基盤エージェント
1. RouterAgent（統合エージェント）
2. MemoryAgent（記憶機能）

### Phase 2: 情報提供エージェント
3. BusinessInfoAgent
4. FacilityAgent
5. EventAgent

### Phase 3: 補助エージェント
6. GeneralKnowledgeAgent
7. ClarificationAgent

### Phase 4: 特殊エージェント
8. RealtimeAgent
9. WelcomeAgent
10. SlideNarrator
11. VoiceOutputAgent
12. CharacterControlAgent

### Phase 5: 新規エージェント
13. OCRAgent

## 参考ファイル

各エージェントの実装は以下のファイルを参照:
- `frontend/src/mastra/agents/{agent-name}.ts`
- `frontend/src/mastra/workflows/main-qa-workflow.ts`
- `frontend/src/mastra/langgraph/langgraph-workflow.ts`

