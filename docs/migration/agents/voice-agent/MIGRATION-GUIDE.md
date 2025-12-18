# Voice Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

Mastra（TypeScript）で実装された 
<br>音声入出力＋会話オーケストレーション（STT→品質判定→聞き返し→QA/RAG→LLM→感情→メモリ→TTS→キャラ制御）を、
<br>Python/LangGraph のノード群へ段階的に移行する。テンプレートは Router Agent の移行ガイドを参照。

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
engineer-cafe-navigator-repo/src/
├── mastra/agents/
│   ├── realtime-agent.ts        # リアルタイム音声処理かつVoice Agentメイン部分　1674行
│   └── voice-output-agent.ts    # TTS処理（前処理・長文制限・フェイルセーフ）　228行
├── lib/
│   ├── stt-correction.ts        # STT誤認識補正（正則化＋置換）　281行
│   └── emotion-tag-parser.ts    # 感情タグ解析・付与（タグ抽出・クリーン化）　203行
└── utils/
    ├── emotion-manager.ts       # 感情推定・VRM表情マッピング　399行
    ├── performance-monitor.ts   # 処理時間計測ユーティリティ　44行
    └── tts-preprocess.ts        # TTS前処理（略語「MTG」→「ミーティング/meeting」など）、4行
```
- ealtime-agent.ts は STT→品質判定→聞き返し→QA/RAG→LLM→感情→メモリ→TTS→キャラ制御までのオーケストレーションを持つ。
<br>TTSは VoiceOutputAgent を優先、失敗時に voiceService にフォールバック。ストリーミングTTSとリップシンク連携も内包。 
- voice-output-agent.ts は 感情タグのパース→TTS前処理→5000bytes制限対応→音声生成（ArrayBuffer）を提供し、
<br>失敗時は 謝罪文のTTS にフェイルセーフする。
- stt-correction.ts は 工程固有の誤認識補正（エンジニアカフェ／サイノウカフェ／Wi‑Fi など）を正規表現で実装。
- emotion-tag-parser.ts は タグ抽出・クリーンテキスト生成・主感情決定を担う。
- emotion-manager.ts は キーワード分析による感情推定と VRM表情マッピングを提供。
- performance-monitor.ts は 処理時間の開始・終了・要約ログを提供。
- tts-preprocess.ts は TTS用の簡易前処理（例：MTG→ミーティング/meeting）。

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   ├── voice_output_agent.py        # 新規　VoiceOutputAgent相当（TTS前処理・長文制約・フェイルセーフ）
│   └── voice_orchestrator.py        # 新規　司令塔（必要なら作成、もしくはworkflowsへ直実装）
├── utils/
│   ├── stt_correction.py            # 移管　STT補正
│   ├── emotion_tag_parser.py        # 移管　感情タグ解析
│   ├── emotion_manager.py           # 移管　感情推定／VRMマッピング
│   ├── tts_preprocess.py            # 移管　TTS前処理
│   └── perf.py                      # 移管　計測ユーティリティ
├── services/
│   ├── stt_port.py                  # 新規　STTサービスポート（speech_to_text）
│   ├── tts_port.py                  # 新規　TTSサービスポート（text_to_speech）
│   ├── qa_service.py                # 新規　QA/RAG呼び出しアダプタ
│   ├── memory_facade.py             # 新規　Shared/Simplified/Supabaseの統合
│   └── character_control.py         # 新規　キャラクター制御アダプタ
└── workflows/
    └── main_workflow.py             # 移管、一部修正　LangGraphワークフロー（ノード追加・統合）
```

## 移行ステップ

### Step 1: 依存モジュールの移行

#### STT Correction の移行

**元**： `src/lib/stt-correction.ts` → **先**： `backend/utils/stt_correction.py`

- 正規表現パターン／前後処理（空白正規化・句読点補正）を Python に移植。

```python

# backend/utils/stt_correction.py（骨子）
import re

def correct(text: str) -> str:
    if not text: return text
    corrected = text
    # 代表例：エンジニアカフェ／サイノカフェ／Wi-Fi
    corrected = re.sub(r"engineer\s*(cafe|coffee|wall)", "エンジニアカフェ", corrected, flags=re.I)
    corrected = re.sub(r"(wife\s*i|why\s*fi|y\s*fi)", "Wi-Fi", corrected, flags=re.I)
    # ...（全文はTSのパターン群を移植）
       corrected = re.sub(r"\s+", " ", corrected).strip()
```

#### 1.2 Emotion Tag Parser の移行

**元**： `src/lib/emotion-tag-parser.ts` → **先**： `backend/utils/emotion_tag_parser.py`

- タグ抽出・クリーン化・主感情決定のロジックを Python 化。


#### 1.3 Emotion Manager の移行

**元**： `src/utils/emotion-manager.ts` → **先**： `backend/utils/emotion_manager.py`

- キーワードスコアリングでの推定、VRM表情マッピング、遷移イージングの基本方針を Python へ。


#### 1.4 TTS Preprocess の移行

**元**： `src/utils/tts-preprocess.ts` → **先**： `backend/utils/tts_preprocess.py`

- MTG→ミーティング等の前処理を Python に移植。


#### 1.5 Performance Monitor の移行

**元**： `src/utils/performance-monitor.ts` → **先**： `backend/utils/perf.py`

- 計測開始/終了/要約のインターフェースを Python で提供。


### Step 2: VoiceOutputAgent 本体の移行

**元ファイル**: `src/mastra/agents/voice-output-agent.ts`
**先ファイル**: `backend/agents/voice_output_agent.py`

- 役割：感情タグ入りテキストを TTS向けに整形（タグ除去→前処理→長文5000bytes制約）し、
<br>音声生成（bytes）を返す。失敗時は 謝罪メッセージのTTS でフェイルセーフ。
- TS実装の タグ処理／前処理／長文制約／フェイルセーフ を反映。

```python
# backend/agents/voice_output_agent.py（骨子）
from backend.utils.emotion_tag_parser import parse
from backend.utils.tts_preprocess import clean, truncate_bytes
from backend.services.tts_port import text_to_speech

async def convert_text_to_speech(text: str, language: str, emotion_hint: str | None = None) -> dict:
    parsed = parse(text)  # clean_text, primary_emotion, emotions
    tts_text = clean(parsed.clean_text, language)
    tts_text = truncate_bytes(tts_text, max_bytes=5000)
    emotion = emotion_hint or (parsed.primary_emotion or "neutral")
    res = await text_to_speech(tts_text, language, emotion)
    if not res["success"]:
        fb = await text_to_speech(
            "申し訳ございません。音声の生成に失敗しました。" if language=="ja" else
            "I apologize, but I failed to generate the audio response.", language, "apologetic"
        )
        return {"success": fb.get("success", False), "audio_bytes": fb.get("audio_bytes", b""), "emotion": "sad"}
```

### Step 3: RealtimeAgent 音声パイプラインの分割移行

**元ファイル**: `src/mastra/agents/realtime-agent.ts`

- 現状は 1 クラスで STT→品質判定→聞き返し→QA/RAG→LLM→感情→メモリ→TTS→キャラ制御まで実装。
<br>LangGraph では ノード分割してワークフロー化。

ノード構成（例）：
- stt_node：ArrayBuffer/Base64→STT→stt_correction.correct→品質判定→言語候補検出。
- clarify_or_route_node：品質NGなら 聞き返し（感情タグ付与 [surprised] 等）を生成。品質OKなら Router/QAへ。
- qa_node：QA/RAG優先で回答取得（空なら llm_fallback_nodeへ）。
- llm_fallback_node：LLM応答＋emotion_tag_parserでタグ付与。
- emotion_and_memory_node：emotion_managerで会話文脈に基づく感情推定→ Shared/Simplified/Supabase 保存→ 言語切替確定（0.98）。
- tts_node：voice_output_agent.convert_text_to_speech を呼び出し、失敗時フェイルセーフ。 
- character_node：音声・感情に基づく 表情／リップシンクの生成。

### Step 4: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python

# 既存 main_workflow.py を拡張（骨子）
def _build_graph(self) -> StateGraph:
    g = StateGraph(WorkflowState)
    g.add_node("stt", stt_node)
    g.add_node("clarify_or_route", clarify_or_route_node)
    g.add_node("qa", qa_node)
    g.add_node("llm_fallback", llm_fallback_node)
    g.add_node("emotion_and_memory", emotion_and_memory_node)
    g.add_node("tts", tts_node)
    g.add_node("character", character_node)
    g.add_node("format_response", self._format_response_node)  # 既存

    g.add_edge(START, "stt")
    g.add_edge("stt", "clarify_or_route")
    g.add_conditional_edges(
        "clarify_or_route",
        lambda s: "tts" if s["stt_quality"] and not s["stt_quality"]["is_valid"] else "qa",
        {"tts": "tts", "qa": "qa"}
    )
    g.add_edge("qa", "llm_fallback")
    g.add_conditional_edges(
        "llm_fallback",
        lambda s: "emotion_and_memory" if not s.get("answer") else "emotion_and_memory",
        {"emotion_and_memory": "emotion_and_memory"}
    )
    g.add_edge("emotion_and_memory", "tts")
    g.add_edge("tts", "character")
    g.add_edge("character", "format_response")
       g.add_edge("format_response", END)
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] realtime-agent.ts／voice-output-agent.ts のフローを把握（STT〜TTS、フェイルセーフ、ストリーミング）。
- [ ] Python/LangGraph 依存の用意（langgraph, langchain ほか）。
- [ ] テスト環境の用意／音声I/Oのダミーデータ整備。

### Phase 2: 依存モジュール

- [ ] `stt_correction.py` を作成した
- [ ] `emotion_tag_parser.py` を作成した
- [ ] `emotion_manager.py` を作成した
- [ ] `tts_preprocess.py` を作成した
- [ ] `perf.py` を作成した
- [ ] 単体テスト（補正・タグ解析・推定・前処理・計測）が通過。

### Phase 3: VoiceOutputAgent 本体

- [ ] `voice_output_agent.py` を作成した（タグ処理→前処理→長文制約→TTS→フェイルセーフ）。
- [ ] 単体テスト（通常／失敗時／長文）。

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にstt_node／clarify_or_route_node／qa_node／llm_fallback_node／emotion_and_memory_node／tts_node／character_node の追加。
- [ ] 条件付きエッジの設定（品質NG→TTS、品質OK→QAなど）。
- [ ] エンドツーエンドテスト（音声入力→音声出力）。

### Phase 5: 検証

- [ ] 各種テストケース（補正／聞き返し／QA→LLM／長文TTS／キャラ制御）。
- [ ] パフォーマンス計測（STT ≤ 500ms、TTS ≤ 1.0s、タグ解析/補正 ≤ 10ms、総合 ≤ 2.0sの目安）。
- [ ] ログ確認・運用フラグ（フォールバック）整備。

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| STTの文字化け／空文字 |Base64 変換不備・サンプリングレート不一致 | 変換部を見直し、audio_base64 に正しく格納。STTポートの仕様に合わせる（speech_to_text）。 |
| 品質NGが過剰に発生 | 閾値／正規化不足 | stt_correction の適用順序を早め、checkSpeechQuality 相当のしきい値（confidence）を調整。 |
| TTSが5000bytes超過で失敗 | 長文制約未対応 | voice_output_agent の truncate_bytes を必ず適用し、文末に省略文言を付加。 |
| 感情タグが反映されない | タグの正規表現差異 | emotion_tag_parser のパターンを TS と同等に移植、未タグ時は EmotionTagger 相当の付与。 |
| キャラクターが音声と同期しない | リップシンク生成漏れ | character_node で audio_bytes を必ず渡し、VRM マッピングの重み計算を適正化 |
| 計測ログが散在 | 計測の責務が曖昧 | perf.py を各ノードから呼び、処理時間と合計を要約出力。 |

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)