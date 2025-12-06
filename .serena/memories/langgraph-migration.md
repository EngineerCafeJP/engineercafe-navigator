# Engineer Cafe Navigator - LangGraph Migration Guide

## Overview

現在のMastra (TypeScript) 実装からLangGraph (Python) への移行を計画中です。
詳細な移行ドキュメントは `/docs/migration/agents/` に各エージェントごとに用意されています。

**Last Updated:** 2025-12-06

## エージェント別担当者一覧

| エージェント | 担当者 | サポート | ステータス |
|-------------|--------|----------|-----------|
| **RouterAgent** | テリスケ | YukitoLyn | 既存あり |
| **BusinessInfoAgent** | テリスケ | - | 既存あり |
| **FacilityAgent** | Natsumi | けいてぃー | 既存あり |
| **EventAgent** | テリスケ | - | 既存あり |
| **MemoryAgent** | takegg0311 | YukitoLyn, Natsumi, Jun | 既存あり |
| **ClarificationAgent** | Chie | Jun | 既存あり |
| **LanguageClassifier** | Chie | Jun | 既存あり |
| **GeneralKnowledgeAgent** | テリスケ | - | 既存あり |
| **CharacterControlAgent** | takegg0311 | YukitoLyn | 既存あり |
| **VoiceAgent** | Chie | たけがわ | 既存あり |
| **SlideAgent** | テリスケ | - | 既存あり |
| **OCRAgent** | けいてぃー | たけがわ | **新規** (Mastra実装なし) |

## ドキュメント構成

```
docs/migration/agents/
├── router-agent/
│   ├── README.md          # 概要、責任範囲、設計
│   ├── SPEC.md            # 詳細仕様
│   ├── MIGRATION-GUIDE.md # 移行手順
│   └── TESTING.md         # テスト計画
├── business-info-agent/
│   └── README.md
├── facility-agent/
│   └── README.md
├── event-agent/
│   └── README.md
├── memory-agent/
│   └── README.md
├── clarification-agent/
│   └── README.md
├── language-classifier/
│   └── README.md
├── general-knowledge-agent/
│   └── README.md
├── character-control-agent/
│   └── README.md
├── voice-agent/
│   └── README.md
├── slide-agent/
│   └── README.md
└── ocr-agent/
    └── README.md          # 新機能 (Mastra実装なし)
```

## 各エージェントの詳細

### 1. RouterAgent (テリスケ担当)

**役割**: クエリの分類とルーティング

**現在の実装**: `/frontend/src/mastra/agents/router-agent.ts`

**LangGraph設計**:
```python
def router_node(state: WorkflowState) -> dict:
    query = state["query"]
    language = state["language"]
    history = state.get("history", [])
    
    route = classify_query(query, language, history)
    
    return {
        "route": route.agent,
        "confidence": route.confidence,
        "metadata": {"agent": "RouterAgent"}
    }
```

**ルーティング先**:
- `business_info`: 営業時間、料金、場所
- `facility`: 設備、Wi-Fi、地下
- `event`: イベント、カレンダー
- `memory`: 会話履歴関連
- `clarification`: 曖昧な質問
- `general`: その他

### 2. BusinessInfoAgent (テリスケ担当)

**役割**: 営業時間、料金、アクセス情報

**主要カテゴリ**:
- 営業時間 (hours)
- 料金 (pricing)
- 場所/アクセス (location)

**LangGraph設計**:
```python
def business_info_node(state: WorkflowState) -> dict:
    query = state["query"]
    language = state["language"]
    
    context = enhanced_rag_search(
        query, 
        category="business-info",
        language=language
    )
    
    response = generate_response(query, context, language)
    
    return {
        "response": response.text,
        "emotion": response.emotion,
        "sources": context.sources
    }
```

### 3. FacilityAgent (Natsumi担当, けいてぃーサポート)

**役割**: 設備、地下施設、Wi-Fi情報

**対象施設**:
- 地下MTGスペース (Basement Meeting Space)
- 地下集中スペース (Focus Space)
- アンダースペース (Under Space)
- Makersスペース
- Wi-Fi、電源、機材

**LangGraph設計**:
```python
def facility_node(state: WorkflowState) -> dict:
    query = state["query"]
    language = state["language"]
    
    # 地下施設キーワード検出
    is_basement = detect_basement_keywords(query)
    
    context = enhanced_rag_search(
        expand_facility_query(query),
        category="facility-info",
        priority_basement=is_basement
    )
    
    return {
        "response": generate_facility_response(query, context),
        "facilities": context.matched_facilities
    }
```

### 4. MemoryAgent (takegg0311担当)

**役割**: 会話履歴の管理と参照

**機能**:
- 会話履歴の保存 (3分TTL)
- 「さっき何を聞いた？」への回答
- コンテキスト継承

**LangGraph設計**:
```python
def memory_node(state: WorkflowState) -> dict:
    session_id = state["session_id"]
    query = state["query"]
    
    # 会話履歴を取得
    history = get_conversation_history(session_id)
    
    # メモリ関連の質問か判定
    if is_memory_question(query):
        return {
            "response": format_history_response(history),
            "history": history
        }
    
    return {"history": history}
```

### 5. EventAgent (テリスケ担当)

**役割**: イベント・カレンダー情報

**データソース**:
- Connpass API (Engineer Cafe events)
- Google Calendar API

**LangGraph設計**:
```python
def event_node(state: WorkflowState) -> dict:
    query = state["query"]
    language = state["language"]
    
    events = fetch_upcoming_events(days=30)
    
    if "today" in query or "今日" in query:
        events = filter_today_events(events)
    
    return {
        "response": format_events_response(events, language),
        "events": events
    }
```

### 6. ClarificationAgent (Chie担当, Junサポート)

**役割**: 曖昧な質問の解消

**対象**:
- 「カフェ」→ エンジニアカフェ or Sainoカフェ
- 「会議室」→ どの会議室?
- 不明確な時間帯指定

**LangGraph設計**:
```python
def clarification_node(state: WorkflowState) -> dict:
    query = state["query"]
    language = state["language"]
    
    ambiguity = detect_ambiguity(query)
    
    if ambiguity.type == "cafe":
        options = ["エンジニアカフェ", "Sainoカフェ"]
    elif ambiguity.type == "meeting_room":
        options = get_meeting_room_options()
    
    return {
        "response": generate_clarification_question(options, language),
        "awaiting_clarification": True,
        "options": options
    }
```

### 7. VoiceAgent (Chie担当, たけがわサポート)

**役割**: STT/TTS処理

**コンポーネント**:
- Speech-to-Text (Google Cloud STT)
- Text-to-Speech (Google Cloud TTS)
- STT補正システム
- 感情タグ処理

**LangGraph設計**:
```python
def stt_node(state: WorkflowState) -> dict:
    audio_base64 = state["audio_data"]
    language = state["language"]
    
    result = await speech_to_text(audio_base64, language)
    corrected = stt_correction.correct(result.transcript)
    
    return {
        "transcript": corrected,
        "confidence": result.confidence
    }

def tts_node(state: WorkflowState) -> dict:
    text = state["response"]
    language = state["language"]
    
    parsed = emotion_tag_parser.parse(text)
    clean_text = tts_preprocess(parsed.clean_text, language)
    audio_data = await text_to_speech(clean_text, language, parsed.emotion)
    
    return {
        "audio_data": audio_data,
        "emotion": parsed.emotion
    }
```

### 8. CharacterControlAgent (takegg0311担当)

**役割**: VRMキャラクター制御

**機能**:
- 表情マッピング (感情→表情)
- アニメーション選択
- リップシンク生成

**感情→表情マッピング**:
| 感情 | VRM表情 | アニメーション |
|------|---------|---------------|
| happy | happy | greeting |
| sad | sad | thinking |
| angry | angry | explaining |
| relaxed | neutral | idle |
| surprised | surprised | greeting |

### 9. SlideAgent (テリスケ担当)

**役割**: スライドナレーション

**機能**:
- スライド説明の音声化
- ナビゲーション (次へ/前へ/指定)
- スライド関連の質問応答
- 自動再生

**ナレーションデータ**:
```
/frontend/src/slides/narration/
├── engineer-cafe-ja.json
└── engineer-cafe-en.json
```

### 10. OCRAgent (けいてぃー担当) **NEW**

**役割**: 画像認識・文字認識 (新機能)

**注意**: Mastra実装なし。LangGraphで新規実装。

**計画機能**:
1. **文字認識 (OCR)**: 番号、テキスト、QRコード
2. **表情認識**: ユーザーの感情検出

**技術選定候補**:
- OCR: Google Cloud Vision / Tesseract.js / Azure CV
- 表情: face-api.js / Google ML Kit

**想定フロー**:
```
1. Clarification Agentが選択肢を提示
   「1. エンジニアカフェ  2. Sainoカフェ」

2. ユーザーが番号（1 or 2）をかざす

3. OCR Agentが番号を認識
   → recognized: "1"

4. Router Agentが選択を処理
   → BusinessInfoAgent（エンジニアカフェ）へ
```

**LangGraph設計**:
```python
def ocr_node(state: WorkflowState) -> dict:
    image_data = state.get("image_data")
    ocr_type = state.get("ocr_type", "text")
    
    if ocr_type == "number":
        result = recognize_number(image_data)
    elif ocr_type == "qr":
        result = recognize_qr(image_data)
    else:
        result = recognize_text(image_data)
    
    return {
        "ocr_result": result,
        "metadata": {"agent": "OCRAgent"}
    }
```

**担当者チェックリスト** (けいてぃー向け):
- [ ] 技術選定を完了した（OCRライブラリ、表情認識ライブラリ）
- [ ] プライバシーポリシーを確認した
- [ ] カメラアクセスのUI/UXを設計した
- [ ] 番号認識の実装を完了した
- [ ] 表情認識の実装を完了した

## 移行優先順位

### Phase 1: コア機能
1. RouterAgent (ルーティングの基盤)
2. BusinessInfoAgent (最も使用頻度が高い)
3. FacilityAgent (地下施設情報が重要)

### Phase 2: 会話機能
4. MemoryAgent (コンテキスト維持)
5. ClarificationAgent (曖昧さ解消)
6. LanguageClassifier (言語検出)

### Phase 3: 出力機能
7. VoiceAgent (STT/TTS)
8. CharacterControlAgent (VRM制御)
9. SlideAgent (プレゼン)

### Phase 4: 新機能
10. OCRAgent (新規実装)
11. EventAgent (カレンダー連携)
12. GeneralKnowledgeAgent (Web検索)

## 共通LangGraph State定義

```python
class WorkflowState(TypedDict):
    # Input
    query: str
    language: Literal["ja", "en"]
    session_id: str
    
    # Optional input
    audio_data: Optional[str]  # base64
    image_data: Optional[bytes]
    
    # Routing
    route: Optional[str]
    confidence: Optional[float]
    
    # Memory
    history: List[Dict]
    
    # Output
    response: Optional[str]
    emotion: Optional[str]
    sources: Optional[List[str]]
    
    # Character
    character_control: Optional[Dict]
    
    # Metadata
    metadata: Dict
```

## バックエンド現状

**Location**: `/backend/`

**現状**:
- FastAPI skeleton (`main.py`)
- LangGraph StateGraph (`workflows/main_workflow.py`)
- 全ノードはTODO状態

**次のステップ**:
1. 上記ノード定義を実装
2. Enhanced RAGツールをPythonに移植
3. Supabase連携を実装
4. Google Cloud音声連携を実装
