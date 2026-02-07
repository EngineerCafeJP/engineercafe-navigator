"""
Agent Tools - LangGraph @tool ラッパー

既存のエージェントを@toolデコレーターで包み、LangGraphのToolNodeで
動的に呼び出せるようにする。

各ドメインエージェントは固定パイプライン（RAG→LLM）を持つため、
内部ロジックは変更せず、ツールインターフェースのみを提供する。

使用例:
    from langchain_core.tools import tool
    from langgraph.prebuilt import ToolNode

    # 全エージェントツールをToolNodeに登録
    tools = get_all_agent_tools()
    tool_node = ToolNode(tools)

    # LLMにツールをバインド
    llm_with_tools = llm.bind_tools(tools)
"""

from typing import Optional
from langchain_core.tools import tool


# 遅延インポート用のエージェントキャッシュ
_agent_cache: dict = {}


def _get_facility_agent():
    """FacilityAgentの遅延初期化"""
    if "facility" not in _agent_cache:
        from backend.agents.facility_agent import FacilityAgent

        _agent_cache["facility"] = FacilityAgent()
    return _agent_cache["facility"]


def _get_business_info_agent():
    """BusinessInfoAgentの遅延初期化"""
    if "business_info" not in _agent_cache:
        from backend.agents.business_info_agent import BusinessInfoAgent

        _agent_cache["business_info"] = BusinessInfoAgent()
    return _agent_cache["business_info"]


def _get_event_agent():
    """EventAgentの遅延初期化"""
    if "event" not in _agent_cache:
        from backend.agents.event_agent import EventAgent

        _agent_cache["event"] = EventAgent()
    return _agent_cache["event"]


def _get_general_knowledge_agent():
    """GeneralKnowledgeAgentの遅延初期化"""
    if "general_knowledge" not in _agent_cache:
        from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent

        _agent_cache["general_knowledge"] = GeneralKnowledgeAgent()
    return _agent_cache["general_knowledge"]


def _get_slide_agent():
    """SlideAgentの遅延初期化"""
    if "slide" not in _agent_cache:
        from backend.agents.slide_agent import SlideAgent

        _agent_cache["slide"] = SlideAgent()
    return _agent_cache["slide"]


def _get_memory_agent():
    """MemoryAgentの遅延初期化"""
    if "memory" not in _agent_cache:
        from backend.agents.memory_agent import MemoryAgent
        from backend.utils.memory_helper import get_memory_helper

        memory_helper = get_memory_helper()
        _agent_cache["memory"] = MemoryAgent(memory_system=memory_helper)
    return _agent_cache["memory"]


@tool
async def facility_query_tool(
    query: str,
    request_type: Optional[str] = None,
    language: str = "ja",
    session_id: Optional[str] = None,
) -> str:
    """施設情報に関する質問に回答するツール。

    Wi-Fi、電源、コンセント、プリンター、地下施設（MTGスペース、集中スペース等）
    に関する質問に対応します。

    Args:
        query: ユーザーからの施設に関する質問
            例: "Wi-Fiは使えますか？", "電源はありますか？", "地下の集中スペースの予約方法は？"
        request_type: リクエストタイプ（wifi, facility, basement）
        language: 言語（ja, en）
        session_id: セッションID

    Returns:
        施設情報に関する回答テキスト
    """
    agent = _get_facility_agent()
    result = await agent.answer_facility_query(query, request_type, language, session_id)
    return result.get("answer", "")


@tool
async def business_info_tool(
    query: str,
    request_type: Optional[str] = None,
    language: str = "ja",
    session_id: Optional[str] = None,
) -> str:
    """営業情報に関する質問に回答するツール。

    営業時間、料金、予約、会員制度、支払い方法に関する質問に対応します。

    Args:
        query: ユーザーからの営業に関する質問
            例: "営業時間は？", "料金はいくら？", "予約は必要？"
        request_type: リクエストタイプ（hours, pricing, reservation, membership）
        language: 言語（ja, en）
        session_id: セッションID

    Returns:
        営業情報に関する回答テキスト
    """
    agent = _get_business_info_agent()
    result = await agent.answer_business_query(query, request_type, language, session_id)
    return result.get("answer", "")


@tool
async def event_info_tool(
    query: str,
    language: str = "ja",
    session_id: Optional[str] = None,
) -> str:
    """イベント情報に関する質問に回答するツール。

    開催予定のイベント、過去のイベント、イベント参加方法に関する質問に対応します。

    Args:
        query: ユーザーからのイベントに関する質問
            例: "今月のイベントは？", "勉強会はありますか？"
        language: 言語（ja, en）
        session_id: セッションID

    Returns:
        イベント情報に関する回答テキスト
    """
    agent = _get_event_agent()
    result = await agent.answer_event_query(query, language, session_id)
    return result.get("answer", "")


@tool
async def general_knowledge_tool(
    query: str,
    language: str = "ja",
    session_id: Optional[str] = None,
) -> str:
    """一般的な質問に回答するツール。

    Engineer Cafeに関する一般情報、AI・技術トピック、福岡のテックシーンに関する
    質問に対応します。ナレッジベースとWeb検索を組み合わせて回答します。

    Args:
        query: ユーザーからの一般的な質問
            例: "AIの最新トレンドは？", "福岡のスタートアップは？"
        language: 言語（ja, en）
        session_id: セッションID

    Returns:
        一般知識に関する回答テキスト
    """
    agent = _get_general_knowledge_agent()
    result = await agent.answer_general_query(query, language, session_id)
    return result.get("answer", "")


@tool
async def slide_action_tool(
    action: str,
    query: Optional[str] = None,
    language: str = "ja",
) -> str:
    """スライド操作に関するツール。

    スライドのナレーション、ページ移動、質問応答に対応します。

    Args:
        action: アクション種別（narrate, next, previous, goto, question）
        query: 質問テキスト（action="question"の場合に使用）
        language: 言語（ja, en）

    Returns:
        スライド操作の結果テキスト
    """
    agent = _get_slide_agent()
    result = await agent.handle_slide_action(action=action, query=query, language=language)
    return result.get("answer", "")


@tool
async def memory_query_tool(
    query: str,
    session_id: str,
    language: str = "ja",
) -> str:
    """会話履歴に関する質問に回答するツール。

    「さっき何を聞いた？」「前に話したことを覚えてる？」などの
    メモリ関連の質問に対応します。

    Args:
        query: ユーザーからの会話履歴に関する質問
        session_id: セッションID（必須）
        language: 言語（ja, en）

    Returns:
        会話履歴に関する回答テキスト
    """
    agent = _get_memory_agent()
    result = await agent.process_memory_query(query, session_id, language)
    return result.get("answer", "")


def get_all_agent_tools() -> list:
    """全エージェントツールのリストを取得

    Returns:
        LangGraph ToolNodeで使用可能なツールのリスト
    """
    return [
        facility_query_tool,
        business_info_tool,
        event_info_tool,
        general_knowledge_tool,
        slide_action_tool,
        memory_query_tool,
    ]


def get_domain_agent_tools() -> list:
    """ドメインエージェントツールのみを取得（スライド・メモリ除く）

    Returns:
        ドメイン特化ツールのリスト
    """
    return [
        facility_query_tool,
        business_info_tool,
        event_info_tool,
        general_knowledge_tool,
    ]


def clear_agent_cache() -> None:
    """エージェントキャッシュをクリア（テスト用）"""
    global _agent_cache
    _agent_cache = {}
