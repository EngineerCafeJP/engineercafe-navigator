# システムシーケンス図

> 注意: この文書には RouterAgent / MemoryAgent 前提の旧シーケンスが含まれます。現行の request path 判断には `docs/STATUS.md` と実装コードを優先してください。

> フロント画面の入力〜バックエンド処理〜フロント画面への出力までを、現在想定している流れで Mermaid シーケンス図として記述する。
> このドキュメントは、今後の設計に応じて更新していく。

---

## 1. 全体フロー概要（音声・テキスト入力 → 応答出力）

```mermaid
sequenceDiagram
    autonumber
    actor User as ユーザー
    participant UI as フロント画面<br/>(VoiceInterface / テキスト入力)
    participant NextAPI as Next.js API Routes<br/>(/api/voice, /api/qa)
    participant Backend as バックエンド<br/>(FastAPI)
    participant Workflow as MainWorkflow<br/>(LangGraph)
    participant Agents as 専門エージェント群

    User->>UI: 入力（音声 / テキスト）
    UI->>NextAPI: POST /api/voice または /api/qa
    NextAPI->>Backend: プロキシ（/api/voice または /api/chat）
    Backend->>Workflow: ainvoke(query, session_id, language)
    Workflow->>Workflow: router → 専門エージェントへ振分け
    Workflow->>Agents: ルーティング先エージェント実行
    Agents-->>Workflow: answer, emotion, metadata
    Workflow-->>Backend: 応答
    Backend-->>NextAPI: answer, emotion, (audioResponse)
    NextAPI-->>UI: 応答データ
    UI->>UI: テキスト表示 / 音声再生 / VRM表情・リップシンク
    UI-->>User: 出力（テキスト・音声・キャラクター）
```

---

## 2. 音声入力フロー（詳細）

音声のみの経路：STT → QA（チャット）→ TTS → キャラクター制御。

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant Page as page.tsx
    participant VoiceAPI as /api/voice
    participant Backend as バックエンド
    participant ChatAPI as /api/chat
    participant Workflow as MainWorkflow
    participant Char as VRMキャラクター<br/>CharacterAvatar
    participant Audio as 音声再生<br/>AudioPlaybackService

    User->>Page: 音声入力（録音）
    Page->>VoiceAPI: POST action: speech_to_text, audioData
    VoiceAPI->>Backend: POST /api/voice
    Backend-->>VoiceAPI: transcript（※現状バックエンドはプレースホルダー）
    VoiceAPI-->>Page: transcript

    Page->>VoiceAPI: POST /api/qa（question: transcript） または Backend /api/chat へ直接
    VoiceAPI->>ChatAPI: プロキシ → Backend /api/chat
    ChatAPI->>Workflow: ainvoke(query, session_id, language)
    Workflow->>Workflow: router → 専門エージェント → format_response
    Workflow-->>ChatAPI: answer, emotion, metadata
    ChatAPI-->>Page: answer, emotion

    Page->>VoiceAPI: POST action: text_to_speech, text: answer
    VoiceAPI->>Backend: POST /api/voice (TTS)
    Backend-->>VoiceAPI: audioResponse (base64)
    VoiceAPI-->>Page: audioResponse

    Page->>Char: emotion → setExpression / handleCharacterControl
    Page->>Audio: playAudioWithLipSync(audioResponse)
    Audio-->>User: 音声再生 + リップシンク
    Char-->>User: 表情・動作表示
```

※ 現状、バックエンドの `/api/voice` はプレースホルダー実装のため、STT/TTS はフロントまたは別サービス連携を想定した流れです。

---

## 3. テキスト入力フロー（Q&A）

テキストのみの経路：質問 → /api/qa → /api/chat → MainWorkflow → 応答 → 表示・キャラクター。

RouterAgent がバックエンドの窓口となり、MemoryAgent を含む専門エージェントへ振り分ける。MemoryAgent は直近の会話履歴の参照や、FAQ のように同種の問答があれば他専門エージェントを介さず回答を生成する役割を持つ。

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant UI as フロント画面
    participant QA as /api/qa
    participant Backend as バックエンド<br/>/api/chat
    participant Workflow as MainWorkflow
    participant Router as RouterAgent
    participant Agent as 専門エージェント<br/>（1つにルーティング）
    participant Format as format_response

    User->>UI: テキストで質問入力
    UI->>QA: POST question, sessionId, language
    QA->>Backend: POST /api/chat (query, session_id, language)
    Backend->>Workflow: ainvoke(input_data)

    Workflow->>Router: ルーティング判定
    Router-->>Workflow: routed_to (clarification / business_info / facility / event / slide / general_knowledge / memory_agent)
    Workflow->>Agent: 該当エージェント実行
    Agent-->>Workflow: answer, emotion, metadata
    Workflow->>Format: 応答フォーマット
    Format-->>Workflow: messages 更新
    Workflow-->>Backend: answer, emotion, metadata
    Backend-->>QA: answer, emotion, metadata
    QA-->>UI: success, answer, emotion, metadata
    UI->>UI: テキスト表示・VRM表情反映
    UI-->>User: 回答表示・キャラクター表情
```

---

## 4. バックエンド MainWorkflow（LangGraph）内部

RouterAgent が窓口となり、MemoryAgent を含む専門エージェントへ振り分ける流れ。MemoryAgent は直近会話履歴の参照や、同種問答（FAQ 的）の場合は他エージェントを介さず回答を生成する。

```mermaid
sequenceDiagram
    participant Invoke as ainvoke(input)
    participant Router as RouterAgent
    participant Cond as 条件分岐
    participant Clarify as clarification
    participant Business as business_info
    participant Facility as facility
    participant Event as event
    participant Slide as slide
    participant General as general_knowledge
    participant MemAgent as MemoryAgent
    participant Format as format_response

    Invoke->>Router: クエリ・セッションでルーティング
    Router-->>Invoke: routed_to, metadata
    Invoke->>Cond: routed_to に応じて分岐
    Cond->>Clarify: clarification
    Cond->>Business: business_info
    Cond->>Facility: facility
    Cond->>Event: event
    Cond->>Slide: slide
    Cond->>General: general_knowledge
    Cond->>MemAgent: memory_agent

    Clarify-->>Format: answer, emotion
    Business-->>Format: answer, emotion
    Facility-->>Format: answer, emotion
    Event-->>Format: answer, emotion
    Slide-->>Format: answer, emotion
    General-->>Format: answer, emotion
    MemAgent-->>Format: answer, emotion

    Format->>Format: messages に HumanMessage / AIMessage 追加
    Format-->>Invoke: 最終 state（answer, emotion, metadata）
```

※ 実装では、Router の前に会話コンテキスト取得用の memory ノードを実行している場合がある。設計上の窓口は RouterAgent であり、MemoryAgent は専門エージェントの一つとして振り分け先となる。

---

## 5. スライド操作フロー（参考）

スライド表示・ナレーション・スライド上での質問は、MainWorkflow を経由せずバックエンドの SlideAgent を直接呼ぶ経路もある。

```mermaid
sequenceDiagram
    actor User as ユーザー
    participant Marp as MarpViewer
    participant SlidesAPI as /api/slides
    participant Backend as バックエンド<br/>/api/slides
    participant SlideAgent as SlideAgent

    User->>Marp: スライド操作（next/previous）またはスライド上で質問
    Marp->>SlidesAPI: POST action, (question), language
    SlidesAPI->>Backend: プロキシ
    Backend->>SlideAgent: handle_slide_action(action, query, language)
    SlideAgent-->>Backend: answer, emotion, slideNumber, metadata
    Backend-->>SlidesAPI: success, answer, emotion, slideNumber
    SlidesAPI-->>Marp: 応答
    Marp->>Marp: スライド更新・音声再生（必要時）
    Marp-->>User: 表示・音声
```

---

## 6. 入力・出力の対応まとめ

| 種別 | 入力 | 主なAPI | バックエンド処理 | 出力 |
|------|------|---------|------------------|------|
| **音声** | マイク録音（base64） | POST /api/voice (speech_to_text, text_to_speech) | QA 部分は /api/chat → MainWorkflow | テキスト表示・音声再生・VRMリップシンク・表情 |
| **テキスト** | テキスト質問 | POST /api/qa → Backend /api/chat | MainWorkflow (router → 専門エージェント → format_response) | テキスト表示・VRM表情 |
| **画像** | 現状なし | — | — | 背景画像・スライド用画像は設定パネル/静的配置のみ。Q&A の画像入力は想定外 |
| **スライド** | 操作・スライド内質問 | POST /api/slides | SlideAgent 直接 | スライド表示・ナレーション音声・回答表示 |

---

## 7. 既存ドキュメント

- [frontend/README.md](../../frontend/README.md): Mermaid の アーキテクチャ構成図（graph TB）あり
- [backend/README.md](../../backend/README.md)
- [SYSTEM-ARCHITECTURE.md](SYSTEM-ARCHITECTURE.md): データフローのテキスト説明あり
- **本ドキュメント**: 上記を補う形で、想定しているシーケンスを Mermaid で初めてまとめたもの。

更新時は上記ドキュメントとの整合性を取ること
