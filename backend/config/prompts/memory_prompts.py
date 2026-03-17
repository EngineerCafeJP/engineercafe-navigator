"""
会話履歴問い合わせ用プロンプトテンプレート

メモリ関連クエリに対するプロンプト構築ロジックと分類キーワードを集約。
"""

from typing import Dict, Any

# 質問タイプ別プロンプトテンプレート
_JA_TEMPLATES: Dict[str, str] = {
    "question_history": (
        "あなたはエンジニアカフェのアシスタントです。\n"
        "ユーザーが過去に何を質問したか尋ねています。\n"
        "以下の会話履歴を参照して、ユーザーの過去の質問を簡潔に教えてください。\n\n"
        "会話履歴:\n{context_string}\n\n"
        "ユーザーの質問: {query}\n\n"
        "回答（1-2文で簡潔に）:"
    ),
    "answer_history": (
        "あなたはエンジニアカフェのアシスタントです。\n"
        "ユーザーが過去の回答内容を尋ねています。\n"
        "以下の会話履歴を参照して、過去の回答を簡潔にまとめてください。\n\n"
        "会話履歴:\n{context_string}\n\n"
        "ユーザーの質問: {query}\n\n"
        "回答（1-2文で簡潔に）:"
    ),
    "other_option": (
        "あなたはエンジニアカフェのアシスタントです。\n"
        "ユーザーが「もう一つの方」や「別の選択肢」について尋ねています。\n"
        "以下の会話履歴から、言及された別の選択肢について説明してください。\n\n"
        "会話履歴:\n{context_string}\n\n"
        "ユーザーの質問: {query}\n\n"
        "回答（1-2文で簡潔に）:"
    ),
    "general_memory": (
        "あなたはエンジニアカフェのアシスタントです。\n"
        "ユーザーが会話の内容について質問しています。\n"
        "以下の会話履歴を参照して、適切に回答してください。\n\n"
        "会話履歴:\n{context_string}\n\n"
        "ユーザーの質問: {query}\n\n"
        "回答（1-2文で簡潔に）:"
    ),
}

_EN_TEMPLATES: Dict[str, str] = {
    "question_history": (
        "You are an Engineer Cafe assistant.\n"
        "The user is asking about their previous questions.\n"
        "Refer to the conversation history and briefly tell them what they asked.\n\n"
        "Conversation history:\n{context_string}\n\n"
        "User's question: {query}\n\n"
        "Response (1-2 sentences):"
    ),
    "answer_history": (
        "You are an Engineer Cafe assistant.\n"
        "The user is asking about previous answers.\n"
        "Refer to the conversation history and summarize the previous answers.\n\n"
        "Conversation history:\n{context_string}\n\n"
        "User's question: {query}\n\n"
        "Response (1-2 sentences):"
    ),
    "other_option": (
        "You are an Engineer Cafe assistant.\n"
        "The user is asking about 'the other one' or alternative options.\n"
        "Explain the alternative mentioned in the conversation history.\n\n"
        "Conversation history:\n{context_string}\n\n"
        "User's question: {query}\n\n"
        "Response (1-2 sentences):"
    ),
    "general_memory": (
        "You are an Engineer Cafe assistant.\n"
        "The user is asking about the conversation.\n"
        "Refer to the history and respond appropriately.\n\n"
        "Conversation history:\n{context_string}\n\n"
        "User's question: {query}\n\n"
        "Response (1-2 sentences):"
    ),
}


def build_memory_prompt(
    query: str,
    context: Dict[str, Any],
    query_type: str,
    language: str = "ja",
) -> str:
    """メモリコンテキストからプロンプトを構築

    Args:
        query: ユーザーのクエリ
        context: メモリシステムから取得したコンテキスト
        query_type: 質問タイプ
        language: 言語設定

    Returns:
        構築されたプロンプト文字列
    """
    context_string = context.get("context_string", "")

    templates = _JA_TEMPLATES if language == "ja" else _EN_TEMPLATES
    template = templates.get(query_type, templates["general_memory"])

    return template.format(query=query, context_string=context_string)
