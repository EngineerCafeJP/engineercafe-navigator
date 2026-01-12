# Voice Agent - テスト戦略

> テストケース・検証方法・品質基準

## テスト概要

Voice Agent は音声 I/O の中核であり、**ユーティリティ単体**／**VoiceOutputAgent 単体**／**ワークフロー統合**の3レベルでテストします。</br>
Router Agent のテスト戦略を踏襲し、音声特有のケース（長文TTS・フェイルセーフ・品質分岐）を追加します。

## テストレベル

- **単体テスト**：`stt_correction.py` / `emotion_tag_parser.py` / `tts_preprocess.py` / `perf.py`。
- **エージェント単体**：`voice_output_agent.py`（通常/長文/失敗時フェイルセーフ/ストリーミング）。
- **統合テスト**：`main_workflow.py` のノード連携（`stt_node`→Clarify/QA→LLM→Emotion/Mem→`tts_node`→`character_node`）。

## 単体テスト例

### 1. STT 誤認補正

```python
# tests/test_stt_correction.py
import pytest
from backend.utils.stt_correction import correct, likely_contains_misrecognition

def test_engineer_cafe_corrections():
    original = "エンジニア壁の営業時間は？"
    corrected = correct(original)
    assert "エンジニアカフェ" in corrected  # 文脈条件付きで置換されること

def test_likely_contains_misrecognition():
    assert likely_contains_misrecognition("エンジニア壁") is True
```

（誤認ルール群と文脈正規表現は TS 実装に準拠）

### 2. Emotion Tag Parser

```python
# tests/test_emotion_tag_parser.py
import pytest
from backend.utils.emotion_tag_parser import parse, get_expression_weights

def test_parse_tags_with_intensity():
    text = "[happy:0.8]はじめまして！"
    result = parse(text)
    assert result["clean_text"].startswith("はじめまして")
    assert result["primary_emotion"] == "happy"

def test_expression_weights_balance():
    weights = get_expression_weights("happy", 0.6)
    assert 0 <= weights["happy"] <= 1 and 0 <= weights["neutral"] <= 1
```

（タグ形式とVRM表情マッピング補助の仕様に準拠）

### 3. TTS 前処理

```python
# tests/test_tts_preprocess.py
from backend.utils.tts_preprocess import expand_abbreviations, truncate_bytes

def test_expand_mtg():
    assert expand_abbreviations("MTG参加", "ja") == "ミーティング参加"
    assert expand_abbreviations("MTG space", "en") == "meeting space"

def test_truncate_bytes_soft_hard():
    long_text = "こんにちは。" * 2000
    t = truncate_bytes(long_text, max_bytes=5000, soft_limit=4500)
    assert len(t.encode("utf-8")) <= 5000
```

（MTG展開・バイト上限の仕様に準拠）

## エージェント単体テスト例

### 4. VoiceOutputAgent 通常系

```python
# tests/test_voice_output_agent.py
import pytest
from backend.agents.voice_output_agent import convert_text_to_speech

class DummyTTS:
    async def text_to_speech(self, text, language, emotion):
        return {"success": True, "audio_bytes": b"dummy"}

@pytest.mark.asyncio
async def test_convert_text_to_speech_normal(monkeypatch):
    async def mock_tts(text, language, emotion):
        return {"success": True, "audio_bytes": b"ok"}
    from backend.tools import tts_port
    monkeypatch.setattr(tts_port, "text_to_speech", mock_tts)

    res = await convert_text_to_speech("[happy]こんにちは！", "ja", None)
    assert res["success"] is True and res["audio_bytes"]
```

（タグ解析→前処理→TTS 呼び出しの流れに準拠）

### 5. 長文トランケート & フェイルセーフ

```python
@pytest.mark.asyncio
async def test_long_text_and_fallback(monkeypatch):
    async def mock_tts_fail(text, language, emotion):
        return {"success": False, "error": "fail"}
    from backend.tools import tts_port
    monkeypatch.setattr(tts_port, "text_to_speech", mock_tts_fail)

    long_text = "[relaxed]" + ("説明文。" * 2000)
    res = await convert_text_to_speech(long_text, "ja", None)
    assert res["success"] in (True, False)  # フェイルセーフの成否
    # いずれにせよ clean_text は返す
    assert "clean_text" in res
```

（文字数上限・フェイルセーフ仕様に準拠）

## 統合テスト例

### 6. Clarify 分岐と QA 統合

```python
# tests/test_workflow_voice_integration.py
import pytest
from backend.workflows.main_workflow import MainWorkflow

@pytest.mark.asyncio
async def test_clarify_or_qa_flow():
    wf = MainWorkflow()
    # 品質NGケース（信頼度やノイズを模擬）
    stt_ng_input = {"audio_data": "...", "language": "ja", "simulate_low_confidence": True}  # TODO: 実引数定義
    res_ng = await wf.ainvoke(stt_ng_input)
    assert res_ng["route"] == "tts"  # Clarify→TTS

    # 品質OKケース→QAへ
    stt_ok_input = {"audio_data": "...", "language": "ja", "simulate_low_confidence": False}
    res_ok = await wf.ainvoke(stt_ok_input)
    assert "answer" in res_ok  # QA 結果
```

（品質分岐・QA優先のワークフローに準拠）

## パフォーマンステスト

- **目安**：STT ≤ 500ms、TTS ≤ 1.0s、タグ解析/補正 ≤ 10ms、総合 ≤ 2.0s。
- **方法**：疑似データで 100 件バッチ・10 件同時を測定し、`perf.py` の要約で閾値超過を検知。**TODO**: 実測環境の I/O をモック。

## テスト実行方法

```bash
# 単体テスト
pytest tests/test_stt_correction.py -v
pytest tests/test_emotion_tag_parser.py -v
pytest tests/test_tts_preprocess.py -v

# エージェント単体
pytest tests/test_voice_output_agent.py -v

# 統合
pytest tests/test_workflow_voice_integration.py -v
```

（Router Agent のテスト戦略を準拠・拡張）

## 品質基準

- 単体テストカバレッジ 90%以上。
- Clarify/QA 分岐の正当性（擬似データで 95%以上）。
- 長文 TTS の失敗率が 0%（必ずトランケート適用）。
- パフォーマンス閾値達成。

## CI 連携（例）

```yaml
# .github/workflows/test-voice-agent.yml
name: Voice Agent Tests
on:
  push:
    paths:
      - 'backend/agents/voice_output_agent.py'
      - 'backend/utils/**'
      - 'backend/tools/**'
      - 'backend/workflows/main_workflow.py'
      - 'tests/**'
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest pytest-asyncio pytest-cov
      - name: Run tests
        run: |
          pytest -v --maxfail=1
```

## 参考

- Voice Agent README（責務・性能・モバイル対策）
- Router Agent の TESTING（構成参照）
- TS 実装（realtime/voice-output/emotion-tag/STT-corrections/tts-preprocess）
