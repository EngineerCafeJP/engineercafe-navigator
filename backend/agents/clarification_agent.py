"""
ClarificationAgent骨組み（専門エンジニア向け）

曖昧な質問を検出し、明確化のための選択肢を生成するエージェント。
「カフェはどこ？」→「Engineer Cafe本郷ですか？秋葉原ですか？」

参考:
- docs/migration/agents/clarification-agent/README.md
- engineer-cafe-navigator-repo/src/mastra/agents/clarification-agent.ts (Mastra版)

TODO (専門エンジニア - Chie):
1. 曖昧さ検出ロジック実装
2. OpenRouter APIを使用した選択肢生成
3. 候補抽出アルゴリズム実装
4. ユーザーフレンドリーな質問文の生成
5. 感情タグの適切な設定
6. エラーハンドリングとフォールバック
"""

import logging
from typing import Dict, Any, List, Optional

# TODO: 実装時に必要なインポート
# from llm.openrouter import OpenRouterProvider
# from llm.models import get_model_config

logger = logging.getLogger(__name__)


class ClarificationAgent:
    """
    ClarificationAgent骨組み（専門エンジニア向け）

    このクラスは骨組みのみを提供します。完全実装は専門エンジニア（Chie）が担当。
    """

    def __init__(self):
        """
        初期化

        TODO:
        - OpenRouterProviderの初期化
        - モデル設定の取得（get_model_config("clarification")）
        - 曖昧さ検出の閾値設定
        """
        logger.info("ClarificationAgent骨組み初期化")
        # TODO: OpenRouterProvider等の初期化

    async def detect_ambiguity(self, query: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        曖昧さを検出

        Args:
            query: ユーザーの質問
            context: コンテキスト情報（オプショナル）

        Returns:
            True: 曖昧な質問, False: 明確な質問

        TODO:
        - キーワードベース検出（「カフェ」「イベント」など複数候補がある語）
        - LLMベース検出（複数の解釈が可能な質問）
        - 閾値判定ロジック
        """
        logger.info(f"曖昧さ検出（骨組み）: {query}")

        # TODO: 実装
        # プレースホルダー: 常にFalseを返す
        return False

    async def generate_clarification_options(
        self, query: str, context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, str]]:
        """
        明確化のための選択肢を生成

        Args:
            query: ユーザーの質問
            context: コンテキスト情報（オプショナル）

        Returns:
            選択肢のリスト
            例: [
                {"label": "Engineer Cafe本郷", "value": "hongo"},
                {"label": "Engineer Cafe秋葉原", "value": "akihabara"}
            ]

        TODO:
        - データベースから候補を抽出
        - LLMで自然な選択肢文を生成
        - 選択肢の優先順位付け
        """
        logger.info(f"選択肢生成（骨組み）: {query}")

        # TODO: 実装
        # プレースホルダー: 空リストを返す
        return []

    async def format_clarification_question(
        self, original_query: str, options: List[Dict[str, str]]
    ) -> str:
        """
        明確化の質問文をフォーマット

        Args:
            original_query: 元の質問
            options: 選択肢リスト

        Returns:
            フォーマットされた質問文
            例: "「カフェ」について聞きたいことは、Engineer Cafe本郷ですか？それともEngineer Cafe秋葉原ですか？"

        TODO:
        - 自然な日本語での質問文生成
        - 選択肢の埋め込み
        - 感情タグの設定
        """
        logger.info(f"質問文フォーマット（骨組み）: {original_query}")

        # TODO: 実装
        # プレースホルダー
        return "申し訳ありません。もう少し詳しく教えていただけますか？"

    async def process(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        明確化処理のメインエントリーポイント

        Args:
            query: ユーザーの質問
            context: コンテキスト情報（オプショナル）

        Returns:
            処理結果
            {
                "needs_clarification": bool,
                "clarification_question": str,
                "options": List[Dict[str, str]],
                "emotion": str
            }

        TODO:
        - 曖昧さ検出 → 選択肢生成 → 質問文フォーマットの統合
        - エラーハンドリング
        - ログ出力
        """
        logger.info(f"ClarificationAgent処理開始（骨組み）: {query}")

        try:
            # TODO: 実装
            # 1. 曖昧さ検出
            needs_clarification = await self.detect_ambiguity(query, context)

            # 2. 明確化が必要な場合、選択肢を生成
            options = []
            clarification_question = ""
            if needs_clarification:
                options = await self.generate_clarification_options(query, context)
                clarification_question = await self.format_clarification_question(query, options)

            return {
                "needs_clarification": needs_clarification,
                "clarification_question": clarification_question,
                "options": options,
                "emotion": "neutral",  # TODO: 適切な感情タグ
            }

        except Exception as e:
            logger.error(f"ClarificationAgent処理エラー（骨組み）: {e}", exc_info=True)
            # TODO: エラーハンドリング
            return {
                "needs_clarification": False,
                "clarification_question": "",
                "options": [],
                "emotion": "confused",
                "error": str(e),
            }
