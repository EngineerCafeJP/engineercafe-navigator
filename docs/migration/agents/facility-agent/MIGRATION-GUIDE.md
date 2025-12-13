# Router Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
frontend/src/
├── mastra/agents/facility-agent.ts         # 378行
├── mastra/tools/enhanced-rag-search.ts     # Enhanced RAG
├── mastra/tools/context-filter.ts          # コンテキストフィルタ
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── facility_agent.py                   # 新規作成
├── tools/
│   ├── enhanced_rag_search.py              # 新規作成
│   └── context_filter.py                   # 新規作成
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
            'wifi': {
                'ja': ['Wi-Fi', 'Wifi', '無線', 'インターネット', 'ネット', '接続', 'パスワード'],
                'en': ['Wi-Fi', 'Wifi', 'internet', 'network', 'connection', 'wireless', 'password']
            },
            'facility': {
                'ja': ['設備', '電源', 'コンセント', 'プリンター', 'プロジェクター', '機器', '貸出'],
                'en': ['facility', 'equipment', 'power outlet', 'printer', 'projector', 'device', 'loan']
            },
            'basement': {
                'ja': ['地下', 'B1', 'MTGスペース', '集中', 'アンダー', 'Makers', 'B1F', 'スペース', '会議室'],
                'en': ['basement', 'B1', 'MTG space', 'focus', 'under space', 'makers space', 'underground', 'meeting room']
            }
        }
        return keywords_map.get(request_type, {}).get(language, [])
```

### Step 2: Facility Agent 本体の移行

**元ファイル**: `src/mastra/agents/facility-agent.ts`

```python
# backend/agents/facility_agent.py

from typing import TypedDict, Any, Literal, Optional
import asyncio # async/awaitを再現するために必要
import re # 正規表現の再現に必要
from langchain_core.messages import AIMessage, HumanMessage # LLM呼び出しと応答整形用
from backend.tools.enhanced_rag_search import EnhancedRAGResult # ツール結果の型をインポート
# 注: UnifiedAgentResponse, SupportedLanguage, createUnifiedResponse は utils/models に移行される前提

# 簡略化された型定義 (実際の移行ではbackend/modelsに定義)
SupportedLanguage = Literal["ja", "en"]

class UnifiedAgentResponse(TypedDict):
    text: str
    emotion: str
    agentName: str
    language: SupportedLanguage
    metadata: dict

def create_unified_response(text: str, emotion: str, agent_name: str, language: SupportedLanguage, metadata: dict) -> UnifiedAgentResponse:
    return {
        "text": text,
        "emotion": emotion,
        "agentName": agent_name,
        "language": language,
        "metadata": metadata
    }

class FacilityAgent:
    def __init__(self, config: dict, llm_client: Any):
        """
        FacilityAgentの初期化。LLMクライアントとツールの格納庫を設定。
        """
        self.llm_client = llm_client # LLMを外部から受け取る
        self._tools: dict[str, Any] = {}
        
        # TypeScriptのinstructionsを保持 (プロンプトテンプレートに組み込む)
        self.instructions = f"""You are a facility information specialist for Engineer Cafe.
            You provide detailed information about:
            - Facilities and equipment (Wi-Fi, power outlets, etc.)
            - Meeting rooms and spaces
            - Basement facilities
            - Technical equipment (3D printers, etc.)
            Focus on practical details that help visitors use the facilities.
            Always respond in the same language as the question.
            
            IMPORTANT: Always start your response with an emotion tag at the very beginning.
            Available emotions: [happy], [sad], [relaxed]
            
            - Use [happy] when describing available facilities or positive features
            - Use [sad] when mentioning unavailable facilities or limitations
            - Use [relaxed] for general facility information or neutral descriptions
            - The emotion tag MUST be the first thing in your response, before any other text"""

    def add_tool(self, name: str, tool: Any):
        """外部からツールを注入するメソッド"""
        self._tools[name] = tool

    async def run(self, state: dict) -> dict:
        """
        LangGraphノードとして実行されるメインメソッド (answerFacilityQueryのロジックを再現)
        """
        query = state.get('query', '')
        request_type = state.get('request_type')
        language = state.get('language', 'ja')

        agent_response = await self.answer_facility_query(query, request_type, language)
        
        # ワークフローの状態を更新して返す
        return {
            "answer": agent_response["text"],
            "emotion": agent_response["emotion"],
            "metadata": {
                **state.get("metadata", {}),
                "agentName": agent_response["agentName"],
                "confidence": agent_response["metadata"]["confidence"],
                "category": agent_response["metadata"]["category"],
                "requestType": agent_response["metadata"]["requestType"],
                "sources": agent_response["metadata"]["sources"],
                "processingInfo": agent_response["metadata"]["processingInfo"]
            }
        }
    
    async def answer_facility_query(
        self, query: str, request_type: Optional[str], language: SupportedLanguage
    ) -> UnifiedAgentResponse:
        """施設情報クエリに回答するロジック"""
        
        print(f'[FacilityAgent] Processing query: query={query}, request_type={request_type}, language={language}')

        enhanced_query = self._enhance_query(query, request_type)
        
        enhanced_rag_tool = self._tools.get('enhancedRagSearch')
        rag_tool = self._tools.get('ragSearch')
        search_tool = enhanced_rag_tool or rag_tool
        
        if not search_tool:
            print('[FacilityAgent] No RAG search tool available')
            return self._get_default_facility_response(language, request_type)

        search_result: Optional[EnhancedRAGResult] = None
        try:
            # 検索ツール実行ロジックの再現
            if search_tool == enhanced_rag_tool:
                search_result = await search_tool.execute(
                    query=enhanced_query,
                    category='facility-info',
                    language=language,
                    include_advice=True,
                    max_results=10
                )
            else:
                search_result = await search_tool.execute(
                    query=enhanced_query,
                    language=language,
                    limit=10
                )
        except Exception as error:
            print(f'[FacilityAgent] RAG search error: {error}')
            return self._get_default_facility_response(language, request_type)
        
        if not search_result or not search_result.get('success'):
            return self._get_default_facility_response(language, request_type)
        
        context = self._build_context_from_search_result(search_result)

        if not context:
            return self._get_default_facility_response(language, request_type)
        
        # 施設特有のフィルタリング (Basement)
        if request_type == 'basement' and context:
            specific_facility = self._detect_specific_facility(query)
            if specific_facility:
                context = self._filter_context_for_specific_facility(context, specific_facility, language)
                print(f'[FacilityAgent] Filtered context for specific facility: {specific_facility}')
        
        # Context Filter Toolの適用
        if request_type:
            context_filter_tool = self._tools.get('contextFilter')
            if context_filter_tool:
                try:
                    filter_result = await context_filter_tool.execute(
                        context=context,
                        request_type=request_type,
                        language=language,
                        query=query
                    )
                    
                    if filter_result.get('success'):
                        context = filter_result['data'].get('filteredContext', context)
                except Exception as error:
                    print(f'[FacilityAgent] Context filter error: {error}')
                    # フィルタリングに失敗しても、フィルタなしのコンテキストで続行

        # プロンプト構築とLLM生成
        prompt = self._build_facility_prompt(query, context, request_type, language)
        
        # LLM呼び出し (LangChain/LLMクライアントの生成メソッドを使用)
        response_text = "施設情報が見つかりました。" # 仮の応答
        # 実際には: response = await self.llm_client.generate([HumanMessage(content=prompt)])
        # response_text = response.text
        
        return self._create_response_from_text(response_text, search_tool == enhanced_rag_tool, request_type, language)

    # --- ユーティリティメソッド ---

    def _enhance_query(self, query: str, request_type: Optional[str]) -> str:
        """TypeScriptの enhanceQuery メソッドを再現"""
        lower_query = query.lower()
        if request_type == 'wifi':
            return f"{query} 無料Wi-Fi インターネット 接続 wireless internet connection"
        
        if '地下' in query or 'basement' in lower_query or request_type == 'basement':
            if 'MTG' in query or 'ミーティング' in query:
                return f"{query} 地下MTGスペース basement meeting space B1"
            elif '集中' in query:
                return f"{query} 地下集中スペース basement focus space B1"
            elif 'アンダー' in query or 'under' in lower_query:
                return f"{query} 地下アンダースペース basement under space B1"
            elif 'Makers' in query or 'メーカー' in query:
                return f"{query} 地下Makersスペース basement makers space B1"
            
            return f"{query} 地下 B1 B1F 地下1階 MTGスペース 集中スペース アンダースペース Makersスペース basement floor underground meeting focus under makers space"
        
        if '会議室' in query or 'meeting room' in lower_query:
            return f"{query} 会議室 ミーティングルーム meeting room MTG 予約"
        
        if request_type == 'facility' or '設備' in query or 'equipment' in lower_query:
            return f"{query} 設備 電源 コンセント プリンター facilities equipment power outlet"
        
        return query

    def _build_context_from_search_result(self, search_result: dict) -> str:
        """RAG検索結果からコンテキスト文字列を構築"""
        if search_result.get('results') and isinstance(search_result['results'], list):
            # 標準RAGツールの結果形式
            return '\n\n'.join(r.get('content', '') for r in search_result['results'])
        elif search_result.get('data') and search_result['data'].get('context'):
            # エンハンスドRAGツールの結果形式
            return search_result['data']['context']
        return ''

    def _detect_specific_facility(self, query: str) -> Optional[str]:
        """特定の地下施設名を検出"""
        lower_query = query.lower()
        if 'MTG' in query or 'ミーティング' in query:
            return 'MTGスペース'
        elif '集中' in query:
            return '集中スペース'
        elif 'アンダー' in query or 'under' in lower_query:
            return 'アンダースペース'
        elif 'Makers' in query or 'メーカー' in query:
            return 'Makersスペース'
        return None

    def _filter_context_for_specific_facility(self, context: str, facility_name: str, language: SupportedLanguage) -> str:
        """地下施設のコンテキストを特定の施設に絞り込む"""
        # TypeScriptの正規表現 ([。\n]+) に相当する分割
        sections = re.split(r'[。\n]+', context)
        sections = [s.strip() for s in sections if s.strip()]
        
        filtered_sections = []
        facility_lower = facility_name.lower()
        
        for section in sections:
            section_lower = section.lower()
            
            is_match = section.find(facility_name) != -1 or section_lower.find(facility_lower) != -1
            
            # 特定のキーワードによるヒューリスティックマッチングを再現
            if facility_name == 'MTGスペース' and ('meeting' in section_lower or 'mtg' in section_lower):
                is_match = True
            elif facility_name == '集中スペース' and 'focus' in section_lower:
                is_match = True
            elif facility_name == 'アンダースペース' and 'under' in section_lower:
                is_match = True
            elif facility_name == 'Makersスペース' and 'makers' in section_lower:
                is_match = True

            if is_match:
                filtered_sections.append(section)
        
        if not filtered_sections:
            return context
        
        return '。'.join(filtered_sections)

    def _build_facility_prompt(self, query: str, context: str, request_type: Optional[str], language: SupportedLanguage) -> str:
        """TypeScriptの buildFacilityPrompt メソッドを再現"""
        # instructionsをシステムプロンプトとして使用し、質問とコンテキストをユーザープロンプトに含める

        # プロンプト分岐ロジックの再現 (requestTypeに基づく)
        # ... (ここでは長大なプロンプトを省略し、構造のみ示します)
        
        base_prompt = f"{self.instructions}\n\n質問: {query}\n情報: {context}\n\n上記の情報を利用して質問に回答してください。"
        return base_prompt

    def _get_default_facility_response(self, language: SupportedLanguage, request_type: Optional[str]) -> UnifiedAgentResponse:
        """情報が見つからなかった場合のデフォルト応答"""
        text = "I couldn't find specific information about that facility or equipment. [sad] Please ask the staff for detailed information about our facilities." if language == 'en' \
            else "その施設や設備に関する具体的な情報が見つかりませんでした。[sad] 施設の詳細についてはスタッフにお尋ねください。"
        
        return create_unified_response(
            text, 'apologetic', 'FacilityAgent', language,
            {'confidence': 0.3, 'category': 'facilities', 'requestType': request_type, 'sources': ['fallback']}
        )
    
    def _create_response_from_text(self, response_text: str, is_enhanced_rag: bool, request_type: Optional[str], language: SupportedLanguage) -> UnifiedAgentResponse:
        """最終応答の整形"""
        # 感情タグの抽出ロジック（LLMがタグを正しく生成した前提）
        emotion_match = re.search(r'\[(happy|sad|relaxed|apologetic|technical|guiding)\]', response_text.lower())
        emotion = emotion_match.group(1) if emotion_match else 'relaxed'
        
        # ソースと処理情報の決定
        sources = ['enhanced_rag'] if is_enhanced_rag else ['knowledge_base']
        
        return create_unified_response(
            response_text, emotion, 'FacilityAgent', language,
            {
                'confidence': 0.85,
                'category': 'facilities',
                'requestType': request_type,
                'sources': sources,
                'processingInfo': {
                    'filtered': bool(request_type),
                    'enhancedRag': is_enhanced_rag
                }
            }
        )
```

### Step 3: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
# 既存のmain_workflow.pyを修正

from backend.agents.facility_agent import FacilityAgent

class MainWorkflow:
    def __init__(self):
        self.facility_agent = FacilityAgent()
        self.graph = self._build_graph()

    async def _facility_node(self, state: WorkflowState) -> dict:
        """ファシリティノード"""

    def _route_decision(self, state: WorkflowState) -> str:
        """ルーティング決定"""
        return agent_to_node.get(routed_to, "general_knowledge")
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Pythonの依存パッケージを確認した（langchain, langgraph等）
- [ ] テスト環境を準備した

### Phase 2: ツール移行

- [ ] `enhanced_rag_search.py` を作成した
- [ ] `context_filter.py` を作成した
- [ ] 単体テストを作成・通過した

### Phase 3: FacilityAgent本体

- [ ] `facility_agent.py` を作成した
- [ ] 全メソッドを移行した
- [ ] 単体テストを作成・通過した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にFacilityAgentを統合した
- [ ] 条件付きエッジを正しく設定した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] Wifiのテストした
- [ ] 設備のテストした
- [ ] 地下施設の4種類（MTG/集中/Under/Makers）のテストした
- [ ] パフォーマンスを計測した（目標: 100ms以下）
- [ ] ログ出力を確認した

## トラブルシューティング

### よくある問題


## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)
- [元実装: facility-agent.ts](../../engineer-cafe-navigator-repo/src/mastra/agents/facility-agent.ts)
````
