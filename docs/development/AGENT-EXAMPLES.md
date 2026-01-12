# エージェント実装例とパターン集

本ドキュメントでは、エンジニアカフェナビゲーターのエージェント実装の実例とベストプラクティスを紹介します。

## 目次

1. [完全実装済みエージェントの例](#完全実装済みエージェントの例)
   - [BusinessInfoAgent - RAG検索を利用した営業情報エージェント](#businessinfoagent---rag検索を利用した営業情報エージェント)
   - [EventAgent - 外部API連携のイベント情報エージェント](#eventagent---外部api連携のイベント情報エージェント)
   - [FacilityAgent - カテゴリマッピングを活用した施設情報エージェント](#facilityagent---カテゴリマッピングを活用した施設情報エージェント)
2. [実装パターン集](#実装パターン集)
   - [RAG検索の実装パターン](#rag検索の実装パターン)
   - [LLMプロンプト構築パターン](#llmプロンプト構築パターン)
   - [エラーハンドリングパターン](#エラーハンドリングパターン)
   - [テストパターン](#テストパターン)
3. [よくある実装ミスと修正例](#よくある実装ミスと修正例)

---

## 完全実装済みエージェントの例

### BusinessInfoAgent - RAG検索を利用した営業情報エージェント

**概要:** 営業時間、料金、場所に関する質問にRAG検索とLLMを組み合わせて回答するエージェント。

**実装ファイル:** `backend/agents/business_info_agent.py`

#### 主要な実装ポイント

1. **RAG検索の統合**
   - `EnhancedRAGSearch`を使用してナレッジベースを検索
   - リクエストタイプをRAGカテゴリにマッピング
   - `include_advice=True`で実用的なアドバイスを含める

2. **LLM応答生成**
   - RAG検索結果をコンテキストとしてLLMに渡す
   - プロンプトで感情タグの埋め込みを指示
   - モデル設定は`get_model_config("facility_info")`を使用

3. **エラーハンドリング**
   - RAG検索失敗時はデフォルト応答を返す
   - LLM生成エラー時もフォールバック
   - すべてのエラーはログに記録

#### コード例: 核となるクエリ処理ロジック

```python
async def answer_business_query(
    self,
    query: str,
    request_type: Optional[str] = None,
    language: str = "ja",
    session_id: Optional[str] = None,
) -> Dict:
    """
    営業情報クエリに回答

    Args:
        query: ユーザークエリ
        request_type: リクエストタイプ（hours, price, location）
        language: 言語（ja or en）
        session_id: セッションID

    Returns:
        回答辞書 {answer, emotion, metadata}
    """
    # 1. リクエストタイプをRAGカテゴリにマッピング
    category = self._map_request_type_to_category(request_type)

    # 2. Enhanced RAG検索
    rag_result = await self.enhanced_rag.search(
        query=query,
        category=category,
        language=language,
        include_advice=True,
        max_results=10
    )

    # 3. 検索結果のバリデーション
    if not rag_result.get("success"):
        return self._get_default_response(language, request_type)

    context = rag_result.get("data", {}).get("context", "")
    if not context:
        return self._get_default_response(language, request_type)

    # 4. プロンプト構築
    prompt = self._build_prompt(query, context, request_type, language)

    # 5. LLM応答生成
    try:
        response_text = await self.llm_provider.generate(
            messages=[{"role": "user", "content": prompt}],
            config=get_model_config("facility_info"),
        )

        emotion = self._determine_emotion(request_type, response_text)

        return {
            "answer": response_text,
            "emotion": emotion,
            "metadata": {
                "agent": "BusinessInfoAgent",
                "confidence": 0.85,
                "category": category,
                "request_type": request_type,
                "sources": ["enhanced_rag"],
            },
        }
    except Exception as e:
        print(f"[BusinessInfoAgent] LLM error: {e}")
        return self._get_default_response(language, request_type)
```

#### カテゴリマッピングの実装

```python
def _map_request_type_to_category(self, request_type: Optional[str]) -> str:
    """requestTypeをEnhanced RAGカテゴリにマッピング"""
    category_mapping = {
        "hours": "hours",
        "price": "pricing",
        "location": "location",
        "access": "location",
        "basement": "facility-info",
        "facility": "facility-info",
        "wifi": "facility-info",
    }
    return category_mapping.get(request_type or "", "general")
```

**ポイント:**
- 複数のリクエストタイプを同一カテゴリにマッピング可能
- 不明なタイプには`"general"`をデフォルトで返す
- RAGシステムのカテゴリと整合性を保つ

---

### EventAgent - 外部API連携のイベント情報エージェント

**概要:** Google Calendar APIからイベント情報を取得し、LLMで自然な応答を生成するエージェント。

**実装ファイル:** `backend/agents/event_agent.py`

#### 主要な実装ポイント

1. **外部API連携**
   - `CalendarService`でGoogle Calendar APIを抽象化
   - 時間範囲をクエリから自動抽出
   - APIレスポンスを整形してLLMに渡す

2. **時間処理**
   - "今日", "今週", "来週", "今月"を自動認識
   - デフォルトは"今週"
   - 日時フォーマットの統一

3. **フォールバック戦略**
   - イベントなし時の適切な応答
   - API失敗時のエラーハンドリング
   - ユーザーフレンドリーなメッセージ

#### コード例: イベント検索と応答生成

```python
async def answer_event_query(
    self, query: str, language: str = "ja", session_id: Optional[str] = None
) -> Dict:
    """
    イベントクエリに回答

    Args:
        query: ユーザークエリ
        language: 言語（ja or en）
        session_id: セッションID

    Returns:
        回答辞書 {answer, emotion, metadata}
    """
    # 1. クエリから時間範囲を抽出
    time_range = self.calendar_service.extract_time_range_from_query(query)

    # 2. Calendar Serviceでイベント取得
    calendar_result = await self.calendar_service.search_events(time_range)

    # 3. 取得失敗またはイベントなし時の処理
    if not calendar_result.get("success"):
        return self._get_no_events_response(language, time_range)

    events = calendar_result.get("data", {}).get("events", [])
    event_count = calendar_result.get("data", {}).get("eventCount", 0)

    if event_count == 0:
        return self._get_no_events_response(language, time_range)

    # 4. イベント情報を整形
    events_text = self._format_calendar_events(events, language)

    # 5. プロンプト構築とLLM生成
    prompt = self._build_event_prompt(query, events_text, time_range, language)

    try:
        response_text = await self.llm_provider.generate(
            messages=[{"role": "user", "content": prompt}],
            config=get_model_config("event_info"),
        )

        emotion = "happy" if event_count > 0 else "sad"

        return {
            "answer": response_text,
            "emotion": emotion,
            "metadata": {
                "agent": "EventAgent",
                "time_range": time_range,
                "event_count": event_count,
            },
        }
    except Exception as e:
        print(f"[EventAgent] LLM error: {e}")
        return self._get_no_events_response(language, time_range)
```

#### イベント整形のベストプラクティス

```python
def _format_calendar_events(self, events: list, language: str) -> str:
    """カレンダーイベントを整形"""
    if not events:
        return ""

    formatted_lines = []

    for event in events:
        title = event.get("title", "No Title")
        start = event.get("start", "")
        description = event.get("description", "")

        # 日時を整形（ISO8601 -> YYYY-MM-DD）
        start_str = start[:10] if start else "日時不明"

        if language == "en":
            event_line = f"- {title} ({start_str})"
            if description:
                event_line += f" - {description[:100]}"  # 長すぎる説明を切り詰め
        else:
            event_line = f"- {title}（{start_str}）"
            if description:
                event_line += f" - {description[:100]}"

        formatted_lines.append(event_line)

    return "\n".join(formatted_lines)
```

**ポイント:**
- LLMに渡す前にデータを整形することでトークン数を削減
- 説明文は100文字に制限して冗長さを防ぐ
- 言語に応じたフォーマットの切り替え

---

### FacilityAgent - カテゴリマッピングを活用した施設情報エージェント

**概要:** Wi-Fi、電源、地下施設など、施設に関する質問にRAG検索とクエリ拡張で回答するエージェント。

**実装ファイル:** `backend/agents/facility_agent.py`

#### 主要な実装ポイント

1. **クエリ拡張**
   - リクエストタイプに応じてキーワードを追加
   - 検索精度を向上させる
   - 言語別のキーワード管理

2. **コンテキストフィルタリング**
   - 地下施設の場合、関連情報のみに絞り込み
   - 特定施設名が含まれる段落を優先
   - ノイズの削減

3. **多段階プロンプト構築**
   - リクエストタイプに応じた指示文の変更
   - 必要な情報のみを抽出するよう指示
   - 感情タグの埋め込み

#### コード例: クエリ拡張ロジック

```python
def _enhance_query(self, query: str, request_type: Optional[str], language: str) -> str:
    """クエリ拡張ロジック"""
    # requestTypeに応じたキーワード追加
    enhancement_keywords = {
        "wifi": {
            "ja": "無料Wi-Fi インターネット 接続方法 パスワード",
            "en": "free Wi-Fi internet connection method password",
        },
        "facility": {
            "ja": "設備 電源 コンセント プリンター 利用方法",
            "en": "facilities power outlet printer usage",
        },
        "basement": {
            "ja": "地下 B1 MTGスペース 集中スペース アンダースペース Makersスペース 予約 利用方法",
            "en": "basement B1 MTG space focus space under space makers space reservation",
        },
    }

    if request_type in enhancement_keywords:
        keywords = enhancement_keywords[request_type].get(
            language, enhancement_keywords[request_type].get("ja", "")
        )
        return f"{query} {keywords}"

    return query
```

**ポイント:**
- ユーザークエリに関連キーワードを追加してRAG検索の精度を向上
- 言語別のキーワード辞書を管理
- 元のクエリは変更せず、キーワードを追加するだけ

#### コンテキストフィルタリングの実装

```python
def _filter_basement_context(self, context: str, query: str, language: str) -> str:
    """地下施設に関連するコンテキストのみに絞り込む"""
    basement_keywords_ja = [
        "MTGスペース", "ミーティングスペース", "集中スペース",
        "アンダースペース", "Makersスペース", "地下", "B1", "basement",
    ]

    basement_keywords_en = [
        "MTG space", "meeting space", "focus space",
        "under space", "makers space", "basement", "B1",
    ]

    keywords = basement_keywords_ja if language == "ja" else basement_keywords_en

    # クエリに特定の施設名が含まれているかチェック
    query_lower = query.lower()
    for keyword in keywords:
        if keyword.lower() in query_lower:
            # 該当キーワードを含む段落のみを抽出
            filtered_lines = []
            for line in context.split("\n"):
                if keyword.lower() in line.lower():
                    filtered_lines.append(line)

            if filtered_lines:
                return "\n".join(filtered_lines)

    # 特定の施設名がない場合は全地下施設情報を返す
    return context
```

**ポイント:**
- 特定施設名が質問に含まれる場合、その施設の情報のみを抽出
- コンテキストのノイズを削減してLLMの精度を向上
- フィルタリング結果が空の場合はフォールバック

---

## 実装パターン集

### RAG検索の実装パターン

#### パターン1: 基本的なRAG検索

```python
from backend.tools.enhanced_rag import EnhancedRAGSearch

class MyAgent:
    def __init__(self):
        self.enhanced_rag = EnhancedRAGSearch()

    async def search_knowledge(self, query: str) -> str:
        """ナレッジベースを検索してコンテキストを取得"""
        rag_result = await self.enhanced_rag.search(
            query=query,
            category="general",  # カテゴリを指定
            language="ja",
            include_advice=False,  # アドバイス不要な場合はFalse
            max_results=10
        )

        if not rag_result.get("success"):
            return ""

        return rag_result.get("data", {}).get("context", "")
```

#### パターン2: カテゴリマッピングを使ったRAG検索

```python
def _map_to_rag_category(self, intent: str) -> str:
    """意図からRAGカテゴリにマッピング"""
    mapping = {
        "営業時間": "hours",
        "料金": "pricing",
        "場所": "location",
        "設備": "facility-info",
    }
    return mapping.get(intent, "general")

async def search_with_intent(self, query: str, intent: str) -> str:
    """意図に基づいてRAG検索"""
    category = self._map_to_rag_category(intent)

    rag_result = await self.enhanced_rag.search(
        query=query,
        category=category,
        language="ja",
        include_advice=True,  # アドバイスを含める
        max_results=5
    )

    return rag_result.get("data", {}).get("context", "")
```

#### パターン3: include_adviceの使い分け

```python
async def search_with_practical_advice(self, query: str, need_advice: bool = True):
    """実用的なアドバイスの有無を制御したRAG検索"""
    rag_result = await self.enhanced_rag.search(
        query=query,
        category="facility-info",
        language="ja",
        include_advice=need_advice,  # ユーザーの要求に応じて制御
        max_results=10
    )

    # include_advice=Trueの場合、コンテキストに実用的なアドバイスが含まれる
    # 例: "💡 設備の利用方法がわからない場合は、スタッフにお気軽にお声がけください。"
    return rag_result.get("data", {}).get("context", "")
```

**ポイント:**
- `include_advice=True`で検索結果に実用的なアドバイスが追加される
- 営業時間、料金、施設情報などのカテゴリで有効
- アドバイスが不要な場合は`False`に設定

---

### LLMプロンプト構築パターン

#### パターン1: システムプロンプト + ユーザープロンプト

```python
def _build_prompt_with_system(self, query: str, context: str) -> List[Dict]:
    """システムプロンプトとユーザープロンプトを分けた構成"""
    system_prompt = """あなたはエンジニアカフェの案内係です。
提供された情報に基づいて、簡潔で親切な回答をしてください。
回答は必ず感情タグ（[happy], [relaxed], [sad]など）で始めてください。"""

    user_prompt = f"""質問: {query}

情報:
{context}

上記の情報を使って質問に答えてください。最大2-3文で簡潔に。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
```

#### パターン2: Few-shot プロンプト

```python
def _build_few_shot_prompt(self, query: str, context: str) -> str:
    """Few-shot学習でLLMに例を示す"""
    prompt = """以下の例を参考に、質問に答えてください。

例1:
質問: 営業時間は何時までですか？
情報: エンジニアカフェは平日9:00-22:00、土日祝10:00-20:00です。
回答: [relaxed]エンジニアカフェは平日9:00-22:00、土日祝10:00-20:00まで営業しております。

例2:
質問: 今日イベントはありますか？
情報: 本日はイベントの予定はございません。
回答: [sad]申し訳ございません。本日はイベントの予定がございません。

---

質問: {query}
情報: {context}
回答:"""
    return prompt
```

#### パターン3: 感情タグの埋め込み指示

```python
def _build_prompt_with_emotion_tag(self, query: str, context: str, language: str) -> str:
    """感情タグを確実に埋め込むよう指示"""
    if language == "en":
        return f"""Answer the question using the provided information.

Question: {query}
Information: {context}

Answer briefly (1-2 sentences) with only the relevant information.
IMPORTANT: Start your response with an emotion tag:
- [happy] for positive news or when events are available
- [relaxed] for neutral information
- [sad] for unavailable services or no events

Example: "[happy]Yes, there is a workshop today at 3 PM."
"""
    else:
        return f"""提供された情報を使って質問に答えてください。

質問: {query}
情報: {context}

関連する情報のみを簡潔に（1-2文）答えてください。
重要: 必ず感情タグで回答を始めてください:
- [happy] 良いニュースやイベントがある場合
- [relaxed] 中立的な情報提供
- [sad] サービスが利用できない、イベントがない場合

例: "[happy]はい、本日15時からワークショップがございます。"
"""
```

**ポイント:**
- 感情タグの具体例を示すことで確実に埋め込まれる
- `IMPORTANT:`で強調して優先度を高める
- Few-shotで正しい使い方を示す

---

### エラーハンドリングパターン

#### パターン1: 多段階フォールバック

```python
async def answer_with_fallback(self, query: str) -> Dict:
    """複数のフォールバックを持つ回答生成"""
    try:
        # 第1段階: RAG検索
        rag_result = await self.enhanced_rag.search(query=query, category="general")

        if not rag_result.get("success"):
            # 第2段階: デフォルト検索にフォールバック
            print("[Agent] RAG failed, trying default search...")
            context = await self._search_default_knowledge(query)
        else:
            context = rag_result.get("data", {}).get("context", "")

        if not context:
            # 第3段階: コンテキストなし応答
            print("[Agent] No context found, returning default response")
            return self._get_no_info_response()

        # 第4段階: LLM生成
        try:
            response_text = await self.llm_provider.generate(
                messages=[{"role": "user", "content": self._build_prompt(query, context)}]
            )
            return {"answer": response_text, "emotion": "helpful"}

        except Exception as llm_error:
            # 第5段階: LLM失敗時のフォールバック
            print(f"[Agent] LLM generation failed: {llm_error}")
            return self._get_llm_error_response()

    except Exception as e:
        # 最終フォールバック
        print(f"[Agent] Critical error: {e}")
        return self._get_critical_error_response()
```

#### パターン2: ログ出力のベストプラクティス

```python
import logging

logger = logging.getLogger(__name__)

async def answer_query(self, query: str) -> Dict:
    """ログ出力を含むクエリ処理"""
    logger.info(f"[{self.__class__.__name__}] Processing query: {query}")

    try:
        # 処理開始
        logger.debug(f"Searching RAG with category: {category}")
        rag_result = await self.enhanced_rag.search(query=query, category="general")

        if not rag_result.get("success"):
            logger.warning(f"RAG search failed: {rag_result.get('error', 'Unknown error')}")
            return self._get_default_response()

        logger.info(f"RAG search successful, context length: {len(context)}")

        # LLM生成
        response_text = await self.llm_provider.generate(...)
        logger.info(f"LLM response generated, length: {len(response_text)}")

        return {"answer": response_text, "emotion": "helpful"}

    except Exception as e:
        logger.error(f"Error in answer_query: {e}", exc_info=True)
        return self._get_error_response()
```

#### パターン3: カスタムエラーレスポンス

```python
def _get_default_response(self, language: str, context: str = "") -> Dict:
    """コンテキストに応じたデフォルト応答"""
    if "timeout" in context.lower():
        # タイムアウトエラー
        message = {
            "ja": "[sad]申し訳ございません。情報の取得に時間がかかっています。もう一度お試しください。",
            "en": "[sad]Sorry, retrieving information is taking longer than expected. Please try again."
        }
    elif "not found" in context.lower():
        # 情報が見つからない
        message = {
            "ja": "[sad]申し訳ございません。お探しの情報が見つかりませんでした。",
            "en": "[sad]Sorry, I couldn't find the information you're looking for."
        }
    else:
        # 一般的なエラー
        message = {
            "ja": "[sad]申し訳ございません。エラーが発生しました。スタッフにお問い合わせください。",
            "en": "[sad]Sorry, an error occurred. Please contact our staff."
        }

    return {
        "answer": message.get(language, message["ja"]),
        "emotion": "apologetic",
        "metadata": {
            "agent": self.__class__.__name__,
            "confidence": 0.3,
            "sources": ["fallback"]
        }
    }
```

**ポイント:**
- エラーの種類に応じて適切なメッセージを返す
- ユーザーフレンドリーなエラーメッセージ
- メタデータに`sources: ["fallback"]`を記録して追跡可能に

---

### テストパターン

#### パターン1: pytest fixtureを使ったエージェントテスト

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.agents.business_info_agent import BusinessInfoAgent

@pytest.fixture
def mock_enhanced_rag():
    """EnhancedRAGSearchのモック"""
    mock = AsyncMock()
    mock.search.return_value = {
        "success": True,
        "data": {
            "context": "エンジニアカフェは平日9:00-22:00まで営業しております。",
            "results": [],
            "totalResults": 1,
            "topEntity": "engineer-cafe"
        }
    }
    return mock

@pytest.fixture
def mock_llm_provider():
    """LLMプロバイダーのモック"""
    mock = AsyncMock()
    mock.generate.return_value = "[relaxed]平日は9:00-22:00まで営業しております。"
    return mock

@pytest.fixture
def agent(mock_enhanced_rag, mock_llm_provider, monkeypatch):
    """BusinessInfoAgentのインスタンス（モック注入済み）"""
    agent = BusinessInfoAgent()
    agent.enhanced_rag = mock_enhanced_rag
    agent.llm_provider = mock_llm_provider
    return agent

@pytest.mark.asyncio
async def test_answer_business_query_success(agent, mock_enhanced_rag, mock_llm_provider):
    """正常系: 営業時間クエリに回答"""
    result = await agent.answer_business_query(
        query="営業時間は？",
        request_type="hours",
        language="ja"
    )

    # RAG検索が呼ばれたことを確認
    mock_enhanced_rag.search.assert_called_once_with(
        query="営業時間は？",
        category="hours",
        language="ja",
        include_advice=True,
        max_results=10
    )

    # LLM生成が呼ばれたことを確認
    assert mock_llm_provider.generate.called

    # 結果の検証
    assert result["answer"] == "[relaxed]平日は9:00-22:00まで営業しております。"
    assert result["emotion"] == "relaxed"
    assert result["metadata"]["agent"] == "BusinessInfoAgent"
```

#### パターン2: パラメータ化テスト

```python
@pytest.mark.parametrize("request_type,expected_category", [
    ("hours", "hours"),
    ("price", "pricing"),
    ("location", "location"),
    ("access", "location"),
    ("basement", "facility-info"),
    ("wifi", "facility-info"),
    (None, "general"),
])
def test_map_request_type_to_category(request_type, expected_category):
    """リクエストタイプからカテゴリへのマッピングをテスト"""
    agent = BusinessInfoAgent()
    assert agent._map_request_type_to_category(request_type) == expected_category
```

#### パターン3: エラーケースのテスト

```python
@pytest.mark.asyncio
async def test_answer_business_query_rag_failure(agent, mock_enhanced_rag):
    """異常系: RAG検索失敗時のフォールバック"""
    # RAG検索を失敗させる
    mock_enhanced_rag.search.return_value = {"success": False, "error": "Connection error"}

    result = await agent.answer_business_query(
        query="営業時間は？",
        request_type="hours",
        language="ja"
    )

    # デフォルト応答が返されることを確認
    assert "[sad]" in result["answer"]
    assert "申し訳ございません" in result["answer"]
    assert result["emotion"] == "apologetic"
    assert result["metadata"]["confidence"] == 0.3
    assert result["metadata"]["sources"] == ["fallback"]

@pytest.mark.asyncio
async def test_answer_business_query_llm_failure(agent, mock_llm_provider):
    """異常系: LLM生成失敗時のフォールバック"""
    # LLM生成を失敗させる
    mock_llm_provider.generate.side_effect = Exception("LLM API error")

    result = await agent.answer_business_query(
        query="営業時間は？",
        request_type="hours",
        language="ja"
    )

    # デフォルト応答が返されることを確認
    assert "[sad]" in result["answer"]
    assert result["emotion"] == "apologetic"
```

**ポイント:**
- `AsyncMock`を使って非同期関数をモック
- `monkeypatch`でエージェントの依存関係を注入
- パラメータ化テストで複数のケースを網羅
- エラーケースも必ずテスト

---

## よくある実装ミスと修正例

### ミス1: RAG検索結果の処理ミス

#### 悪い例

```python
async def answer_query(self, query: str):
    rag_result = await self.enhanced_rag.search(query=query, category="general")

    # ❌ success チェックなし
    context = rag_result["data"]["context"]  # KeyErrorの可能性

    # ❌ 空のコンテキストチェックなし
    prompt = f"質問: {query}\n情報: {context}"
    response = await self.llm_provider.generate([{"role": "user", "content": prompt}])

    return {"answer": response}
```

#### 良い例

```python
async def answer_query(self, query: str):
    rag_result = await self.enhanced_rag.search(query=query, category="general")

    # ✅ successチェック
    if not rag_result.get("success"):
        print(f"[Agent] RAG search failed: {rag_result.get('error')}")
        return self._get_default_response()

    # ✅ 安全なデータ取得
    context = rag_result.get("data", {}).get("context", "")

    # ✅ 空のコンテキストチェック
    if not context:
        print("[Agent] No context found")
        return self._get_default_response()

    prompt = f"質問: {query}\n情報: {context}"

    try:
        response = await self.llm_provider.generate([{"role": "user", "content": prompt}])
        return {"answer": response, "emotion": "helpful"}
    except Exception as e:
        print(f"[Agent] LLM error: {e}")
        return self._get_default_response()
```

---

### ミス2: LLMレスポンスのパースエラー

#### 悪い例

```python
async def extract_emotion(self, response_text: str) -> str:
    # ❌ 感情タグが含まれていない場合にエラー
    emotion = response_text.split("[")[1].split("]")[0]
    return emotion
```

#### 良い例

```python
def _determine_emotion(self, response_text: str, default: str = "helpful") -> str:
    """感情タグを安全に抽出"""
    # ✅ 感情タグの存在チェック
    if "[happy]" in response_text.lower():
        return "happy"
    elif "[sad]" in response_text.lower():
        return "sad"
    elif "[relaxed]" in response_text.lower():
        return "relaxed"

    # ✅ デフォルト値を返す
    return default
```

---

### ミス3: 環境変数の取得ミス

#### 悪い例

```python
class MyAgent:
    def __init__(self):
        # ❌ 環境変数が未設定の場合にエラー
        self.api_key = os.environ["OPENAI_API_KEY"]

        # ❌ 空文字列チェックなし
        self.supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
```

#### 良い例

```python
class MyAgent:
    def __init__(self):
        # ✅ デフォルト値を設定
        self.api_key = os.getenv("OPENAI_API_KEY", "")

        # ✅ 環境変数チェック
        supabase_url = os.getenv("SUPABASE_URL", "")
        supabase_key = os.getenv("SUPABASE_KEY", "")

        if not supabase_url or not supabase_key:
            print("[Agent] Warning: Supabase credentials not configured")
            self.supabase = None
        else:
            self.supabase = create_client(supabase_url, supabase_key)

    async def search(self, query: str):
        # ✅ 初期化チェック
        if not self.supabase:
            return {"success": False, "error": "Supabase not configured"}

        # 検索処理...
```

---

### ミス4: 非同期処理の間違い

#### 悪い例

```python
class MyAgent:
    async def answer_query(self, query: str):
        # ❌ awaitを忘れた
        rag_result = self.enhanced_rag.search(query=query, category="general")
        # rag_resultはコルーチンオブジェクトのまま

        context = rag_result.get("data", {}).get("context", "")  # AttributeError
```

#### 良い例

```python
class MyAgent:
    async def answer_query(self, query: str):
        # ✅ awaitを使用
        rag_result = await self.enhanced_rag.search(query=query, category="general")

        context = rag_result.get("data", {}).get("context", "")
        # 正常に動作
```

---

### ミス5: プロンプトのトークン数オーバー

#### 悪い例

```python
def _build_prompt(self, query: str, context: str):
    # ❌ コンテキストが長すぎる場合にトークン制限超過
    return f"""
質問: {query}

情報:
{context}  # 数千文字のコンテキストをそのまま渡す

上記の情報を使って質問に答えてください。
"""
```

#### 良い例

```python
def _build_prompt(self, query: str, context: str, max_context_length: int = 2000):
    # ✅ コンテキストを制限
    if len(context) > max_context_length:
        context = context[:max_context_length] + "..."
        print(f"[Agent] Context truncated to {max_context_length} chars")

    return f"""
質問: {query}

情報:
{context}

上記の情報を使って質問に答えてください。
"""
```

---

## まとめ

本ドキュメントでは、エンジニアカフェナビゲーターの完全実装済みエージェントの実例と、実装パターン、よくあるミスを紹介しました。

### 重要なポイント

1. **RAG検索の活用**
   - カテゴリマッピングで検索精度を向上
   - `include_advice=True`で実用的なアドバイスを含める
   - 検索結果の安全な処理（successチェック、空チェック）

2. **LLMプロンプト構築**
   - 感情タグの確実な埋め込み
   - Few-shotで正しい使い方を示す
   - トークン数を意識したコンテキスト制限

3. **エラーハンドリング**
   - 多段階フォールバック戦略
   - ユーザーフレンドリーなエラーメッセージ
   - 詳細なログ出力

4. **テスト**
   - モックを使った単体テスト
   - パラメータ化テストで網羅性向上
   - エラーケースも必ずテスト

### 次のステップ

- 骨組みエージェント（VoiceAgent, CharacterControlAgent, MemoryAgent）の完全実装
- 新規エージェントの追加
- 統合テストの充実

参考にして、高品質なエージェント実装を実現してください。
