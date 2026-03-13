## TESTING.md（テスト仕様書）

### 1. テスト方針

OCR Agent は UX とルーティング精度に直結するため、以下を重点的に検証する。

- 認識精度
- 安定性
- 処理性能
- プライバシー遵守

### 2. テストレベル

| レベル | 対象 | 目的 |
|----|----|----|
| 単体テスト | OCR / 表情認識 | 認識精度検証 |
| 統合テスト | Router Agent | ワークフロー確認 |
| 回帰テスト | 既存パターン | 精度劣化防止 |
| 非機能テスト | 性能 | 実運用耐性 |

### 3. 単体テストケース

#### 番号認識
- 「1」「2」を正しく認識
- confidence >= 0.8
```
# tests/test_ocr_agent_number.py

import pytest
from backend.agents.ocr_agent import OCRAgent

class TestNumberRecognition:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    @pytest.mark.parametrize("image_path,expected_text", [
        ("tests/assets/number_1.png", "1"),
        ("tests/assets/number_2.png", "2"),
        ("tests/assets/number_123.png", "123"),
    ])
    async def test_number_recognition(self, ocr_agent, image_path, expected_text):
        result = await ocr_agent.recognize(
            image_path=image_path,
            recognition_type="number"
        )

        assert result["detected"] is True
        assert result["ocr_result"]["text"] == expected_text
        assert result["ocr_result"]["confidence"] >= 0.8
```
#### テキストOCR
- 日本語・英語テキストを抽出
- 空文字を返さない
```
# tests/test_ocr_agent_text.py

import pytest
from backend.agents.ocr_agent import OCRAgent

class TestTextOCR:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    @pytest.mark.parametrize("image_path,language", [
        ("tests/assets/japanese_text.png", "ja"),
        ("tests/assets/english_text.png", "en"),
    ])
    async def test_text_ocr(self, ocr_agent, image_path, language):
        result = await ocr_agent.recognize(
            image_path=image_path,
            recognition_type="text"
        )

        assert result["detected"] is True
        assert result["ocr_result"]["text"] != ""
        assert result["language"] == language
        assert result["confidence"] >= 0.7
```
#### QRコード
- QRコードから情報を取得可能
```
# tests/test_ocr_agent_qr.py

import pytest
from backend.agents.ocr_agent import OCRAgent

class TestQRCodeRecognition:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    async def test_qr_code_recognition(self, ocr_agent):
        result = await ocr_agent.recognize(
            image_path="tests/assets/sample_qr.png",
            recognition_type="qr"
        )

        assert result["detected"] is True
        assert result["ocr_result"]["text"].startswith("http")
        assert result["confidence"] >= 0.8
```

#### 表情認識
- happy / confused / neutral を検出
- confidence >= 0.7
```
# tests/test_face_expression.py

import pytest
from backend.agents.ocr_agent import OCRAgent

class TestFaceExpression:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    @pytest.mark.parametrize("image_path,expected_emotion", [
        ("tests/assets/face_happy.png", "happy"),
        ("tests/assets/face_confused.png", "confused"),
        ("tests/assets/face_neutral.png", "neutral"),
    ])
    async def test_expression_detection(self, ocr_agent, image_path, expected_emotion):
        result = await ocr_agent.recognize(
            image_path=image_path,
            recognition_type="face_expression"
        )

        assert result["detected"] is True
        assert result["face_expression"]["emotion"] == expected_emotion
        assert result["face_expression"]["confidence"] >= 0.7
```
#### 顔未検出
- detected=false を返却
```
# tests/test_face_not_detected.py

import pytest
from backend.agents.ocr_agent import OCRAgent

class TestNoFaceDetected:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    async def test_no_face_detected(self, ocr_agent):
        result = await ocr_agent.recognize(
            image_path="tests/assets/no_face.png",
            recognition_type="face_expression"
        )

        assert result["detected"] is False
        assert result["face_expression"] is None
```
### 4. 統合テスト

- OCR結果に基づき Router Agent が適切に分岐する
- 番号入力 → BusinessInfoAgent へのルーティング成功
```
# tests/test_ocr_router_integration.py

import pytest
from backend.workflows.main_workflow import MainWorkflow

class TestOCRRouterIntegration:

    @pytest.fixture
    def workflow(self):
        return MainWorkflow()

    async def test_number_to_business_info(self, workflow):
        result = await workflow.ainvoke({
            "image_path": "tests/assets/number_1.png",
            "ocr_type": "number",
            "session_id": "test_session"
        })

        assert result["metadata"]["routing"]["agent"] == "BusinessInfoAgent"
```
### 5. パフォーマンス基準
```
# tests/test_ocr_performance.py

import time
import pytest
from backend.agents.ocr_agent import OCRAgent

class TestOCRPerformance:

    @pytest.fixture
    def ocr_agent(self):
        return OCRAgent()

    async def test_ocr_response_time(self, ocr_agent):
        start = time.perf_counter()

        await ocr_agent.recognize(
            image_path="tests/assets/number_1.png",
            recognition_type="number"
        )

        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 800
```
| 項目 | 基準 |
|----|----|
| 平均処理時間 | 500ms 以下 |
| 最大処理時間 | 800ms 以下 |

### 6. 品質基準

| 項目 | 基準 |
|----|----|
| 番号認識精度 | 98% 以上 |
| 日本語OCR精度 | 90% 以上 |
| 英語OCR精度 | 95% 以上 |
| 表情認識精度 | 85% 以上 |
| 画像保存 | 一切行わない |
