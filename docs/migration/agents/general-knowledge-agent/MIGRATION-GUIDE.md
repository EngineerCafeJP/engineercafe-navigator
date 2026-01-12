# General Knowledge Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
engineer-cafe-navigator-repo/frontend/src/
└── mastra/agents/general-knowledge-agent.ts    # 209行
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── general_knowledge_agent.py              # 新規作成
├── tools/
│   ├── rag_search.py                           # 既存（利用）
│   └── web_search.py                           # 新規作成
└── workflows/
    └── main_workflow.py                        # 既存（修正）
```

## 移行ステップ

### Step 1: ウェブ検索ツールの作成

**新規ファイル**: `backend/tools/web_search.py`

```python
# backend/tools/web_search.py

from typing import TypedDict, Literal
import httpx
from langchain.tools import tool

SupportedLanguage = Literal["ja", "en"]

class WebSearchInput(TypedDict):
    query: str
    language: SupportedLanguage

class WebSearchResult(TypedDict):
    success: bool
    text: str | None
    data: dict | None

@tool
def general_web_search(query: str, language: str = "ja") -> WebSearchResult:
    """
    一般的なウェブ検索を実行

    Args:
        query: 検索クエリ
        language: 言語 ('ja' または 'en')

    Returns:
        WebSearchResult: 検索結果
    """
    try:
        # TODO: 実際のWeb検索APIを統合
        # 例: Google Custom Search API, Bing API, DuckDuckGo API など

        # プレースホルダー実装
        search_results = _perform_web_search(query, language)

        if not search_results:
            return {
                "success": False,
                "text": None,
                "data": None
            }

        # 検索結果をテキストに整形
        context = _format_search_results(search_results, language)

        return {
            "success": True,
            "text": context,
            "data": {"context": context}
        }

    except Exception as e:
        print(f"[WebSearch] Error: {e}")
        return {
            "success": False,
            "text": None,
            "data": None
        }

def _perform_web_search(query: str, language: str) -> list[dict]:
    """
    実際のウェブ検索を実行（プレースホルダー）

    実装例:
    - Google Custom Search API
    - Bing Web Search API
    - DuckDuckGo API
    """
    # TODO: 実装
    return []

def _format_search_results(results: list[dict], language: str) -> str:
    """
    検索結果をテキストに整形
    """
    if not results:
        return ""

    formatted = []
    for result in results[:5]:  # 上位5件
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        formatted.append(f"{title}\n{snippet}")

    return "\n\n".join(formatted)
```

### Step 2: General Knowledge Agent 本体の移行

**新規ファイル**: `backend/agents/general_knowledge_agent.py`

```python
# backend/agents/general_knowledge_agent.py

from typing import TypedDict, Literal
import re
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

SupportedLanguage = Literal["ja", "en"]
EmotionType = Literal["helpful", "apologetic"]

class GeneralKnowledgeMetadata(TypedDict):
    confidence: float
    category: str
    sources: list[str]
    processing_info: dict

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: EmotionType
    agent_name: str
    language: SupportedLanguage
    metadata: GeneralKnowledgeMetadata

class GeneralKnowledgeAgent:
    """一般的な質問に対応するエージェント"""

    def __init__(self, llm: ChatGoogleGenerativeAI):
        self.llm = llm
        self.name = "GeneralKnowledgeAgent"

        self.instructions = """You are a general knowledge specialist who can answer a wide range of questions.
You handle:
- General information about Engineer Cafe
- AI and technology topics
- Fukuoka tech scene and startup information
- Questions that don't fit specific categories
Use both knowledge base and web search when appropriate.
Always respond in the same language as the question.

IMPORTANT: Always start your response with an emotion tag.
Available emotions: [happy], [sad], [angry], [relaxed], [surprised]

Use [relaxed] for informational responses about general topics
Use [happy] when sharing exciting tech news or positive information
Use [surprised] for unexpected or innovative topics
Use [sad] when unable to find information or discussing challenges"""

    async def answer_general_query(
        self,
        query: str,
        language: SupportedLanguage,
        rag_search_tool,
        web_search_tool
    ) -> UnifiedAgentResponse:
        """
        一般的な質問に回答

        Args:
            query: ユーザーからの質問
            language: 言語
            rag_search_tool: RAG検索ツール
            web_search_tool: Web検索ツール

        Returns:
            UnifiedAgentResponse: 統一レスポンス
        """
        print(f"[GeneralKnowledgeAgent] Processing general query: query={query}, language={language}")

        # ウェブ検索が必要かどうか判定
        needs_web_search = self._should_use_web_search(query)

        # ナレッジベース検索（常に実行）
        context = ""
        sources = []

        try:
            kb_result = await rag_search_tool.ainvoke({
                "query": query,
                "language": language,
                "limit": 10
            })

            if kb_result.get("success"):
                if kb_result.get("results"):
                    # 結果配列の場合
                    context = "\n\n".join([r["content"] for r in kb_result["results"]])
                    sources.append("knowledge base")
                elif kb_result.get("data", {}).get("context"):
                    # データオブジェクトの場合
                    context = kb_result["data"]["context"]
                    sources.append("knowledge base")
        except Exception as e:
            print(f"[GeneralKnowledgeAgent] RAG search error: {e}")

        # ウェブ検索（条件付き）
        if needs_web_search or not context:
            try:
                web_result = await web_search_tool.ainvoke({
                    "query": query,
                    "language": language
                })

                if web_result.get("success"):
                    web_context = web_result.get("text") or web_result.get("data", {}).get("context", "")
                    if web_context:
                        context = f"{context}\n\n{web_context}" if context else web_context
                        sources.append("web search")
            except Exception as e:
                print(f"[GeneralKnowledgeAgent] Web search error: {e}")

        # コンテキストがない場合はデフォルトレスポンス
        if not context:
            return self._get_default_general_response(language)

        # プロンプト構築
        prompt = self._build_general_prompt(query, context, sources, language)

        # LLM生成
        messages = [
            SystemMessage(content=self.instructions),
            HumanMessage(content=prompt)
        ]
        response = await self.llm.ainvoke(messages)
        response_text = response.content

        # 信頼度計算
        confidence = self._calculate_confidence(sources)

        # 感情抽出
        emotion = self._extract_emotion(response_text)

        return {
            "text": response_text,
            "emotion": emotion,
            "agent_name": self.name,
            "language": language,
            "metadata": {
                "confidence": confidence,
                "category": "general_knowledge",
                "sources": sources,
                "processing_info": {
                    "enhancedRag": False
                }
            }
        }

    def _should_use_web_search(self, query: str) -> bool:
        """ウェブ検索が必要かどうか判定"""
        lower_query = query.lower()

        # ウェブ検索が必要なキーワード
        web_search_keywords = [
            # 日本語
            '最新', '現在', '今', 'ニュース', 'トレンド', 'スタートアップ', 'ベンチャー',
            '技術', 'ai', '人工知能', '機械学習', 'プログラミング',
            # 英語
            'latest', 'current', 'now', 'news', 'trend', 'startup', 'venture',
            'technology', 'artificial intelligence', 'machine learning', 'programming'
        ]

        return any(keyword in lower_query for keyword in web_search_keywords)

    def _build_general_prompt(
        self,
        query: str,
        context: str,
        sources: list[str],
        language: SupportedLanguage
    ) -> str:
        """プロンプトを構築"""
        source_info = " and ".join(sources)

        if language == "en":
            return f"""Answer the following question using the provided information from {source_info}.

Question: {query}

Information:
{context}

Provide a comprehensive but concise answer. If the information is from web search, mention that it's current information. Be helpful and informative."""
        else:
            return f"""{source_info}から提供された情報を使用して、次の質問に答えてください。

質問: {query}

情報:
{context}

包括的だが簡潔な回答を提供してください。情報がウェブ検索からのものである場合は、それが最新の情報であることを述べてください。役立つ情報を提供してください。"""

    def _calculate_confidence(self, sources: list[str]) -> float:
        """信頼度を計算"""
        has_kb = "knowledge_base" in sources or "knowledge base" in sources
        has_web = "web_search" in sources or "web search" in sources

        if has_kb and has_web:
            return 0.9
        elif has_kb:
            return 0.8
        elif has_web:
            return 0.6
        else:
            return 0.3

    def _extract_emotion(self, text: str) -> EmotionType:
        """テキストから感情を抽出"""
        if text.startswith("[sad]"):
            return "apologetic"
        else:
            return "helpful"

    def _get_default_general_response(self, language: SupportedLanguage) -> UnifiedAgentResponse:
        """デフォルトレスポンスを生成"""
        if language == "en":
            text = "[sad]I'm sorry, I couldn't find specific information to answer your question. Please try rephrasing your question or ask about something else."
        else:
            text = "[sad]申し訳ございません。ご質問に答えるための具体的な情報が見つかりませんでした。質問を言い換えていただくか、別のことについてお尋ねください。"

        return {
            "text": text,
            "emotion": "apologetic",
            "agent_name": self.name,
            "language": language,
            "metadata": {
                "confidence": 0.3,
                "category": "general_knowledge",
                "sources": ["fallback"],
                "processing_info": {
                    "enhancedRag": False
                }
            }
        }
```

### Step 3: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
# backend/workflows/main_workflow.py

from backend.agents.general_knowledge_agent import GeneralKnowledgeAgent
from backend.tools.rag_search import rag_search_tool
from backend.tools.web_search import general_web_search
from langchain_google_genai import ChatGoogleGenerativeAI

class MainWorkflow:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash-exp",
            temperature=0.7
        )
        self.general_knowledge_agent = GeneralKnowledgeAgent(self.llm)
        self.graph = self._build_graph()

    async def _general_knowledge_node(self, state: WorkflowState) -> dict:
        """General Knowledgeノード"""
        query = state.get("query", "")
        language = state.get("language", "ja")

        # General Knowledge Agentを使用
        response = await self.general_knowledge_agent.answer_general_query(
            query=query,
            language=language,
            rag_search_tool=rag_search_tool,
            web_search_tool=general_web_search
        )

        return {
            "response": response["text"],
            "metadata": {
                **state.get("metadata", {}),
                "agent": response["agent_name"],
                "confidence": response["metadata"]["confidence"],
                "sources": response["metadata"]["sources"]
            }
        }

    def _build_graph(self):
        """ワークフローグラフを構築"""
        from langgraph.graph import StateGraph, END

        workflow = StateGraph(WorkflowState)

        # ノードを追加
        workflow.add_node("router", self._router_node)
        workflow.add_node("general_knowledge", self._general_knowledge_node)
        # ... 他のノード

        # エッジを追加
        workflow.set_entry_point("router")
        workflow.add_conditional_edges(
            "router",
            self._route_decision,
            {
                "general_knowledge": "general_knowledge",
                # ... 他のルート
            }
        )
        workflow.add_edge("general_knowledge", END)

        return workflow.compile()
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Web検索APIを選定した（Google Custom Search, Bing, etc.）
- [ ] APIキーと認証情報を準備した
- [ ] テスト環境を準備した

### Phase 2: ツール開発

- [ ] `web_search.py` を作成した
- [ ] Web検索APIを統合した
- [ ] 検索結果フォーマット機能を実装した
- [ ] 単体テストを作成・通過した

### Phase 3: Agent本体

- [ ] `general_knowledge_agent.py` を作成した
- [ ] `_should_use_web_search()` メソッドを実装した
- [ ] `_build_general_prompt()` メソッドを実装した
- [ ] `_calculate_confidence()` メソッドを実装した
- [ ] `_get_default_general_response()` メソッドを実装した
- [ ] 単体テストを作成・通過した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にGeneral Knowledge Agentを統合した
- [ ] ルーティング条件を正しく設定した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] 全クエリパターンをテストした
- [ ] パフォーマンスを計測した（目標: 4秒以下）
- [ ] 信頼度計算が正しく動作することを確認した
- [ ] ウェブ検索が適切にトリガーされることを確認した
- [ ] ログ出力を確認した

## Web検索API統合オプション

### Option 1: Google Custom Search API

```python
import httpx

async def _perform_web_search(query: str, language: str) -> list[dict]:
    api_key = os.getenv("GOOGLE_CUSTOM_SEARCH_API_KEY")
    cx = os.getenv("GOOGLE_CUSTOM_SEARCH_CX")

    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "lr": f"lang_{language}",
        "num": 5
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()

        return [
            {
                "title": item["title"],
                "snippet": item["snippet"],
                "link": item["link"]
            }
            for item in data.get("items", [])
        ]
```

### Option 2: Bing Web Search API

```python
async def _perform_web_search(query: str, language: str) -> list[dict]:
    api_key = os.getenv("BING_SEARCH_API_KEY")

    url = "https://api.bing.microsoft.com/v7.0/search"
    headers = {"Ocp-Apim-Subscription-Key": api_key}
    params = {
        "q": query,
        "mkt": "ja-JP" if language == "ja" else "en-US",
        "count": 5
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        data = response.json()

        return [
            {
                "title": item["name"],
                "snippet": item["snippet"],
                "link": item["url"]
            }
            for item in data.get("webPages", {}).get("value", [])
        ]
```

### Option 3: DuckDuckGo (無料)

```python
from duckduckgo_search import DDGS

async def _perform_web_search(query: str, language: str) -> list[dict]:
    with DDGS() as ddgs:
        results = list(ddgs.text(
            query,
            region="jp-jp" if language == "ja" else "us-en",
            max_results=5
        ))

        return [
            {
                "title": r["title"],
                "snippet": r["body"],
                "link": r["href"]
            }
            for r in results
        ]
```

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| Web検索が動作しない | APIキー未設定 | 環境変数を確認 |
| レスポンスが遅い | Web検索のタイムアウト | タイムアウト設定を調整 |
| 信頼度が低い | ソースが見つからない | キーワードリストを拡張 |
| 感情タグが正しくない | LLMの出力形式 | プロンプトを調整 |

## パフォーマンス最適化

### キャッシング戦略

```python
from functools import lru_cache
import hashlib

class GeneralKnowledgeAgent:
    def __init__(self, llm):
        self.llm = llm
        self._search_cache = {}

    async def _cached_web_search(self, query: str, language: str) -> dict:
        """キャッシュ付きウェブ検索"""
        cache_key = hashlib.md5(f"{query}:{language}".encode()).hexdigest()

        if cache_key in self._search_cache:
            print("[GeneralKnowledgeAgent] Using cached web search result")
            return self._search_cache[cache_key]

        result = await web_search_tool.ainvoke({
            "query": query,
            "language": language
        })

        self._search_cache[cache_key] = result
        return result
```

## 参考リンク

- [Google Custom Search API](https://developers.google.com/custom-search)
- [Bing Web Search API](https://www.microsoft.com/en-us/bing/apis/bing-web-search-api)
- [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search)
- [LangChain Tools](https://python.langchain.com/docs/modules/agents/tools/)
- [元実装: general-knowledge-agent.ts](../../engineer-cafe-navigator-repo/frontend/src/mastra/agents/general-knowledge-agent.ts)
