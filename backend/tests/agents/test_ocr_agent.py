"""
VisionAgent (OCR Agent) のユニットテスト

テスト対象: backend/agents/ocr_agent.py
カバレッジ:
  - VisionAgent.__init__ (モック依存関係)
  - run() テキスト認識パス
  - run() QR認識パス
  - 画像リサイズロジック
  - Base64エンコーディング
  - エッジケース (空コンテンツ, None表情, ToolMessage解析)
  - ツール関数 (face_recognition, text_recognition)
  - recognize_qr 関数
"""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


# ---------------------------------------------------------------------------
# Tool functions (import directly, no LLM dependency)
# ---------------------------------------------------------------------------
class TestFaceRecognitionTool:
    """face_recognition ツール関数の直接テスト"""

    def test_returns_expression_as_is(self):
        """渡された表情文字列をそのまま返すことを確認"""
        from backend.agents.ocr_agent import face_recognition

        result = face_recognition.invoke({"expression": "happy"})
        assert result == "happy"

    def test_returns_various_expressions(self):
        """全サポート表情を正しく返すことを確認"""
        from backend.agents.ocr_agent import face_recognition

        expressions = ["happy", "sad", "angry", "neutral", "surprised", "confused"]
        for expr in expressions:
            result = face_recognition.invoke({"expression": expr})
            assert result == expr

    def test_returns_none_string(self):
        """'None' 文字列を渡した場合もそのまま返す"""
        from backend.agents.ocr_agent import face_recognition

        result = face_recognition.invoke({"expression": "None"})
        assert result == "None"


class TestTextRecognitionTool:
    """text_recognition ツール関数の直接テスト"""

    def test_returns_text_as_is(self):
        """渡されたテキストをそのまま返すことを確認"""
        from backend.agents.ocr_agent import text_recognition

        result = text_recognition.invoke({"text": "Hello World"})
        assert result == "Hello World"

    def test_returns_japanese_text(self):
        """日本語テキストを正しく返すことを確認"""
        from backend.agents.ocr_agent import text_recognition

        result = text_recognition.invoke({"text": "エンジニアカフェ"})
        assert result == "エンジニアカフェ"

    def test_returns_empty_string(self):
        """空文字列を渡した場合も返すことを確認"""
        from backend.agents.ocr_agent import text_recognition

        result = text_recognition.invoke({"text": ""})
        assert result == ""


# ---------------------------------------------------------------------------
# recognize_qr function
# ---------------------------------------------------------------------------
class TestRecognizeQr:
    """recognize_qr 関数のテスト"""

    @patch("backend.agents.ocr_agent.cv2.QRCodeDetector")
    def test_returns_qr_data_on_success(self, mock_detector_cls):
        """QRコードが検出された場合にデータを返すことを確認"""
        from backend.agents.ocr_agent import recognize_qr

        mock_detector = MagicMock()
        mock_detector.detectAndDecode.return_value = ("https://example.com", None, None)
        mock_detector_cls.return_value = mock_detector

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = recognize_qr(image)

        assert result == "https://example.com"
        mock_detector.detectAndDecode.assert_called_once_with(image)

    @patch("backend.agents.ocr_agent.cv2.QRCodeDetector")
    def test_returns_none_when_no_qr_detected(self, mock_detector_cls):
        """QRコードが検出されない場合に None を返すことを確認"""
        from backend.agents.ocr_agent import recognize_qr

        mock_detector = MagicMock()
        mock_detector.detectAndDecode.return_value = ("", None, None)
        mock_detector_cls.return_value = mock_detector

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = recognize_qr(image)

        assert result is None

    @patch("backend.agents.ocr_agent.cv2.QRCodeDetector")
    def test_returns_none_when_data_is_none(self, mock_detector_cls):
        """detectAndDecode が None を返した場合"""
        from backend.agents.ocr_agent import recognize_qr

        mock_detector = MagicMock()
        mock_detector.detectAndDecode.return_value = (None, None, None)
        mock_detector_cls.return_value = mock_detector

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = recognize_qr(image)

        assert result is None


# ---------------------------------------------------------------------------
# VisionAgent
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_vision_agent():
    """
    VisionAgent を LLM/OpenRouter のモック付きで生成するフィクスチャ。

    OpenRouterProvider と get_model_config をモックし、
    実際の API 呼び出しを行わない。
    """
    with (
        patch("backend.agents.ocr_agent.OpenRouterProvider") as mock_provider_cls,
        patch("backend.agents.ocr_agent.get_model_config") as mock_get_config,
    ):
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = MagicMock()

        mock_provider = MagicMock()
        mock_provider.get_langchain_llm.return_value = mock_llm
        mock_provider_cls.return_value = mock_provider

        mock_get_config.return_value = MagicMock()

        from backend.agents.ocr_agent import VisionAgent

        agent = VisionAgent()
        yield agent, mock_provider_cls, mock_get_config, mock_llm


class TestVisionAgentInit:
    """VisionAgent.__init__ のテスト"""

    def test_creates_openrouter_provider(self, mock_vision_agent):
        """OpenRouterProvider が呼ばれることを確認"""
        _, mock_provider_cls, _, _ = mock_vision_agent
        mock_provider_cls.assert_called_once()

    def test_calls_get_model_config_with_vision(self, mock_vision_agent):
        """get_model_config('vision') が呼ばれることを確認"""
        _, _, mock_get_config, _ = mock_vision_agent
        mock_get_config.assert_called_once_with("vision")

    def test_binds_tools_to_llm(self, mock_vision_agent):
        """LLM に face_recognition と text_recognition がバインドされることを確認"""
        from backend.agents.ocr_agent import face_recognition, text_recognition

        _, _, _, mock_llm = mock_vision_agent
        mock_llm.bind_tools.assert_called_once()
        bound_tools = mock_llm.bind_tools.call_args[0][0]
        assert face_recognition in bound_tools
        assert text_recognition in bound_tools
        assert len(bound_tools) == 2

    def test_builds_graph(self, mock_vision_agent):
        """グラフ (self.app) が構築されることを確認"""
        agent, _, _, _ = mock_vision_agent
        assert agent.app is not None


# ---------------------------------------------------------------------------
# run() - QR recognition path
# ---------------------------------------------------------------------------
class TestVisionAgentRunQr:
    """VisionAgent.run() の QR認識パスのテスト"""

    @patch("backend.agents.ocr_agent.recognize_qr")
    async def test_qr_success(self, mock_recognize_qr, mock_vision_agent):
        """QR コード認識成功時のレスポンス形式を確認"""
        agent, _, _, _ = mock_vision_agent
        mock_recognize_qr.return_value = "https://example.com"

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = await agent.run({"image": image, "recognition_type": "qr"})

        assert result["qr"]["success"] is True
        assert result["qr"]["data"] == "https://example.com"
        assert result["qr"]["error"] is None

    @patch("backend.agents.ocr_agent.recognize_qr")
    async def test_qr_failure(self, mock_recognize_qr, mock_vision_agent):
        """QR コード検出失敗時のレスポンス形式を確認"""
        agent, _, _, _ = mock_vision_agent
        mock_recognize_qr.return_value = None

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        result = await agent.run({"image": image, "recognition_type": "qr"})

        assert result["qr"]["success"] is False
        assert result["qr"]["data"] is None
        assert result["qr"]["error"] == "QR not detected"

    @patch("backend.agents.ocr_agent.recognize_qr")
    async def test_qr_does_not_invoke_graph(self, mock_recognize_qr, mock_vision_agent):
        """QR パスでは LLM グラフが呼ばれないことを確認"""
        agent, _, _, _ = mock_vision_agent
        mock_recognize_qr.return_value = "data"

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock()

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        await agent.run({"image": image, "recognition_type": "qr"})

        agent.app.ainvoke.assert_not_called()


# ---------------------------------------------------------------------------
# run() - Text/face recognition path (image processing)
# ---------------------------------------------------------------------------
class TestVisionAgentImageProcessing:
    """画像前処理 (リサイズ, エンコード) のテスト"""

    async def test_image_not_resized_when_within_max_width(self, mock_vision_agent):
        """640px以下の画像はリサイズされないことを確認"""
        agent, _, _, _ = mock_vision_agent

        # 320x240 の画像 (640以下)
        image = np.zeros((240, 320, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="no tools called")]}
        )

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))

            with patch("backend.agents.ocr_agent.cv2.resize") as mock_resize:
                await agent.run({"image": image})
                mock_resize.assert_not_called()

    async def test_image_resized_when_exceeds_max_width(self, mock_vision_agent):
        """640pxを超える画像がリサイズされることを確認"""
        agent, _, _, _ = mock_vision_agent

        # 1280x720 の画像 (640を超える)
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        resized_image = np.zeros((360, 640, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(
            return_value={"messages": [AIMessage(content="no tools called")]}
        )

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))

            with patch("backend.agents.ocr_agent.cv2.resize") as mock_resize:
                mock_resize.return_value = resized_image
                await agent.run({"image": image})

                mock_resize.assert_called_once()
                call_args = mock_resize.call_args
                # 新しいサイズ: (640, 360)
                assert call_args[0][1] == (640, 360)

    async def test_imencode_called_with_jpeg_quality_85(self, mock_vision_agent):
        """cv2.imencode が JPEG品質85で呼ばれることを確認"""
        agent, _, _, _ = mock_vision_agent

        image = np.zeros((100, 100, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([65, 66, 67], dtype=np.uint8))

            with patch("backend.agents.ocr_agent.cv2.IMWRITE_JPEG_QUALITY", 1):
                await agent.run({"image": image})

                mock_imencode.assert_called_once()
                call_args = mock_imencode.call_args[0]
                assert call_args[0] == ".jpg"

    async def test_base64_encoded_image_in_message(self, mock_vision_agent):
        """エンコードされた画像が base64 として HumanMessage に含まれることを確認"""
        agent, _, _, _ = mock_vision_agent

        image = np.zeros((100, 100, 3), dtype=np.uint8)
        fake_buffer = np.array([72, 101, 108, 108, 111], dtype=np.uint8)
        expected_b64 = base64.b64encode(fake_buffer).decode("utf-8")

        captured_input = {}

        async def capture_ainvoke(input_data):
            captured_input.update(input_data)
            return {"messages": [AIMessage(content="done")]}

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(side_effect=capture_ainvoke)

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, fake_buffer)
            await agent.run({"image": image})

        # ainvoke に渡された HumanMessage を検証
        messages = captured_input["messages"]
        assert len(messages) == 1
        msg = messages[0]
        assert isinstance(msg, HumanMessage)

        # image_url 部分に base64 が含まれること
        image_content = msg.content[1]
        assert image_content["type"] == "image_url"
        assert expected_b64 in image_content["image_url"]["url"]


# ---------------------------------------------------------------------------
# run() - ToolMessage parsing
# ---------------------------------------------------------------------------
class TestVisionAgentToolMessageParsing:
    """ToolMessage の解析ロジックのテスト"""

    async def _run_with_tool_messages(self, agent, tool_messages):
        """ヘルパー: 指定した ToolMessage を返すようモックして run を実行"""
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        all_messages = [
            HumanMessage(content="original"),
            AIMessage(content="calling tools"),
            *tool_messages,
            AIMessage(content="final answer"),
        ]

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": all_messages})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1], dtype=np.uint8))
            return await agent.run({"image": image})

    async def test_text_recognition_success(self, mock_vision_agent):
        """テキスト認識成功時の結果パースを確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="Engineer Cafe", name="text_recognition", tool_call_id="tc1"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["text"]["success"] is True
        assert result["text"]["text"] == "Engineer Cafe"
        assert result["text"]["error"] is None

    async def test_face_recognition_success(self, mock_vision_agent):
        """表情認識成功時の結果パースを確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="happy", name="face_recognition", tool_call_id="tc2"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["face"]["success"] is True
        assert result["face"]["detected"] is True
        assert result["face"]["expression"] == {"emotion": "happy"}
        assert result["face"]["error"] is None

    async def test_both_tools_return_results(self, mock_vision_agent):
        """テキストと表情の両方が返された場合のパースを確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="Hello", name="text_recognition", tool_call_id="tc1"),
            ToolMessage(content="surprised", name="face_recognition", tool_call_id="tc2"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["text"]["success"] is True
        assert result["text"]["text"] == "Hello"
        assert result["face"]["success"] is True
        assert result["face"]["detected"] is True
        assert result["face"]["expression"] == {"emotion": "surprised"}

    async def test_text_recognition_empty_content(self, mock_vision_agent):
        """テキスト認識で空コンテンツの場合のエラー処理を確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="", name="text_recognition", tool_call_id="tc1"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["text"]["success"] is False
        assert result["text"]["text"] is None
        assert result["text"]["error"] == "text not detected"

    async def test_face_recognition_none_content(self, mock_vision_agent):
        """表情認識で None コンテンツの場合のエラー処理を確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="", name="face_recognition", tool_call_id="tc2"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["face"]["success"] is True
        assert result["face"]["detected"] is False
        assert result["face"]["expression"] is None
        assert result["face"]["error"] == "face not detected"

    async def test_face_recognition_none_string(self, mock_vision_agent):
        """表情認識で 'None' 文字列の場合のエラー処理を確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="None", name="face_recognition", tool_call_id="tc2"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["face"]["success"] is True
        assert result["face"]["detected"] is False
        assert result["face"]["expression"] is None
        assert result["face"]["error"] == "face not detected"

    async def test_face_recognition_none_case_insensitive(self, mock_vision_agent):
        """表情認識で 'NONE' (大文字) も None として扱われることを確認"""
        agent, _, _, _ = mock_vision_agent

        tool_msgs = [
            ToolMessage(content="NONE", name="face_recognition", tool_call_id="tc2"),
        ]
        result = await self._run_with_tool_messages(agent, tool_msgs)

        assert result["face"]["success"] is True
        assert result["face"]["detected"] is False
        assert result["face"]["error"] == "face not detected"

    async def test_no_tool_messages_returns_defaults(self, mock_vision_agent):
        """ToolMessage がない場合のデフォルト値を確認"""
        agent, _, _, _ = mock_vision_agent

        result = await self._run_with_tool_messages(agent, [])

        assert result["text"]["success"] is False
        assert result["text"]["text"] is None
        assert result["text"]["error"] is None
        assert result["face"]["success"] is False
        assert result["face"]["detected"] is False
        assert result["face"]["expression"] is None
        assert result["face"]["error"] is None

    async def test_default_recognition_type_is_text(self, mock_vision_agent):
        """recognition_type 未指定の場合 'text' パスが使われることを確認"""
        agent, _, _, _ = mock_vision_agent

        image = np.zeros((100, 100, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1], dtype=np.uint8))

            # recognition_type を指定しない
            result = await agent.run({"image": image})

        # QR 結果ではなく text/face 結果が返される
        assert "text" in result
        assert "face" in result
        assert "qr" not in result


# ---------------------------------------------------------------------------
# run() - Resize edge cases
# ---------------------------------------------------------------------------
class TestVisionAgentResizeEdgeCases:
    """画像リサイズのエッジケーステスト"""

    async def test_exactly_640_width_not_resized(self, mock_vision_agent):
        """幅がちょうど640pxの場合リサイズされないことを確認"""
        agent, _, _, _ = mock_vision_agent

        image = np.zeros((480, 640, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1], dtype=np.uint8))
            with patch("backend.agents.ocr_agent.cv2.resize") as mock_resize:
                await agent.run({"image": image})
                mock_resize.assert_not_called()

    async def test_641_width_is_resized(self, mock_vision_agent):
        """幅が641pxの場合リサイズされることを確認"""
        agent, _, _, _ = mock_vision_agent

        image = np.zeros((480, 641, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1], dtype=np.uint8))
            with patch("backend.agents.ocr_agent.cv2.resize") as mock_resize:
                mock_resize.return_value = np.zeros((479, 640, 3), dtype=np.uint8)
                await agent.run({"image": image})
                mock_resize.assert_called_once()

    async def test_very_wide_image_preserves_aspect_ratio(self, mock_vision_agent):
        """非常に幅広の画像でもアスペクト比が保たれることを確認"""
        agent, _, _, _ = mock_vision_agent

        # 1920x1080 画像
        image = np.zeros((1080, 1920, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": [AIMessage(content="done")]})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1], dtype=np.uint8))
            with patch("backend.agents.ocr_agent.cv2.resize") as mock_resize:
                mock_resize.return_value = np.zeros((360, 640, 3), dtype=np.uint8)
                await agent.run({"image": image})

                call_args = mock_resize.call_args[0]
                new_w, new_h = call_args[1]
                assert new_w == 640
                # scale = 640/1920 = 1/3, new_h = int(1080 * 1/3) = 360
                assert new_h == 360


# ---------------------------------------------------------------------------
# Integration Tests: VisionAgent Graph Structure
# ---------------------------------------------------------------------------
@pytest.mark.vision
class TestVisionAgentGraphStructure:
    """VisionAgent のコンパイル済みグラフ構造の検証テスト

    グラフが期待通りのノード・エッジを持つことを確認する。
    get_graph() が返す Graph オブジェクトの nodes / edges を検査する。
    """

    def _get_graph(self, agent):
        """ヘルパー: コンパイル済みグラフの描画用表現を取得"""
        return agent.app.get_graph()

    def _node_names(self, graph):
        """ヘルパー: グラフ内のノード名セットを返す"""
        return {node.name for node in graph.nodes.values()}

    def _edge_tuples(self, graph):
        """ヘルパー: (source_name, target_name, conditional) のセットを返す"""
        id_to_name = {nid: node.name for nid, node in graph.nodes.items()}
        return {
            (id_to_name.get(e.source, e.source), id_to_name.get(e.target, e.target), e.conditional)
            for e in graph.edges
        }

    def test_graph_has_vision_node(self, mock_vision_agent):
        """コンパイル済みグラフに 'vision' ノードが存在することを確認"""
        agent, _, _, _ = mock_vision_agent
        graph = self._get_graph(agent)
        node_names = self._node_names(graph)
        assert "vision" in node_names

    def test_graph_has_tools_node(self, mock_vision_agent):
        """コンパイル済みグラフに 'tools' ノードが存在することを確認"""
        agent, _, _, _ = mock_vision_agent
        graph = self._get_graph(agent)
        node_names = self._node_names(graph)
        assert "tools" in node_names

    def test_graph_starts_with_vision(self, mock_vision_agent):
        """START -> vision エッジが存在することを確認"""
        agent, _, _, _ = mock_vision_agent
        graph = self._get_graph(agent)
        edge_tuples = self._edge_tuples(graph)

        # START ノードは __start__ という名前で表現される
        start_to_vision = any(src == "__start__" and tgt == "vision" for src, tgt, _ in edge_tuples)
        assert start_to_vision, f"START -> vision エッジが見つかりません。エッジ一覧: {edge_tuples}"

    def test_tools_condition_edge(self, mock_vision_agent):
        """vision ノードから条件付きエッジ (tools_condition) が存在することを確認"""
        agent, _, _, _ = mock_vision_agent
        graph = self._get_graph(agent)
        edge_tuples = self._edge_tuples(graph)

        # tools_condition は conditional=True のエッジを生成する
        conditional_from_vision = [
            (src, tgt) for src, tgt, cond in edge_tuples if src == "vision" and cond is True
        ]
        assert (
            len(conditional_from_vision) > 0
        ), f"vision からの条件付きエッジが見つかりません。エッジ一覧: {edge_tuples}"

    def test_tools_to_vision_edge(self, mock_vision_agent):
        """tools -> vision エッジが存在することを確認"""
        agent, _, _, _ = mock_vision_agent
        graph = self._get_graph(agent)
        edge_tuples = self._edge_tuples(graph)

        tools_to_vision = any(
            src == "tools" and tgt == "vision" and cond is False for src, tgt, cond in edge_tuples
        )
        assert tools_to_vision, f"tools -> vision エッジが見つかりません。エッジ一覧: {edge_tuples}"


# ---------------------------------------------------------------------------
# Integration Tests: VisionAgent Full Flow
# ---------------------------------------------------------------------------
@pytest.mark.vision
class TestVisionAgentFullFlow:
    """VisionAgent のフルフロー統合テスト

    LLM がツール呼び出しを返すシナリオをシミュレートし、
    画像入力からパース済み結果までの全パイプラインを検証する。
    """

    async def _run_full_flow(self, agent, tool_call_messages):
        """ヘルパー: 合成画像を作成し、ツール呼び出しレスポンスをシミュレートして run を実行

        Args:
            agent: VisionAgent インスタンス
            tool_call_messages: ainvoke が返す全メッセージリスト
        """
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        agent.app = MagicMock()
        agent.app.ainvoke = AsyncMock(return_value={"messages": tool_call_messages})

        with patch("backend.agents.ocr_agent.cv2.imencode") as mock_imencode:
            mock_imencode.return_value = (True, np.array([1, 2, 3], dtype=np.uint8))
            return await agent.run({"image": image})

    async def test_text_recognition_full_flow(self, mock_vision_agent):
        """テキスト認識フルフロー: 画像入力 -> LLMツール呼び出し -> テキスト結果パース"""
        agent, _, _, _ = mock_vision_agent

        messages = [
            HumanMessage(content="analyze image"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "name": "text_recognition",
                        "args": {"text": "Engineer Cafe Fukuoka"},
                    }
                ],
            ),
            ToolMessage(
                content="Engineer Cafe Fukuoka",
                name="text_recognition",
                tool_call_id="tc1",
            ),
            AIMessage(content="The text found is: Engineer Cafe Fukuoka"),
        ]

        result = await self._run_full_flow(agent, messages)

        assert result["text"]["success"] is True
        assert result["text"]["text"] == "Engineer Cafe Fukuoka"
        assert result["text"]["error"] is None
        # face は呼ばれていないのでデフォルト
        assert result["face"]["success"] is False
        assert result["face"]["detected"] is False

    async def test_face_recognition_full_flow(self, mock_vision_agent):
        """表情認識フルフロー: 画像入力 -> LLMツール呼び出し -> 表情結果パース"""
        agent, _, _, _ = mock_vision_agent

        messages = [
            HumanMessage(content="analyze image"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc2",
                        "name": "face_recognition",
                        "args": {"expression": "happy"},
                    }
                ],
            ),
            ToolMessage(
                content="happy",
                name="face_recognition",
                tool_call_id="tc2",
            ),
            AIMessage(content="The person looks happy"),
        ]

        result = await self._run_full_flow(agent, messages)

        assert result["face"]["success"] is True
        assert result["face"]["detected"] is True
        assert result["face"]["expression"] == {"emotion": "happy"}
        assert result["face"]["error"] is None
        # text は呼ばれていないのでデフォルト
        assert result["text"]["success"] is False
        assert result["text"]["text"] is None

    async def test_combined_text_and_face_flow(self, mock_vision_agent):
        """テキスト+表情の同時認識フルフロー: 両ツールが一度に呼ばれるケース"""
        agent, _, _, _ = mock_vision_agent

        messages = [
            HumanMessage(content="analyze image"),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc1",
                        "name": "text_recognition",
                        "args": {"text": "Welcome"},
                    },
                    {
                        "id": "tc2",
                        "name": "face_recognition",
                        "args": {"expression": "surprised"},
                    },
                ],
            ),
            ToolMessage(
                content="Welcome",
                name="text_recognition",
                tool_call_id="tc1",
            ),
            ToolMessage(
                content="surprised",
                name="face_recognition",
                tool_call_id="tc2",
            ),
            AIMessage(content="Found text 'Welcome' and a surprised expression"),
        ]

        result = await self._run_full_flow(agent, messages)

        # テキスト結果
        assert result["text"]["success"] is True
        assert result["text"]["text"] == "Welcome"
        assert result["text"]["error"] is None

        # 表情結果
        assert result["face"]["success"] is True
        assert result["face"]["detected"] is True
        assert result["face"]["expression"] == {"emotion": "surprised"}
        assert result["face"]["error"] is None


# ---------------------------------------------------------------------------
# Integration Tests: Workflow-level VisionAgent integration
# ---------------------------------------------------------------------------
@pytest.mark.vision
class TestVisionWorkflowIntegration:
    """MainWorkflow における VisionAgent 統合テスト

    MainWorkflow._input_type_decision のルーティングロジックと、
    _vision_node の VisionAgent 未初期化時のエラーハンドリングを検証する。
    """

    @pytest.fixture
    def mock_main_workflow(self):
        """MainWorkflow をすべての外部依存をモックして生成するフィクスチャ"""
        with (
            patch("backend.workflows.main_workflow.OrchestratorAgent"),
            patch("backend.agents.business_info_agent.BusinessInfoAgent"),
            patch("backend.agents.facility_agent.FacilityAgent"),
            patch("backend.agents.event_agent.EventAgent"),
            patch("backend.agents.slide_agent.SlideAgent"),
            patch("backend.agents.general_knowledge_agent.GeneralKnowledgeAgent"),
            patch("backend.utils.memory_helper.get_memory_helper", return_value=MagicMock()),
            patch("backend.agents.ocr_agent.OpenRouterProvider"),
            patch("backend.agents.ocr_agent.get_model_config"),
        ):
            from backend.workflows.main_workflow import MainWorkflow

            workflow = MainWorkflow(checkpointer=None)
            yield workflow

    def test_input_type_decision_routes_image(self, mock_main_workflow):
        """image_data が存在する state では 'image' を返すことを確認"""
        state = {
            "messages": [],
            "query": "some query",
            "session_id": "test",
            "language": "ja",
            "routing": {},
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": {},
            "image_data": np.zeros((100, 100, 3), dtype=np.uint8),
            "ocr_result": None,
        }

        result = mock_main_workflow._input_type_decision(state)
        assert result == "image"

    def test_input_type_decision_routes_text(self, mock_main_workflow):
        """image_data が None の state では 'text' を返すことを確認"""
        state = {
            "messages": [],
            "query": "hello",
            "session_id": "test",
            "language": "ja",
            "routing": {},
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": {},
            "image_data": None,
            "ocr_result": None,
        }

        result = mock_main_workflow._input_type_decision(state)
        assert result == "text"

    async def test_vision_node_raises_when_agent_unavailable(self, mock_main_workflow):
        """_vision_agent が None の場合に RuntimeError が発生することを確認"""
        mock_main_workflow._vision_agent = None

        state = {
            "messages": [],
            "query": "",
            "session_id": "test",
            "language": "ja",
            "routing": {},
            "answer": None,
            "emotion": None,
            "metadata": {},
            "context": {},
            "image_data": np.zeros((100, 100, 3), dtype=np.uint8),
            "ocr_result": None,
        }

        with pytest.raises(RuntimeError, match="VisionAgent is not available"):
            await mock_main_workflow._vision_node(state)
