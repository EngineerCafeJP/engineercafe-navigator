"""Message windowing utility tests"""

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from backend.utils.message_windowing import MessageWindow, apply_message_window


class TestMessageWindow:
    def test_short_conversation_unchanged(self):
        """Short conversations should pass through unchanged"""
        window = MessageWindow(max_messages=20)
        msgs = [HumanMessage(content="Hello"), AIMessage(content="Hi!")]
        result = window.apply_window(msgs)
        assert len(result) == 2

    def test_long_conversation_windowed(self):
        """Long conversations should be windowed"""
        window = MessageWindow(max_messages=5)
        msgs = []
        for i in range(20):
            msgs.append(HumanMessage(content=f"Question {i}"))
            msgs.append(AIMessage(content=f"Answer {i}"))

        result = window.apply_window(msgs)
        # Should have max_messages conv msgs + 1 summary
        assert len(result) <= 5 + 1  # 5 recent + 1 summary

    def test_window_summary_preserves_explicit_user_memory_facts(self):
        """Dropped messages should leave explicit user facts in the summary."""
        window = MessageWindow(max_messages=4)
        msgs = [
            HumanMessage(
                content="この会話では、私の希望席は窓側で、目的は集中作業です。覚えてください。"
            ),
            AIMessage(content="承知しました。"),
        ]
        for i in range(8):
            msgs.append(HumanMessage(content=f"ターン {i} です。助言をください。"))
            msgs.append(AIMessage(content=f"助言 {i} です。"))

        result = window.apply_window(msgs)
        summaries = [m for m in result if isinstance(m, SystemMessage)]

        assert summaries
        summary_text = summaries[0].content
        assert "Important earlier user facts" in summary_text
        assert "希望席は窓側" in summary_text
        assert "目的は集中作業" in summary_text

    def test_system_messages_preserved(self):
        """System messages should always be preserved"""
        window = MessageWindow(max_messages=3)
        msgs = [
            SystemMessage(content="You are a helpful assistant"),
            HumanMessage(content="Q1"),
            AIMessage(content="A1"),
            HumanMessage(content="Q2"),
            AIMessage(content="A2"),
            HumanMessage(content="Q3"),
            AIMessage(content="A3"),
            HumanMessage(content="Q4"),
            AIMessage(content="A4"),
        ]

        result = window.apply_window(msgs)
        sys_msgs = [m for m in result if isinstance(m, SystemMessage)]
        assert len(sys_msgs) >= 1  # Original system message preserved

    def test_should_compact(self):
        """should_compact returns True when threshold exceeded"""
        window = MessageWindow(summary_threshold=5)
        msgs = [HumanMessage(content=f"msg {i}") for i in range(10)]
        assert window.should_compact(msgs) is True

    def test_should_not_compact_below_threshold(self):
        """should_compact returns False when under threshold"""
        window = MessageWindow(summary_threshold=30)
        msgs = [HumanMessage(content=f"msg {i}") for i in range(5)]
        assert window.should_compact(msgs) is False

    def test_estimate_tokens(self):
        """Token estimation should return reasonable values"""
        window = MessageWindow()
        msgs = [HumanMessage(content="Hello world")]
        tokens = window.estimate_tokens(msgs)
        assert tokens > 0

    def test_apply_message_window_convenience(self):
        """Convenience function should work"""
        msgs = [HumanMessage(content="Hello"), AIMessage(content="Hi!")]
        result = apply_message_window(msgs)
        assert len(result) == 2
