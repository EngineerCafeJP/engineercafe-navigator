# Voice Agent

> 音声入出力（STT/TTS）を担当するエージェント

## 担当者

| 担当者 | 役割 |
|-------|------|
| **Chie** | メイン実装 |
| **たけがわ** | レビュー・サポート |

## 概要

Voice Agentは、音声の入出力処理を担当します。Speech-to-Text（音声認識）とText-to-Speech（音声合成）の両方を統括し、リアルタイム音声インタラクションを実現します。Google Cloud Speech APIと連携し、日本語/英語の両方に対応します。

## 責任範囲

### 主要責務

| 責務 | 説明 |
|------|------|
| **音声認識(STT)** | 音声データをテキストに変換 |
| **音声合成(TTS)** | テキストを音声データに変換 |
| **STT補正** | 認識誤りの自動補正 |
| **感情タグ処理** | 感情タグの解析・除去 |
| **テキスト前処理** | TTS用のテキストクリーニング |

### 責任範囲外

- AI回答生成（各専門エージェントの責務）
- キャラクター制御（CharacterControlAgentの責務）

## アーキテクチャ上の位置づけ

```
[マイク入力]
     │
     ▼
┌─────────────────┐
│  Voice Agent    │ ← このエージェント
│    (STT)        │
└────────┬────────┘
         │ テキスト
         ▼
┌─────────────────┐
│  Router Agent   │
│  → 専門Agent    │
└────────┬────────┘
         │ 回答テキスト
         ▼
┌─────────────────┐
│  Voice Agent    │ ← このエージェント
│    (TTS)        │
└────────┬────────┘
         │ 音声データ
         ▼
[スピーカー出力]
```

## コンポーネント構成

### 関連ファイル（Mastra実装）

```
engineer-cafe-navigator-repo/src/
├── mastra/agents/
│   ├── voice-output-agent.ts    # TTS処理
│   └── realtime-agent.ts        # リアルタイム音声処理
├── lib/
│   ├── stt-correction.ts        # STT補正
│   └── emotion-tag-parser.ts    # 感情タグ解析
└── utils/
    └── tts-preprocess.ts        # TTS前処理
```

## STT（音声認識）処理

### 処理フロー

```
[音声データ (ArrayBuffer)]
         │
         ▼ Base64エンコード
┌─────────────────────────┐
│  Google Cloud STT API   │
└───────────┬─────────────┘
            │ transcript, confidence
            ▼
┌─────────────────────────┐
│    STT Correction       │
│  (認識誤り補正)          │
└───────────┬─────────────┘
            │ 補正済みテキスト
            ▼
        [出力]
```

### STT補正の例

```typescript
// よくある認識誤り → 正しい表記
'エンジンカフェ' → 'エンジニアカフェ'
'コーヒーセイノ' → 'Sainoカフェ'
'才能カフェ' → 'Sainoカフェ'
```

### 品質チェック

```typescript
interface QualityCheck {
  isValid: boolean;
  reason?: 'no_transcript' | 'low_confidence' | 'too_short' | 'gibberish' | 'user_unclear';
  confidence?: number;
}
```

## TTS（音声合成）処理

### 処理フロー

```
[回答テキスト（感情タグ付き）]
         │
         ▼
┌─────────────────────────┐
│  Emotion Tag Parser     │
│  (感情タグ抽出・除去)    │
└───────────┬─────────────┘
            │ cleanText, emotion
            ▼
┌─────────────────────────┐
│   TTS Preprocess        │
│  (テキストクリーニング)   │
└───────────┬─────────────┘
            │ 前処理済みテキスト
            ▼
┌─────────────────────────┐
│  Google Cloud TTS API   │
└───────────┬─────────────┘
            │ AudioBuffer
            ▼
        [音声出力]
```

### TTS前処理

```typescript
// Markdownの除去
'**重要**な情報' → '重要な情報'

// 略語の展開
'MTGスペース' → 'ミーティングスペース'

// 特殊文字の除去
'Wi-Fi (無料)' → 'ワイファイ 無料'
```

## 入出力仕様

### VoiceOutputRequest

```typescript
interface VoiceOutputRequest {
  text: string;              // 回答テキスト（感情タグ含む）
  language: 'ja' | 'en';     // 言語
  emotion?: string;          // 感情（オプション）
  sessionId?: string;        // セッションID
  agentName?: string;        // 呼び出し元エージェント
}
```

### VoiceOutputResponse

```typescript
interface VoiceOutputResponse {
  success: boolean;
  audioData?: ArrayBuffer;   // 音声データ
  cleanText?: string;        // 感情タグ除去後のテキスト
  emotion?: string;          // 検出された感情
  error?: string;
}
```

## LangGraph移行後の設計

### STTノード

```python
def stt_node(state: WorkflowState) -> dict:
    """音声認識ノード"""
    audio_base64 = state["audio_data"]
    language = state["language"]

    # Google Cloud STTで認識
    result = await speech_to_text(audio_base64, language)

    # STT補正
    corrected = stt_correction.correct(result.transcript)

    # 品質チェック
    quality = check_speech_quality(result)
    if not quality.is_valid:
        return {"needs_clarification": True, "reason": quality.reason}

    return {
        "transcript": corrected,
        "confidence": result.confidence
    }
```

### TTSノード

```python
def tts_node(state: WorkflowState) -> dict:
    """音声合成ノード"""
    text = state["response"]
    language = state["language"]

    # 感情タグ解析
    parsed = emotion_tag_parser.parse(text)

    # テキスト前処理
    clean_text = tts_preprocess(parsed.clean_text, language)

    # Google Cloud TTSで合成
    audio_data = await text_to_speech(clean_text, language, parsed.emotion)

    return {
        "audio_data": audio_data,
        "emotion": parsed.emotion
    }
```

## パフォーマンス目標

| 処理 | 目標時間 |
|-----|---------|
| STT（認識） | 500ms以下 |
| STT補正 | 10ms以下 |
| TTS（合成） | 1秒以下 |
| 感情タグ解析 | 10ms以下 |

## モバイル対応

### 既知の制限

- **iOS Safari**: マイク権限の取得タイミングに注意
- **Android**: 一部ブラウザで音声再生にユーザー操作が必要

### 対応策

- MobileAudioService: 自動再生ポリシーへの対応
- AudioInteractionManager: ユーザー操作待ち処理

## テストケース概要

| カテゴリ | テストケース例 |
|---------|--------------|
| STT正常 | 明瞭な音声 → 正確なテキスト |
| STT補正 | 「エンジンカフェ」→「エンジニアカフェ」 |
| STT低品質 | ノイズ多い音声 → 聞き直し応答 |
| TTS正常 | 感情タグ付きテキスト → 音声出力 |
| TTS長文 | 5000バイト超え → 適切に切り詰め |

## 担当者向けチェックリスト

- [ ] Mastra版の実装を理解した
- [ ] Google Cloud Speech APIの使用方法を把握した
- [ ] STT補正パターンを確認した
- [ ] TTS前処理のロジックを理解した
- [ ] 感情タグ解析を理解した
- [ ] モバイル制限と対策を確認した
- [ ] テストケースを確認した

## 関連ドキュメント

- [Character Control Agent](../character-control-agent/README.md) - キャラクター制御
- [STT Correction](../../lib/stt-correction.md) - STT補正
- [Emotion Tag Parser](../../lib/emotion-tag-parser.md) - 感情タグ解析
- [Mobile Audio Service](../../lib/mobile-audio-service.md) - モバイル音声
