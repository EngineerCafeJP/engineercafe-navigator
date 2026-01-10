# Business Info Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
frontend/src/
├── mastra/agents/business-info-agent.ts    # 401行
├── mastra/tools/enhanced-rag-search.ts     # Enhanced RAG
├── mastra/tools/context-filter.ts          # コンテキストフィルタ
└── lib/simplified-memory.ts                # メモリシステム
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── business_info_agent.py              # 新規作成
├── tools/
│   ├── enhanced_rag_search.py              # 新規作成
│   └── context_filter.py                   # 新規作成
├── utils/
│   └── memory_system.py                    # 新規作成
└── workflows/
    └── main_workflow.py                    # 既存（修正）
```

## 移行ステップ

### Step 1: 依存モジュールの移行

#### 1.1 Enhanced RAG Search の移行

**元ファイル**: `frontend/src/mastra/tools/enhanced-rag-search.ts`

```python
# backend/tools/enhanced_rag_search.py

from typing import TypedDict, Literal
from supabase import create_client
import openai

class EnhancedRAGResult(TypedDict):
    success: bool
    data: dict | None
    error: str | None

class EnhancedRAGSearch:
    def __init__(self, supabase_client, openai_client):
        self.supabase = supabase_client
        self.openai = openai_client

    async def execute(
        self,
        query: str,
        category: str,
        language: str,
        include_advice: bool = True,
        max_results: int = 10
    ) -> EnhancedRAGResult:
        """Enhanced RAG検索を実行"""
        try:
            # クエリをエンベディングに変換
            embedding = await self._get_embedding(query)

            # ベクトル検索実行
            results = await self._vector_search(embedding, max_results)

            # エンティティ認識とスコアリング
            scored_results = self._score_results(results, query, category)

            # コンテキスト構築
            context = self._build_context(scored_results, include_advice)

            return {
                "success": True,
                "data": {"context": context, "results": scored_results},
                "error": None
            }
        except Exception as e:
            return {"success": False, "data": None, "error": str(e)}

    async def _get_embedding(self, text: str) -> list[float]:
        """OpenAI embeddings APIを使用"""
        response = await self.openai.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

    async def _vector_search(self, embedding: list[float], limit: int) -> list[dict]:
        """Supabaseでベクトル検索"""
        result = self.supabase.rpc(
            'match_knowledge_base',
            {
                'query_embedding': embedding,
                'match_count': limit,
                'match_threshold': 0.7
            }
        ).execute()
        return result.data

    def _score_results(self, results: list[dict], query: str, category: str) -> list[dict]:
        """エンティティ認識とスコアリング"""
        scored = []
        for r in results:
            score = r.get('similarity', 0)

            # エンティティ認識
            if 'saino' in query.lower() and 'saino' in r.get('content', '').lower():
                score += 0.1
            elif 'エンジニアカフェ' in query and 'エンジニアカフェ' in r.get('content', ''):
                score += 0.1

            # カテゴリマッチング
            if category and r.get('category') == category:
                score += 0.05

            scored.append({**r, 'final_score': score})

        return sorted(scored, key=lambda x: x['final_score'], reverse=True)

    def _build_context(self, results: list[dict], include_advice: bool) -> str:
        """コンテキスト文字列を構築"""
        context_parts = [r.get('content', '') for r in results[:5]]
        return '\n\n'.join(context_parts)
```

#### 1.2 Context Filter の移行

**元ファイル**: `frontend/src/mastra/tools/context-filter.ts`

```python
# backend/tools/context_filter.py

from typing import TypedDict

class FilterResult(TypedDict):
    success: bool
    data: dict | None

class ContextFilter:
    def execute(
        self,
        context: str,
        request_type: str,
        language: str,
        query: str
    ) -> FilterResult:
        """requestTypeに基づいてコンテキストをフィルタ"""
        if not request_type:
            return {"success": True, "data": {"filteredContext": context}}

        # リクエストタイプに応じたキーワード
        keywords = self._get_keywords(request_type, language)

        # 関連する文を抽出
        sentences = context.split('。')
        filtered_sentences = []

        for sentence in sentences:
            if any(kw in sentence for kw in keywords):
                filtered_sentences.append(sentence)

        filtered_context = '。'.join(filtered_sentences)
        if not filtered_context:
            filtered_context = context  # フォールバック

        return {
            "success": True,
            "data": {"filteredContext": filtered_context}
        }

    def _get_keywords(self, request_type: str, language: str) -> list[str]:
        """リクエストタイプに応じたキーワードリスト"""
        keywords_map = {
            'hours': {
                'ja': ['営業時間', '時間', '開館', '閉館', '開い', '閉ま'],
                'en': ['hours', 'open', 'close', 'time']
            },
            'price': {
                'ja': ['料金', '価格', '無料', '有料', '円'],
                'en': ['price', 'cost', 'free', 'fee', 'yen']
            },
            'location': {
                'ja': ['場所', '住所', 'アクセス', '行き方', '駅'],
                'en': ['location', 'address', 'access', 'station', 'direction']
            }
        }
        return keywords_map.get(request_type, {}).get(language, [])
```

### Step 2: Business Info Agent 本体の移行

**元ファイル**: `frontend/src/mastra/agents/business-info-agent.ts`

```python
# backend/agents/business_info_agent.py

from typing import TypedDict, Literal
import re
from backend.tools.enhanced_rag_search import EnhancedRAGSearch
from backend.tools.context_filter import ContextFilter
from backend.utils.memory_system import SimplifiedMemorySystem

SupportedLanguage = Literal["ja", "en"]

class BusinessInfoResponse(TypedDict):
    text: str
    emotion: str
    agent_name: str
    language: str
    metadata: dict

class BusinessInfoAgent:
    def __init__(self, llm, supabase_client, openai_client):
        self.llm = llm
        self.memory = SimplifiedMemorySystem('shared', supabase_client)
        self.enhanced_rag = EnhancedRAGSearch(supabase_client, openai_client)
        self.context_filter = ContextFilter()

    async def answer_business_query(
        self,
        query: str,
        category: str,
        request_type: str | None,
        language: SupportedLanguage,
        session_id: str | None = None
    ) -> BusinessInfoResponse:
        """ビジネス情報クエリに回答"""
        print(f"[BusinessInfoAgent] Processing: {query}")

        # 文脈継承チェック
        effective_request_type = request_type
        context_entity = None

        if session_id and self._is_short_context_query(query):
            memory_context = await self.memory.get_context(
                query,
                include_knowledge_base=False,
                language=language,
                inherit_context=True
            )

            if memory_context.get('inherited_request_type'):
                effective_request_type = memory_context['inherited_request_type']
                print(f"[BusinessInfoAgent] Inherited: {effective_request_type}")

            # エンティティ検出
            context_string = memory_context.get('context_string', '')
            if 'サイノカフェ' in context_string or 'saino' in context_string.lower():
                context_entity = 'saino'
            elif 'エンジニアカフェ' in context_string:
                context_entity = 'engineer'

        # クエリ拡張
        search_query = query
        if self._is_short_context_query(query) or context_entity:
            search_query = self._enhance_context_query(
                query, effective_request_type, language, context_entity
            )
            print(f"[BusinessInfoAgent] Enhanced query: {search_query}")

        # Enhanced RAG検索
        rag_category = self._map_request_type_to_category(effective_request_type)
        search_result = await self.enhanced_rag.execute(
            query=search_query,
            category=rag_category,
            language=language,
            include_advice=True,
            max_results=10
        )

        if not search_result['success']:
            return self._get_default_response(language, category, request_type)

        context = search_result['data'].get('context', '')
        if not context:
            return self._get_default_response(language, category, request_type)

        # コンテキストフィルタリング
        if effective_request_type:
            filter_result = self.context_filter.execute(
                context=context,
                request_type=effective_request_type,
                language=language,
                query=query
            )
            if filter_result['success']:
                context = filter_result['data']['filteredContext']

        # プロンプト構築とLLM応答
        prompt = self._build_prompt(query, context, effective_request_type, language)
        response = await self.llm.generate(prompt)

        # レスポンス構築
        emotion = self._determine_emotion(effective_request_type)
        sources = ['enhanced_rag']

        return {
            "text": response,
            "emotion": emotion,
            "agent_name": "BusinessInfoAgent",
            "language": language,
            "metadata": {
                "confidence": 0.85,
                "category": category,
                "request_type": effective_request_type,
                "sources": sources,
                "processing_info": {
                    "filtered": effective_request_type is not None,
                    "context_inherited": effective_request_type != request_type,
                    "enhanced_rag": True
                }
            }
        }

    def _is_short_context_query(self, query: str) -> bool:
        """文脈依存クエリかどうか判定"""
        trimmed = query.strip()

        context_patterns = [
            r'^土曜[日]?は.*',
            r'^日曜[日]?は.*',
            r'^平日は.*',
            r'^saino[のは方]?.*',
            r'^そっち[のは]?.*',
            r'^あっち[のは]?.*',
        ]

        for pattern in context_patterns:
            if re.match(pattern, trimmed):
                return True

        return len(trimmed) < 10

    def _enhance_context_query(
        self,
        query: str,
        request_type: str | None,
        language: SupportedLanguage,
        context_entity: str | None
    ) -> str:
        """文脈に基づいてクエリを拡張"""
        lower_query = query.lower()

        # エンティティ優先
        if context_entity == 'saino':
            if request_type == 'hours':
                return 'sainoカフェの営業時間' if language == 'ja' else 'saino cafe operating hours'
            if request_type == 'price':
                return 'sainoカフェの料金 メニュー' if language == 'ja' else 'saino cafe prices menu'
            return 'sainoカフェ 情報' if language == 'ja' else 'saino cafe information'

        # 曜日関連
        if '土曜' in lower_query or '日曜' in lower_query or '平日' in lower_query:
            return 'エンジニアカフェ 営業時間 曜日' if language == 'ja' else 'engineer cafe operating hours days'

        # requestTypeベース
        if request_type == 'hours':
            return f'{query} 営業時間' if language == 'ja' else f'{query} operating hours'
        if request_type == 'price':
            return f'{query} 料金 価格' if language == 'ja' else f'{query} price cost'
        if request_type == 'location':
            return f'{query} 場所 アクセス' if language == 'ja' else f'{query} location access'

        return query

    def _map_request_type_to_category(self, request_type: str | None) -> str:
        """requestTypeをEnhanced RAGカテゴリにマッピング"""
        mapping = {
            'hours': 'hours',
            'price': 'pricing',
            'location': 'location',
            'access': 'location',
        }
        return mapping.get(request_type or '', 'general')

    def _build_prompt(
        self,
        query: str,
        context: str,
        request_type: str | None,
        language: SupportedLanguage
    ) -> str:
        """LLM用プロンプトを構築"""
        if request_type:
            type_prompt = self._get_request_type_prompt(request_type, language)
            if language == 'en':
                return f"""Extract ONLY the {type_prompt} from the following information to answer the question.

Question: {query}
Information: {context}

Answer with ONLY the {type_prompt}. Maximum 1-2 sentences.
IMPORTANT: Start your response with [relaxed] for information or [happy] for positive news."""
            else:
                return f"""次の情報から{type_prompt}のみを抽出して質問に答えてください。

質問: {query}
情報: {context}

{type_prompt}のみを答えてください。最大1-2文。
重要: 情報提供の場合は[relaxed]、良いニュースの場合は[happy]で回答を始めてください。"""
        else:
            if language == 'en':
                return f"""Answer the question using the provided information. Be concise and direct.

Question: {query}
Information: {context}

Answer briefly (1-2 sentences) with only the relevant information.
IMPORTANT: Start with an emotion tag: [relaxed] for info, [happy] for positive news, [sad] for unavailable."""
            else:
                return f"""提供された情報を使って質問に答えてください。簡潔で直接的に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（1-2文）答えてください。
重要: 感情タグで回答を始めてください: [relaxed]/[happy]/[sad]。"""

    def _get_request_type_prompt(self, request_type: str, language: SupportedLanguage) -> str:
        """requestTypeに対応するプロンプト文字列"""
        prompts = {
            'hours': {'en': 'operating hours', 'ja': '営業時間'},
            'price': {'en': 'pricing information', 'ja': '料金情報'},
            'location': {'en': 'location information', 'ja': '場所情報'},
        }
        return prompts.get(request_type, {}).get(language, 'requested information' if language == 'en' else '要求された情報')

    def _determine_emotion(self, request_type: str | None) -> str:
        """レスポンスの感情を決定"""
        emotions = {
            'hours': 'informative',
            'price': 'informative',
            'location': 'guiding',
        }
        return emotions.get(request_type or '', 'helpful')

    def _get_default_response(
        self,
        language: SupportedLanguage,
        category: str | None,
        request_type: str | None
    ) -> BusinessInfoResponse:
        """デフォルトレスポンス（情報なし時）"""
        text = (
            "[sad]申し訳ございません。お探しの情報が見つかりませんでした。"
            if language == 'ja' else
            "[sad]I'm sorry, I couldn't find the specific information you're looking for."
        )

        return {
            "text": text,
            "emotion": "apologetic",
            "agent_name": "BusinessInfoAgent",
            "language": language,
            "metadata": {
                "confidence": 0.3,
                "category": category,
                "request_type": request_type,
                "sources": ["fallback"],
                "processing_info": {
                    "filtered": False,
                    "context_inherited": False,
                    "enhanced_rag": False
                }
            }
        }
```

### Step 3: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
from backend.agents.business_info_agent import BusinessInfoAgent

class MainWorkflow:
    def __init__(self, llm, supabase_client, openai_client):
        self.business_info_agent = BusinessInfoAgent(llm, supabase_client, openai_client)
        self.graph = self._build_graph()

    async def _business_info_node(self, state: WorkflowState) -> dict:
        """ビジネス情報ノード"""
        query = state["query"]
        language = state["language"]
        session_id = state.get("session_id")
        routing_metadata = state.get("metadata", {}).get("routing", {})

        result = await self.business_info_agent.answer_business_query(
            query=query,
            category=routing_metadata.get("category", "facility-info"),
            request_type=routing_metadata.get("request_type"),
            language=language,
            session_id=session_id
        )

        return {
            "response": result["text"],
            "metadata": {
                **state.get("metadata", {}),
                "business_info": result["metadata"]
            }
        }
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Pythonの依存パッケージを確認した（langchain, langgraph, supabase, openai）
- [ ] テスト環境を準備した

### Phase 2: ツール移行

- [ ] `enhanced_rag_search.py` を作成した
- [ ] `context_filter.py` を作成した
- [ ] 単体テストを作成・通過した

### Phase 3: Agent本体

- [ ] `business_info_agent.py` を作成した
- [ ] 文脈継承ロジックを移行した
- [ ] クエリ拡張ロジックを移行した
- [ ] 単体テストを作成・通過した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にBusinessInfoAgentを統合した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] 営業時間クエリをテストした
- [ ] 料金クエリをテストした
- [ ] 場所クエリをテストした
- [ ] 文脈継承（「土曜日は？」等）をテストした
- [ ] Sainoカフェクエリをテストした
- [ ] パフォーマンスを計測した

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| Enhanced RAG結果が空 | エンベディング次元不一致 | 1536次元を確認 |
| 文脈継承が動作しない | sessionIdが未設定 | sessionIdの伝播を確認 |
| フィルタで情報が消える | キーワード不足 | キーワードリストを拡充 |
| 感情タグが欠落 | プロンプト不備 | プロンプトテンプレートを確認 |

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Supabase Python](https://supabase.com/docs/reference/python)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
