#!/usr/bin/env python3
"""
Debug Agent Tool - エージェント実装のデバッグツール

エージェントの動作をステップごとに確認し、RAG検索結果、
LLMプロンプト/レスポンス、エラー詳細を表示する対話的デバッグツール。

使用方法:
    python backend/debug_agent.py
    または
    make debug-agent

機能:
    1. エージェント動作のステップ実行
    2. RAG検索結果の確認
    3. LLMプロンプト/レスポンスのログ出力
    4. エラー詳細の表示
    5. 内部状態の可視化
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# プロジェクトルートをPythonパスに追加
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# バックエンドディレクトリをPythonパスに追加
BACKEND_ROOT = Path(__file__).parent
sys.path.insert(0, str(BACKEND_ROOT))

try:
    from agents.business_info_agent import BusinessInfoAgent
    from agents.event_agent import EventAgent
    from tools.enhanced_rag import EnhancedRAGSearch
    from llm import get_llm_provider, get_model_config
except ImportError:
    # フォールバック: backend.プレフィックスで再試行
    from backend.agents.business_info_agent import BusinessInfoAgent
    from backend.agents.event_agent import EventAgent
    from backend.tools.enhanced_rag import EnhancedRAGSearch
    from backend.llm import get_llm_provider, get_model_config


class Colors:
    """コンソール色定義"""

    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"
    END = "\033[0m"


class AgentDebugger:
    """エージェントデバッグツール"""

    def __init__(self, agent_type: str = "business_info", verbose: bool = False):
        """
        初期化

        Args:
            agent_type: エージェントタイプ (business_info, event)
            verbose: 詳細ログ出力
        """
        self.agent_type = agent_type
        self.verbose = verbose
        self.log_dir = PROJECT_ROOT / "logs" / "agent-debug"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # エージェント初期化
        if agent_type == "business_info":
            self.agent = BusinessInfoAgent()
        elif agent_type == "event":
            self.agent = EventAgent()
        else:
            raise ValueError(f"Unknown agent type: {agent_type}")

        # RAG検索ツール
        self.rag_search = EnhancedRAGSearch()

        # LLM Provider
        self.llm_provider = get_llm_provider()

        self.log_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

    def print_header(self, text: str) -> None:
        """ヘッダーを表示"""
        print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{text:^60}{Colors.END}")
        print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.END}\n")

    def print_step(self, step: str, description: str) -> None:
        """ステップを表示"""
        print(f"{Colors.CYAN}{Colors.BOLD}[STEP] {step}{Colors.END}")
        print(f"{Colors.BLUE}{description}{Colors.END}\n")

    def print_success(self, message: str) -> None:
        """成功メッセージを表示"""
        print(f"{Colors.GREEN}✓ {message}{Colors.END}")

    def print_error(self, message: str) -> None:
        """エラーメッセージを表示"""
        print(f"{Colors.RED}✗ {message}{Colors.END}")

    def print_warning(self, message: str) -> None:
        """警告メッセージを表示"""
        print(f"{Colors.YELLOW}⚠ {message}{Colors.END}")

    def print_json(self, data: Dict, title: str = "Data") -> None:
        """JSON形式でデータを表示"""
        print(f"{Colors.BOLD}{title}:{Colors.END}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print()

    def save_log(self, data: Dict, filename: str) -> None:
        """ログをファイルに保存"""
        log_file = self.log_dir / f"{self.log_session_id}_{filename}.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if self.verbose:
            print(f"{Colors.CYAN}Log saved: {log_file}{Colors.END}")

    async def test_rag_search(
        self, query: str, category: str = "general", language: str = "ja"
    ) -> Optional[Dict]:
        """
        RAG検索をテスト

        Args:
            query: 検索クエリ
            category: カテゴリ
            language: 言語

        Returns:
            検索結果
        """
        self.print_step("1", "RAG検索実行")
        print(f"  Query: {query}")
        print(f"  Category: {category}")
        print(f"  Language: {language}\n")

        try:
            result = await self.rag_search.search(
                query=query,
                category=category,
                language=language,
                include_advice=True,
                max_results=5,
            )

            if result.get("success"):
                data = result.get("data", {})
                self.print_success(f"Found {data.get('totalResults', 0)} results")

                # 結果を表示
                print(f"\n{Colors.BOLD}Top Entity:{Colors.END} {data.get('topEntity', 'N/A')}")
                print(f"\n{Colors.BOLD}Context:{Colors.END}")
                print(f"{data.get('context', 'No context')[:500]}...")

                if self.verbose and data.get("results"):
                    print(f"\n{Colors.BOLD}Top Results:{Colors.END}")
                    for i, r in enumerate(data.get("results", [])[:3], 1):
                        print(f"\n  {i}. {r.get('title', 'No title')}")
                        print(f"     Entity: {r.get('entity', 'N/A')}")
                        print(f"     Similarity: {r.get('original_similarity', 0):.3f}")
                        print(f"     Priority Score: {r.get('priority_score', 0):.3f}")

                # ログ保存
                self.save_log(result, f"rag_search_{category}")

                return result

            else:
                self.print_error(f"RAG search failed: {result.get('error', 'Unknown error')}")
                return None

        except Exception as e:
            self.print_error(f"RAG search error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return None

    async def test_llm_generation(
        self, prompt: str, config_name: str = "qa_response"
    ) -> Optional[str]:
        """
        LLM応答生成をテスト

        Args:
            prompt: プロンプト
            config_name: モデル設定名

        Returns:
            生成されたテキスト
        """
        self.print_step("2", "LLM応答生成")
        print(f"  Config: {config_name}")
        print(f"  Prompt length: {len(prompt)} characters\n")

        if self.verbose:
            print(f"{Colors.BOLD}Prompt:{Colors.END}")
            print(f"{prompt[:500]}...\n")

        try:
            config = get_model_config(config_name)
            response = await self.llm_provider.generate(
                messages=[{"role": "user", "content": prompt}], config=config
            )

            self.print_success(f"Generated {len(response)} characters")
            print(f"\n{Colors.BOLD}Response:{Colors.END}")
            print(response)

            # ログ保存
            self.save_log(
                {"prompt": prompt, "response": response, "config": config_name},
                f"llm_generation_{config_name}",
            )

            return response

        except Exception as e:
            self.print_error(f"LLM generation error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return None

    async def test_business_info_agent(
        self,
        query: str,
        request_type: Optional[str] = None,
        language: str = "ja",
    ) -> Optional[Dict]:
        """
        BusinessInfoAgentをテスト

        Args:
            query: クエリ
            request_type: リクエストタイプ
            language: 言語

        Returns:
            エージェント応答
        """
        self.print_header(f"BusinessInfoAgent Debug: {query}")

        print(f"{Colors.BOLD}Parameters:{Colors.END}")
        print(f"  Request Type: {request_type or 'auto'}")
        print(f"  Language: {language}")
        print()

        try:
            # RAG検索をテスト
            category = self.agent._map_request_type_to_category(request_type)
            rag_result = await self.test_rag_search(query, category, language)

            if not rag_result or not rag_result.get("success"):
                self.print_warning("RAG search returned no results")

            # エージェント実行
            self.print_step("3", "エージェント実行")

            result = await self.agent.answer_business_query(
                query=query, request_type=request_type, language=language
            )

            self.print_success("Agent execution completed")

            print(f"\n{Colors.BOLD}Answer:{Colors.END}")
            print(result.get("answer", "No answer"))

            print(f"\n{Colors.BOLD}Emotion:{Colors.END} {result.get('emotion', 'N/A')}")

            if self.verbose:
                self.print_json(result.get("metadata", {}), "Metadata")

            # ログ保存
            self.save_log(
                {
                    "query": query,
                    "request_type": request_type,
                    "language": language,
                    "result": result,
                },
                "agent_business_info",
            )

            return result

        except Exception as e:
            self.print_error(f"Agent error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return None

    async def test_event_agent(self, query: str, language: str = "ja") -> Optional[Dict]:
        """
        EventAgentをテスト

        Args:
            query: クエリ
            language: 言語

        Returns:
            エージェント応答
        """
        self.print_header(f"EventAgent Debug: {query}")

        print(f"{Colors.BOLD}Parameters:{Colors.END}")
        print(f"  Language: {language}")
        print()

        try:
            # エージェント実行
            self.print_step("1", "エージェント実行")

            result = await self.agent.answer_event_query(query=query, language=language)

            self.print_success("Agent execution completed")

            print(f"\n{Colors.BOLD}Answer:{Colors.END}")
            print(result.get("answer", "No answer"))

            print(f"\n{Colors.BOLD}Emotion:{Colors.END} {result.get('emotion', 'N/A')}")

            if self.verbose:
                self.print_json(result.get("metadata", {}), "Metadata")

            # ログ保存
            self.save_log({"query": query, "language": language, "result": result}, "agent_event")

            return result

        except Exception as e:
            self.print_error(f"Agent error: {e}")
            if self.verbose:
                import traceback

                traceback.print_exc()
            return None

    async def interactive_mode(self) -> None:
        """対話的デバッグモード"""
        self.print_header("Agent Debugger - Interactive Mode")

        print(f"{Colors.BOLD}Agent Type:{Colors.END} {self.agent_type}")
        print(f"{Colors.BOLD}Log Directory:{Colors.END} {self.log_dir}")
        print(f"{Colors.BOLD}Session ID:{Colors.END} {self.log_session_id}\n")

        print(f"{Colors.YELLOW}Commands:{Colors.END}")
        print("  test <query> - Test agent with query")
        print("  rag <query> - Test RAG search only")
        print("  llm <prompt> - Test LLM generation only")
        print("  verbose - Toggle verbose mode")
        print("  quit - Exit\n")

        while True:
            try:
                user_input = input(f"{Colors.GREEN}> {Colors.END}").strip()

                if not user_input:
                    continue

                if user_input == "quit":
                    print(f"\n{Colors.CYAN}Exiting...{Colors.END}")
                    break

                elif user_input == "verbose":
                    self.verbose = not self.verbose
                    print(
                        f"{Colors.YELLOW}Verbose mode: {'ON' if self.verbose else 'OFF'}{Colors.END}"
                    )

                elif user_input.startswith("test "):
                    query = user_input[5:].strip()
                    if self.agent_type == "business_info":
                        await self.test_business_info_agent(query)
                    elif self.agent_type == "event":
                        await self.test_event_agent(query)

                elif user_input.startswith("rag "):
                    query = user_input[4:].strip()
                    await self.test_rag_search(query)

                elif user_input.startswith("llm "):
                    prompt = user_input[4:].strip()
                    await self.test_llm_generation(prompt)

                else:
                    self.print_warning(f"Unknown command: {user_input}")

            except KeyboardInterrupt:
                print(f"\n\n{Colors.CYAN}Exiting...{Colors.END}")
                break
            except Exception as e:
                self.print_error(f"Error: {e}")
                if self.verbose:
                    import traceback

                    traceback.print_exc()


async def main():
    """メイン関数"""
    parser = argparse.ArgumentParser(description="Agent Debugger Tool")
    parser.add_argument(
        "--agent",
        "-a",
        type=str,
        default="business_info",
        choices=["business_info", "event"],
        help="Agent type to debug",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Query to test (if not provided, starts interactive mode)",
    )
    parser.add_argument(
        "--request-type",
        "-r",
        type=str,
        help="Request type for BusinessInfoAgent (hours, price, location)",
    )
    parser.add_argument(
        "--language", "-l", type=str, default="ja", choices=["ja", "en"], help="Language"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")

    args = parser.parse_args()

    debugger = AgentDebugger(agent_type=args.agent, verbose=args.verbose)

    if args.query:
        # クエリが指定されている場合は即座に実行
        if args.agent == "business_info":
            await debugger.test_business_info_agent(
                query=args.query, request_type=args.request_type, language=args.language
            )
        elif args.agent == "event":
            await debugger.test_event_agent(query=args.query, language=args.language)
    else:
        # 対話的モード
        await debugger.interactive_mode()


if __name__ == "__main__":
    asyncio.run(main())
