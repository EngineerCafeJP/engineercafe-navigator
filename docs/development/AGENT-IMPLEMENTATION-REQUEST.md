# エージェント完全実装依頼ドキュメント

> フェーズ9.8: 骨組み実装済みエージェントの完全実装依頼（専門エンジニア向け）

## 目次

- [概要](#概要)
- [背景と現在の状況](#背景と現在の状況)
- [実装対象エージェント](#実装対象エージェント)
  - [1. VoiceAgent 完全実装](#1-voiceagent-完全実装)
  - [2. CharacterControlAgent 完全実装](#2-charactercontrolagent-完全実装)
  - [3. MemoryAgent 完全実装](#3-memoryagent-完全実装)
- [実装支援資料](#実装支援資料)
- [実装順序の推奨](#実装順序の推奨)
- [コードレビュープロセス](#コードレビュープロセス)
- [開発環境とツール](#開発環境とツール)
- [質問・サポート](#質問サポート)

---

## 概要

このドキュメントは、Engineer Cafe Navigator プロジェクトにおいて骨組み実装が完了した3つのエージェント（VoiceAgent、CharacterControlAgent、MemoryAgent）の完全実装を担当エンジニアに依頼するためのものです。

### フェーズ7.5で完了していること

- **骨組み実装**: 各エージェントの基本クラス構造、メソッドシグネチャ、TODO コメントが完備
- **フロントエンドプロキシ**: API エンドポイントとフロントエンド連携が完了
- **実装パターン確立**: BusinessInfoAgent、EventAgent など完全実装済みエージェントが参考として利用可能

### これから実装すること

各エージェントのコア機能（STT/TTS連携、表情マッピング、メモリシステム統合など）を骨組みに実装し、受け入れ基準を満たす完全動作状態にします。

---

## 背景と現在の状況

### プロジェクトアーキテクチャ

```
backend/
├── agents/                      # LangGraphエージェント
│   ├── voice_agent.py          # ← 骨組み実装済み
│   ├── character_control_agent.py  # ← 骨組み実装済み
│   ├── memory_agent.py         # ← 骨組み実装済み
│   ├── business_info_agent.py  # ← 完全実装済み（参考）
│   └── event_agent.py          # ← 完全実装済み（参考）
├── workflows/
│   └── main_workflow.py        # LangGraphワークフロー
├── tools/                       # エージェントツール
├── utils/                       # ユーティリティ
└── llm/                        # LLMプロバイダー
```

### 技術スタック

- **Backend**: Python 3.11+, FastAPI
- **AI Framework**: LangGraph
- **LLM**: OpenRouter API
- **STT/TTS**: Google Cloud Speech-to-Text/Text-to-Speech
- **Database**: Supabase (PostgreSQL)
- **3D Character**: VRM形式
- **開発環境**: Docker, mise, Make

---

## 実装対象エージェント

## 1. VoiceAgent 完全実装

### 担当者

| 担当者 | 役割 | サポート |
|-------|------|---------|
| **Chie** | メイン実装 | たけがわ |

### 1.1 概要

音声処理（STT/TTS）を担当するエージェント。ユーザーの音声入力を認識し、システムの応答を音声で返します。

### 1.2 骨組み実装済みファイル

**ファイル**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/voice_agent.py`

骨組みには以下が含まれています:
- クラス構造とメソッドシグネチャ
- 詳細な TODO コメント
- 入出力仕様のドキュメント
- プレースホルダー実装

### 1.3 実装内容

#### 必須実装項目

1. **Google Cloud STT (Speech-to-Text) 連携**
   - 音声データ（バイト列）をテキストに変換
   - 言語コード（ja-JP, en-US）のサポート
   - 信頼度スコアの取得

2. **Google Cloud TTS (Text-to-Speech) 連携**
   - テキストを音声データに変換
   - 感情タグに応じた音声パラメータ調整（ピッチ、速度）
   - SSMLマークアップの使用

3. **STT補正システム実装**
   - カタカナ/ひらがなの統一
   - 発音の揺らぎ補正（例: 「えんじにあかふぇ」→「Engineer Cafe」）
   - 固有名詞の補正
   - LLMを使用した文脈補正

4. **感情タグ処理**
   - 応答テキストに含まれる感情タグの抽出（例: `[happy]`, `[sad]`）
   - 感情タグに基づく音声パラメータの調整
   - デフォルト感情の設定（neutral）

5. **音声ファイル管理**
   - 一時ファイルの保存と削除
   - メモリ効率的な音声データ処理

6. **エラーハンドリングとフォールバック**
   - STT/TTS API エラーのハンドリング
   - フォールバック音声の生成（謝罪メッセージ）
   - ログ出力

#### 実装メソッド

```python
async def speech_to_text(audio_data: bytes, language_code: str = "ja-JP") -> Dict[str, Any]
async def text_to_speech(text: str, language_code: str = "ja-JP", emotion: Optional[str] = None) -> Dict[str, Any]
async def correct_speech_text(text: str) -> str
async def extract_emotion_from_text(text: str) -> str
async def process(audio_data: Optional[bytes] = None, text: Optional[str] = None) -> Dict[str, Any]
```

### 1.4 参考資料

#### 必読ドキュメント

1. **移行ガイド**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/voice-agent/MIGRATION-GUIDE.md`
   - Mastra (TypeScript) → LangGraph (Python) 移行手順
   - 依存ユーティリティの Python への移植方法
   - ノード分割設計

2. **骨組み実装**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/voice_agent.py`
   - 詳細な TODO コメント
   - 入出力仕様

3. **Mastra 版実装（TypeScript）**:
   - `engineer-cafe-navigator-repo/src/mastra/agents/realtime-agent.ts`
   - `engineer-cafe-navigator-repo/src/mastra/agents/voice-output-agent.ts`
   - `engineer-cafe-navigator-repo/src/lib/stt-correction.ts`
   - `engineer-cafe-navigator-repo/src/lib/emotion-tag-parser.ts`

#### 参考実装パターン

- **BusinessInfoAgent**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/business_info_agent.py`
  - LLM連携パターン
  - エラーハンドリング
  - プロンプト構築

- **EventAgent**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/event_agent.py`
  - 外部サービス連携パターン
  - 感情タグ設定

### 1.5 受け入れ基準

#### 機能要件

- [ ] **STT機能**: 音声データをテキストに変換できる（日本語・英語対応）
- [ ] **TTS機能**: テキストを音声データに変換できる（感情タグ対応）
- [ ] **STT補正**: 固有名詞や技術用語の補正が動作する
- [ ] **感情タグ抽出**: テキストから感情タグを正しく抽出できる
- [ ] **エラーハンドリング**: API エラー時にフォールバック処理が動作する

#### 品質要件

- [ ] **コードスタイル**: Ruff, Black のチェックに合格
- [ ] **型ヒント**: すべての関数に型ヒントが付与されている
- [ ] **ドキュメント**: docstring が適切に記述されている
- [ ] **ログ出力**: 重要な処理でログが出力されている

#### パフォーマンス要件

- [ ] **STT処理**: 500ms 以下
- [ ] **TTS処理**: 1.0s 以下
- [ ] **STT補正**: 10ms 以下
- [ ] **総合処理**: 2.0s 以下（目安）

---

## 2. CharacterControlAgent 完全実装

### 担当者

| 担当者 | 役割 | サポート |
|-------|------|---------|
| **takegg0311** | メイン実装 | YukitoLyn |

### 2.1 概要

VRMキャラクターの表情・モーションを制御するエージェント。応答テキストの感情タグに基づいて、適切な表情やアニメーションを指示します。

### 2.2 骨組み実装済みファイル

**ファイル**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/character_control_agent.py`

骨組みには以下が含まれています:
- クラス構造とメソッドシグネチャ
- 詳細な TODO コメント
- 入出力仕様のドキュメント
- プレースホルダー実装

### 2.3 実装内容

#### 必須実装項目

1. **感情→表情マッピング実装**
   - 感情タグ（happy, sad, neutral, excited, confused等）を表情パラメータにマッピング
   - 表情の強度計算（0.0～1.0）
   - 表情の持続時間設定

2. **VRM制御コマンド生成**
   - VRMライブラリに応じたコマンド形式生成
   - BlendShapeの制御パラメータ生成
   - モーフターゲットの重み計算

3. **アニメーション選択ロジック実装**
   - 感情とアニメーションのマッピング
   - コンテキストに応じたアニメーション選択（挨拶、説明、質問等）
   - ランダム性の導入（同じ感情でも毎回違う動き）

4. **リップシンク制御**
   - テキストから音素（Phoneme）を抽出
   - 音素から口の形状（Viseme）にマッピング
   - タイムスタンプの計算
   - 音声データとの同期

5. **複数感情の優先順位付け**
   - 感情のブレンド（例: happy + excited → very_happy）
   - 矛盾する感情の解決（例: happy + sad → neutral）

6. **エラーハンドリングとフォールバック**
   - 無効な感情タグへのフォールバック
   - デフォルト表情の設定

#### 実装メソッド

```python
def map_emotion_to_expression(emotion: str) -> Dict[str, Any]
def generate_vrm_command(expression: str, intensity: float = 1.0) -> Dict[str, Any]
def select_animation(emotion: str, context: Optional[Dict[str, Any]] = None) -> str
def generate_lipsync_data(audio_duration: float, text: str) -> List[Dict[str, Any]]
def combine_emotions(emotions: List[str]) -> str
async def process(emotion: str, text: Optional[str] = None, audio_duration: Optional[float] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]
```

### 2.4 参考資料

#### 必読ドキュメント

1. **README**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/character-control-agent/README.md`
   - 責任範囲
   - 感情→表情マッピングテーブル
   - リップシンクシステム
   - パフォーマンス最適化

2. **骨組み実装**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/character_control_agent.py`
   - 詳細な TODO コメント
   - 入出力仕様

3. **Mastra 版実装（TypeScript）**:
   - `engineer-cafe-navigator-repo/src/mastra/agents/character-control-agent.ts`
   - `engineer-cafe-navigator-repo/src/lib/lip-sync-analyzer.ts`
   - `engineer-cafe-navigator-repo/src/lib/lip-sync-cache.ts`
   - `engineer-cafe-navigator-repo/src/lib/emotion-mapping.ts`

#### 参考実装パターン

- **BusinessInfoAgent**: プロンプト構築、メタデータ処理
- **EventAgent**: 外部データの整形とフォーマット

### 2.5 受け入れ基準

#### 機能要件

- [ ] **感情マッピング**: 全ての感情タグ（happy, sad, neutral, excited, confused等）が適切な表情にマッピングされる
- [ ] **VRM制御**: VRM制御コマンドが正しい形式で生成される
- [ ] **アニメーション選択**: 感情に応じた適切なアニメーションが選択される
- [ ] **リップシンク**: 音声データからリップシンクデータが生成される（タイムスタンプ付き）
- [ ] **複数感情処理**: 複数の感情タグが適切にブレンドまたは優先順位付けされる

#### 品質要件

- [ ] **コードスタイル**: Ruff, Black のチェックに合格
- [ ] **型ヒント**: すべての関数に型ヒントが付与されている
- [ ] **ドキュメント**: docstring が適切に記述されている
- [ ] **ログ出力**: 重要な処理でログが出力されている

#### パフォーマンス要件

- [ ] **表情マッピング**: 10ms 以下
- [ ] **リップシンク（キャッシュあり）**: 50ms 以下
- [ ] **リップシンク（新規解析）**: 1-3秒

---

## 3. MemoryAgent 完全実装

### 担当者

| 担当者 | 役割 | サポート |
|-------|------|---------|
| **takegg0311** | メイン実装 | YukitoLyn, Natsumi, Jun |

### 3.1 概要

会話履歴・記憶に関する質問に回答するエージェント。「さっき何を聞いた？」「前に話したことを覚えてる？」といった質問を処理します。

### 3.2 骨組み実装済みファイル

**ファイル**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/memory_agent.py`

骨組みには以下が含まれています:
- クラス構造とメソッドシグネチャ
- 詳細な TODO コメント
- 入出力仕様のドキュメント
- プレースホルダー実装

### 3.3 実装内容

#### 必須実装項目

1. **SimplifiedMemoryHelperとの完全統合**
   - Supabaseクライアント初期化
   - メッセージ保存（`store_message()`）
   - コンテキスト取得（`get_context()`）
   - 前回リクエストタイプ取得（`get_previous_request_type()`）
   - TTL管理（3分間の会話コンテキスト）

2. **OpenRouter API使用による回答生成**
   - OpenRouterProviderの初期化
   - モデル設定の取得（`get_model_config("qa_response")`）
   - プロンプト構築と回答生成

3. **メモリ関連質問の判定ロジック実装**
   - 質問タイプの判定（question_history, answer_history, other_option, general_memory）
   - キーワードマッチング（日本語・英語両対応）
   - 正規表現パターンの最適化

4. **質問タイプ別のプロンプト構築**
   - 質問履歴への質問
   - 回答履歴への質問
   - 「もう一つの方」系の質問
   - 一般的なメモリ関連質問

5. **感情タグの適切な設定**
   - 履歴あり: relaxed
   - 履歴なし: sad
   - もう一つ系: happy
   - 文脈不明: surprised

6. **エラーハンドリングとフォールバック**
   - メモリシステム利用不可時の処理
   - 会話履歴なし時の処理
   - LLM応答生成失敗時の処理

#### 実装メソッド

```python
async def process_memory_query(query: str, session_id: str, language: str = "ja") -> Dict[str, Any]
def detect_memory_query_type(query: str) -> str
def build_memory_prompt(query: str, context: Dict[str, Any], query_type: str, language: str = "ja") -> str
async def generate_response(prompt: str) -> str
def _determine_emotion(context: Dict[str, Any], query_type: str) -> str
```

### 3.4 参考資料

#### 必読ドキュメント

1. **完全実装ガイド**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/memory-agent/IMPLEMENTATION-GUIDE.md`
   - 実装手順（Step 1-5）
   - SimplifiedMemoryHelper完全実装
   - MemoryAgent完全実装
   - Checkpointer基盤完全実装
   - テストケース作成

2. **骨組み実装**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/memory_agent.py`
   - 詳細な TODO コメント
   - 入出力仕様

3. **Mastra 版実装（TypeScript）**:
   - `engineer-cafe-navigator-repo/src/mastra/agents/memory-agent.ts`
   - `frontend/src/lib/simplified-memory.ts`

4. **関連ファイル**:
   - `backend/utils/memory_interface.py` - Protocolインターフェース定義
   - `backend/utils/memory_helper.py` - SimplifiedMemoryHelper暫定実装
   - `backend/utils/checkpointer.py` - Checkpointer基盤

#### 参考実装パターン

- **BusinessInfoAgent**: LLM連携、プロンプト構築、エラーハンドリング
- **EventAgent**: 外部サービス連携、データ整形

### 3.5 受け入れ基準

#### 機能要件

- [ ] **メモリシステム統合**: SimplifiedMemoryHelperとの統合が完了し、会話履歴の保存・取得が動作する
- [ ] **OpenRouter API連携**: OpenRouter APIを使用して回答を生成できる
- [ ] **質問タイプ判定**: メモリ関連質問のタイプを正しく判定できる（日本語・英語両対応）
- [ ] **プロンプト構築**: 質問タイプに応じた適切なプロンプトが構築される
- [ ] **感情タグ設定**: コンテキストに応じた適切な感情タグが設定される
- [ ] **会話コンテキスト**: 3分間の会話コンテキストが保持される

#### 品質要件

- [ ] **コードスタイル**: Ruff, Black のチェックに合格
- [ ] **型ヒント**: すべての関数に型ヒントが付与されている
- [ ] **ドキュメント**: docstring が適切に記述されている
- [ ] **ログ出力**: 重要な処理でログが出力されている
- [ ] **テストカバレッジ**: `test_memory_helper.py`, `test_memory_agent.py` が作成され、主要機能がテストされている

#### パフォーマンス要件

- [ ] **メモリ取得**: 200ms 以下
- [ ] **LLM応答生成**: 2.0s 以下
- [ ] **総合処理**: 2.5s 以下

---

## 実装支援資料

### フェーズ9.1-9.7 ドキュメント

以下のドキュメントが実装支援として利用可能です:

1. **フェーズ9.1: ローカル開発環境セットアップ**
   - Docker Compose環境
   - mise + Makefile構成
   - 環境変数設定

2. **フェーズ9.2: 環境変数ドキュメント整備**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/ENVIRONMENT-VARIABLES.md`
   - 全環境変数の説明と設定方法

3. **フェーズ9.3: エージェント実装チェックリスト**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/AGENT-IMPLEMENTATION-CHECKLIST.md`
   - 実装前・中・後のチェック項目

4. **フェーズ9.4: エージェントクイックスタートガイド**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/AGENT-QUICKSTART.md`
   - 新規エージェント作成手順

5. **フェーズ9.5: ローカル開発環境ドキュメント**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/LOCAL-DEVELOPMENT-SETUP.md`
   - Docker, mise, Makefileの使用方法

6. **フェーズ9.6: 開発ガイド統合**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/DEVELOPER-GUIDE.md`
   - プロジェクト全体の開発ガイド

7. **フェーズ9.7: Claude.md統合**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/development/CLAUDE.md`
   - Claude Code向け開発コマンド集

### 参考実装済みエージェント

以下のエージェントは完全実装済みで、実装パターンの参考になります:

1. **BusinessInfoAgent**
   - **ファイル**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/business_info_agent.py`
   - **参考ポイント**:
     - Enhanced RAG連携パターン
     - LLMプロバイダー使用方法
     - プロンプト構築
     - エラーハンドリング
     - 感情タグ設定

2. **EventAgent**
   - **ファイル**: `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/backend/agents/event_agent.py`
   - **参考ポイント**:
     - 外部サービス連携（CalendarService）
     - データ整形とフォーマット
     - 時間範囲抽出
     - 多言語対応
     - デフォルトレスポンス処理

### 移行ガイド

各エージェントの詳細な移行ガイドが用意されています:

1. **VoiceAgent移行ガイド**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/voice-agent/MIGRATION-GUIDE.md`

2. **CharacterControlAgent README**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/character-control-agent/README.md`

3. **MemoryAgent実装ガイド**
   - `/Users/teradakousuke/Developer/engineer-cafe-navigator2025/docs/migration/agents/memory-agent/IMPLEMENTATION-GUIDE.md`

---

## 実装順序の推奨

以下の順序で実装することを推奨します:

### Phase 1: MemoryAgent 実装（Week 1-2）

**理由**: 他のエージェントの基盤となるため最優先

1. **Week 1**: SimplifiedMemoryHelper完全実装
   - Supabaseクライアント初期化
   - メッセージ保存・取得機能
   - TTL管理

2. **Week 2**: MemoryAgent本体実装
   - OpenRouter API統合
   - 質問判定ロジック
   - プロンプト構築
   - テストケース作成

**担当**: takegg0311（サポート: YukitoLyn, Natsumi, Jun）

**完了基準**:
- SimplifiedMemoryHelperがSupabaseと連携して動作
- MemoryAgentが「さっき何を聞いた？」系の質問に回答可能
- テストがすべてパス（Ruff, Black, pytest）

---

### Phase 2: VoiceAgent 実装（Week 3-4）

**理由**: CharacterControlAgentの入力となるため

1. **Week 3**: STT/TTS基本機能実装
   - Google Cloud STT連携
   - Google Cloud TTS連携
   - エラーハンドリング

2. **Week 4**: 補正・感情処理実装
   - STT補正システム
   - 感情タグ抽出
   - 音声ファイル管理

**担当**: Chie（サポート: たけがわ）

**完了基準**:
- 音声データをテキストに変換できる
- テキストを音声データに変換できる（感情タグ対応）
- STT補正が動作する
- パフォーマンス要件を満たす（STT: 500ms以下、TTS: 1.0s以下）

---

### Phase 3: CharacterControlAgent 実装（Week 5-6）

**理由**: VoiceAgentの出力を使用するため

1. **Week 5**: 基本機能実装
   - 感情→表情マッピング
   - VRM制御コマンド生成
   - アニメーション選択

2. **Week 6**: リップシンク実装
   - リップシンクデータ生成
   - 音声データとの同期
   - パフォーマンス最適化

**担当**: takegg0311（サポート: YukitoLyn）

**完了基準**:
- 感情タグから適切な表情が生成される
- VRM制御コマンドが正しい形式で生成される
- リップシンクが動作する
- パフォーマンス要件を満たす（表情マッピング: 10ms以下、リップシンク: 50ms以下）

---

### Phase 4: 統合テストとデバッグ（Week 7）

全エージェントの統合テストとデバッグを実施:

1. **統合テスト**:
   - MemoryAgent + VoiceAgent 連携テスト
   - VoiceAgent + CharacterControlAgent 連携テスト
   - 全エージェント連携テスト

2. **パフォーマンステスト**:
   - エンドツーエンドの応答時間測定
   - ボトルネック特定と最適化

3. **エラーハンドリングテスト**:
   - 各種エラーケースのテスト
   - フォールバック処理の検証

**担当**: 全員

**完了基準**:
- すべての統合テストがパス
- パフォーマンス要件を満たす
- エラーケースが適切にハンドリングされる

---

## コードレビュープロセス

### レビューフロー

```
実装完了
    ↓
セルフレビュー（チェックリスト確認）
    ↓
PR作成（feature/agent-{name}-implementation）
    ↓
CI/CD自動チェック（Ruff, Black, pytest）
    ↓
コードレビュー（レビュアー指定）
    ↓
修正・再レビュー
    ↓
承認
    ↓
mainブランチへマージ
```

### レビュアー指定

| エージェント | 実装担当 | レビュアー |
|------------|---------|-----------|
| MemoryAgent | takegg0311 | YukitoLyn, テリスケ |
| VoiceAgent | Chie | たけがわ, テリスケ |
| CharacterControlAgent | takegg0311 | YukitoLyn, テリスケ |

### レビュー観点

1. **機能性**:
   - 受け入れ基準をすべて満たしているか
   - エッジケースが考慮されているか
   - エラーハンドリングが適切か

2. **コード品質**:
   - Ruff, Blackのチェックに合格しているか
   - 型ヒントが適切に付与されているか
   - docstringが適切に記述されているか
   - ログ出力が適切か

3. **パフォーマンス**:
   - パフォーマンス要件を満たしているか
   - 不要な処理がないか
   - キャッシュやバッチ処理が適切か

4. **保守性**:
   - コードが読みやすいか
   - 適切に関数が分割されているか
   - マジックナンバーが排除されているか
   - テストが十分にカバーされているか

### PR テンプレート

```markdown
## 概要
[実装内容の概要]

## 関連Issue
- Fixes #XXX

## 実装内容
- [ ] 主要機能1
- [ ] 主要機能2
- [ ] 主要機能3

## 受け入れ基準チェック
- [ ] 機能要件をすべて満たしている
- [ ] 品質要件をすべて満たしている
- [ ] パフォーマンス要件をすべて満たしている

## CI/CDチェック
- [ ] Ruff: ✅ PASS
- [ ] Black: ✅ PASS
- [ ] pytest: ✅ PASS

## テスト方法
[テスト手順の説明]

## スクリーンショット（任意）
[必要に応じて]

## 備考
[追加情報]
```

---

## 開発環境とツール

### 必須ツール

1. **Python 3.11+**
   ```bash
   mise install python@3.11
   ```

2. **Docker & Docker Compose**
   - ローカル開発環境（PostgreSQL, Supabase）

3. **mise**
   - バージョン管理ツール
   ```bash
   brew install mise
   ```

4. **Make**
   - タスク実行ツール

### 環境セットアップ

```bash
# 1. リポジトリクローン
git clone <repository-url>
cd engineer-cafe-navigator2025

# 2. 環境変数設定
cp backend/.env.example backend/.env
# .envファイルを編集して必要な環境変数を設定

# 3. Docker環境起動
cd backend
make dev-up

# 4. 依存関係インストール
mise install
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 5. データベースマイグレーション
make db-migrate

# 6. 開発サーバー起動
make dev
```

### コード品質チェック

```bash
# Ruff (リンター)
cd backend
ruff check .

# Black (フォーマッター)
black --check .

# pytest (テスト)
pytest tests/ -v
```

### よく使うコマンド

```bash
# 開発環境起動
make dev-up

# 開発環境停止
make dev-down

# ログ確認
make dev-logs

# データベースリセット
make db-reset

# テスト実行
make test

# コード品質チェック（Ruff + Black）
make lint
```

---

## 質問・サポート

### 質問がある場合

1. **ドキュメントを確認**:
   - 本ドキュメント
   - 移行ガイド
   - 実装ガイド
   - チェックリスト

2. **既存実装を参照**:
   - BusinessInfoAgent
   - EventAgent
   - Mastra版実装（TypeScript）

3. **チームに相談**:
   - Slack `#engineer-cafe-navigator` チャンネル
   - 担当サポートに直接連絡

### サポート体制

| エージェント | 担当 | サポート | 連絡方法 |
|------------|------|---------|---------|
| MemoryAgent | takegg0311 | YukitoLyn, Natsumi, Jun | Slack DM / チャンネル |
| VoiceAgent | Chie | たけがわ | Slack DM / チャンネル |
| CharacterControlAgent | takegg0311 | YukitoLyn | Slack DM / チャンネル |

### よくある質問（FAQ）

#### Q1: Google Cloud の認証情報はどこで取得できますか？

A1: `config/service-account-key.json` を使用します。ファイルがない場合は、プロジェクトマネージャーに依頼してください。

#### Q2: OpenRouter APIキーの設定方法は？

A2: `backend/.env` ファイルに `OPENROUTER_API_KEY=your-api-key` を設定します。詳細は `docs/development/ENVIRONMENT-VARIABLES.md` を参照してください。

#### Q3: Supabaseの接続情報はどこで確認できますか？

A3: `backend/.env` ファイルに以下を設定します:
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DB_URI=postgresql://postgres:password@host:port/database
```

#### Q4: テストが失敗する場合の対処法は？

A4: 以下を確認してください:
1. 環境変数が正しく設定されているか
2. Dockerコンテナが起動しているか（`make dev-up`）
3. データベースマイグレーションが完了しているか（`make db-migrate`）
4. 依存関係が最新か（`pip install -r requirements.txt`）

#### Q5: CI/CDでRuff/Blackが失敗する場合は？

A5: ローカルで以下を実行してください:
```bash
# Ruffで自動修正
ruff check . --fix

# Blackでフォーマット
black .

# 再度チェック
ruff check .
black --check .
```

#### Q6: パフォーマンス要件を満たせない場合は？

A6: 以下を試してください:
1. ログ出力で処理時間をプロファイリング
2. ボトルネックを特定
3. キャッシュやバッチ処理の導入を検討
4. サポートチームに相談

---

## まとめ

このドキュメントでは、以下の3つのエージェントの完全実装について説明しました:

1. **VoiceAgent**: 音声処理（STT/TTS、補正、感情タグ）
2. **CharacterControlAgent**: キャラクター制御（表情、アニメーション、リップシンク）
3. **MemoryAgent**: メモリシステム（会話履歴、コンテキスト管理）

### 実装の流れ

1. **Phase 1（Week 1-2）**: MemoryAgent実装
2. **Phase 2（Week 3-4）**: VoiceAgent実装
3. **Phase 3（Week 5-6）**: CharacterControlAgent実装
4. **Phase 4（Week 7）**: 統合テストとデバッグ

### 成功のための重要ポイント

1. **ドキュメントを熟読**: 移行ガイド、実装ガイド、チェックリストを活用
2. **既存実装を参考**: BusinessInfoAgent、EventAgentのパターンを踏襲
3. **小さく始めて段階的に**: 基本機能から実装し、徐々に拡張
4. **テストを書く**: 実装と並行してテストケースを作成
5. **早めに相談**: 疑問点はサポートチームに早めに相談
6. **CI/CDを活用**: Ruff, Black, pytestを定期的に実行

### 連絡先

- **プロジェクトマネージャー**: テリスケ
- **技術サポート**: YukitoLyn, たけがわ, Natsumi, Jun
- **Slackチャンネル**: `#engineer-cafe-navigator`

皆さんの実装を楽しみにしています。Good luck!
