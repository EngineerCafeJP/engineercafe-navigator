# MemoryAgent 完全実装ガイド

> 専門エンジニア（takegg0311）向けの完全実装手順書

## 現在の状態

✅ **骨組み完了（2025-01-12）**
- `backend/utils/memory_interface.py` - Protocolインターフェース定義
- `backend/utils/memory_helper.py` - SimplifiedMemoryHelper暫定実装
- `backend/utils/checkpointer.py` - Checkpointer基盤（langgraph-checkpoint-postgres）
- `backend/agents/memory_agent.py` - MemoryAgent骨組み
- `backend/workflows/main_workflow.py` - _memory_node()更新

⏳ **未完了（完全実装が必要）**
- SimplifiedMemoryHelperの完全実装
- MemoryAgentのロジック実装
- OpenRouter API統合
- テストケース作成
- Checkpointerテーブルマイグレーション

---

## 実装の前提条件

### 必須環境変数

```bash
# Supabase接続情報
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key
SUPABASE_DB_URI=postgresql://postgres:password@host:port/database

# OpenRouter API
OPENROUTER_API_KEY=your-openrouter-api-key
```

### 必須パッケージ

```bash
# requirements.txtに追加
langgraph-checkpoint-postgres>=1.0.0
supabase>=2.0.0
httpx>=0.24.0  # OpenRouter API用
```

### データベーススキーマ

既存の`agent_memory`テーブルを使用（マイグレーション済み）:

```sql
-- backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql
CREATE TABLE IF NOT EXISTS agent_memory (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  agent_name varchar(100) NOT NULL,
  key varchar(255) NOT NULL,
  value jsonb NOT NULL,
  expires_at timestamp with time zone,
  created_at timestamp with time zone DEFAULT now(),
  updated_at timestamp with time zone DEFAULT now(),
  UNIQUE(agent_name, key)
);
```

---

## 実装手順

### Step 1: SimplifiedMemoryHelper完全実装

#### 1.1 Supabaseクライアント初期化

`backend/utils/memory_helper.py` の`__init__()`を完全実装:

```python
def __init__(self):
    """初期化"""
    from supabase import create_client, Client

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")

    self.supabase: Client = create_client(supabase_url, supabase_key)
    self.agent_name = "langgraph_memory"
    self.ttl_seconds = 180  # 3 minutes
    self.max_entries = 100

    logger.info(f"SimplifiedMemoryHelper initialized with TTL={self.ttl_seconds}s")
```

#### 1.2 メッセージ保存の実装

`store_message()`を完全実装:

```python
async def store_message(
    self,
    role: str,
    content: str,
    session_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """メッセージを保存"""
    timestamp = int(datetime.now().timestamp() * 1000)  # ミリ秒
    metadata = metadata or {}

    # リクエストタイプの自動抽出
    if role == "user" and "request_type" not in metadata:
        metadata["request_type"] = self._extract_request_type(content)

    message_data = {
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "session_id": session_id,
        **metadata,
    }

    # TTL設定
    expires_at = (datetime.now() + timedelta(seconds=self.ttl_seconds)).isoformat()

    # Supabaseに保存
    result = self.supabase.table("agent_memory").insert({
        "agent_name": self.agent_name,
        "key": f"message_{timestamp}",
        "value": message_data,
        "expires_at": expires_at,
    }).execute()

    logger.info(f"Stored {role} message with 3-minute TTL: {result.data}")
```

#### 1.3 コンテキスト取得の実装

`get_context()`を完全実装:

```python
async def get_context(
    self, query: str, session_id: str, options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """会話コンテキストを取得"""
    options = options or {}
    include_knowledge_base = options.get("include_knowledge_base", True)
    language = options.get("language", "ja")
    inherit_context = options.get("inherit_context", True)

    # 1. Recent messagesを取得（3分以内）
    current_time = datetime.now().isoformat()
    result = self.supabase.table("agent_memory") \
        .select("*") \
        .eq("agent_name", self.agent_name) \
        .like("key", "message_%") \
        .gt("expires_at", current_time) \
        .order("created_at", desc=False) \
        .execute()

    recent_messages = [
        {
            "role": item["value"]["role"],
            "content": item["value"]["content"],
            "metadata": {
                "emotion": item["value"].get("emotion"),
                "session_id": item["value"].get("session_id"),
                "request_type": item["value"].get("request_type"),
                "timestamp": item["value"].get("timestamp"),
            },
        }
        for item in result.data
        if item["value"].get("session_id") == session_id  # session_idでフィルタ
    ]

    # 2. コンテキスト継承
    inherited_request_type = None
    if inherit_context:
        inherited_request_type = await self.get_previous_request_type(session_id)

    # 3. ナレッジベース検索（TODO: RAGツール統合）
    knowledge_results = []
    if include_knowledge_base and query.strip():
        # TODO: RAGツールとの統合
        pass

    # 4. コンテキスト文字列のフォーマット
    context_string = self._build_comprehensive_context(
        recent_messages, knowledge_results, language
    )

    return {
        "recent_messages": recent_messages,
        "knowledge_results": knowledge_results,
        "context_string": context_string,
        "inherited_request_type": inherited_request_type,
    }
```

#### 1.4 前回リクエストタイプ取得の実装

`get_previous_request_type()`を完全実装:

```python
async def get_previous_request_type(self, session_id: str) -> Optional[str]:
    """前回のリクエストタイプを取得"""
    current_time = datetime.now().isoformat()
    result = self.supabase.table("agent_memory") \
        .select("*") \
        .eq("agent_name", self.agent_name) \
        .like("key", "message_%") \
        .gt("expires_at", current_time) \
        .order("created_at", desc=True) \
        .execute()

    # 最新のuser messageを探す
    for item in result.data:
        msg = item["value"]
        if msg.get("role") == "user" and msg.get("session_id") == session_id:
            request_type = msg.get("request_type")
            if request_type:
                logger.info(f"Found previous request type: {request_type}")
                return request_type

    return None
```

---

### Step 2: MemoryAgent完全実装

#### 2.1 OpenRouter API統合

`backend/agents/memory_agent.py`の`__init__()`を更新:

```python
def __init__(self, memory_system: Optional[MemorySystemInterface] = None):
    """初期化"""
    from backend.llm.openrouter import OpenRouterProvider
    from backend.llm.models import get_model_config

    self.memory_system = memory_system
    self.provider = OpenRouterProvider()
    self.config = get_model_config("qa_response")

    logger.info(f"MemoryAgent initialized with OpenRouter")
```

#### 2.2 メモリ関連質問判定の実装

`detect_memory_query_type()`を完全実装:

```python
def detect_memory_query_type(self, query: str) -> str:
    """メモリ関連質問のタイプを判定"""
    lower_query = query.lower()

    # 質問履歴
    question_keywords = [
        "何を聞いた", "質問した", "どんな質問", "聞いたこと",
        "what did i ask", "what i asked", "my question"
    ]
    if any(keyword in lower_query for keyword in question_keywords):
        return "question_history"

    # 回答履歴
    answer_keywords = [
        "答え", "回答", "返事", "応答",
        "answer", "response", "replied", "told me"
    ]
    if any(keyword in lower_query for keyword in answer_keywords):
        return "answer_history"

    # もう一つ系
    other_option_keywords = [
        "もう一つの方", "もう一つ", "別の方", "もう片方",
        "the other one", "the other", "alternative"
    ]
    if any(keyword in lower_query for keyword in other_option_keywords):
        return "other_option"

    return "general_memory"
```

#### 2.3 プロンプト構築の実装

`build_memory_prompt()`を完全実装:

```python
def build_memory_prompt(
    self,
    query: str,
    context: Dict[str, Any],
    query_type: str,
    language: str = "ja",
) -> str:
    """メモリコンテキストからプロンプトを構築"""

    # 質問タイプ別のテンプレート
    templates = {
        "question_history": {
            "ja": "以下の会話履歴から、ユーザーが前に何を質問したか答えてください。\n\n{context}\n\nユーザーの質問: {query}\n",
            "en": "Based on the conversation history below, answer what the user asked before.\n\n{context}\n\nUser question: {query}\n"
        },
        "answer_history": {
            "ja": "以下の会話履歴から、前回の回答内容を教えてください。\n\n{context}\n\nユーザーの質問: {query}\n",
            "en": "Based on the conversation history below, tell me the previous answer.\n\n{context}\n\nUser question: {query}\n"
        },
        "other_option": {
            "ja": "以下の会話履歴から、「もう一つの選択肢」について補足情報を提供してください。\n\n{context}\n\nユーザーの質問: {query}\n",
            "en": "Based on the conversation history below, provide additional information about \"the other option\".\n\n{context}\n\nUser question: {query}\n"
        },
        "general_memory": {
            "ja": "以下の会話履歴を参考に、ユーザーの質問に答えてください。\n\n{context}\n\nユーザーの質問: {query}\n",
            "en": "Based on the conversation history below, answer the user's question.\n\n{context}\n\nUser question: {query}\n"
        }
    }

    template = templates.get(query_type, templates["general_memory"])[language]
    return template.format(
        context=context.get("context_string", ""),
        query=query
    )
```

#### 2.4 回答生成の実装

`generate_response()`を完全実装:

```python
async def generate_response(self, prompt: str) -> str:
    """OpenRouter APIで回答を生成"""
    try:
        response = await self.provider.generate(
            model=self.config["model"],
            prompt=prompt,
            temperature=self.config.get("temperature", 0.7),
            max_tokens=self.config.get("max_tokens", 500),
        )
        return response["text"]
    except Exception as e:
        logger.error(f"Failed to generate response: {e}")
        return "申し訳ございません。回答を生成できませんでした。"
```

#### 2.5 完全なprocess_memory_query実装

`process_memory_query()`を完全実装:

```python
async def process_memory_query(
    self, query: str, session_id: str, language: str = "ja"
) -> Dict[str, Any]:
    """メモリ関連のクエリを処理"""

    # メモリシステムチェック
    if not self.memory_system:
        return self._handle_no_memory_system(language)

    # 質問タイプ判定
    query_type = self.detect_memory_query_type(query)
    logger.info(f"Detected query type: {query_type}")

    # 会話履歴取得
    context = await self.memory_system.get_context(
        query=query,
        session_id=session_id,
        options={"language": language, "include_knowledge_base": False}
    )

    # 履歴なしの場合
    if not context["recent_messages"]:
        return self._no_history_response(language)

    # プロンプト構築
    prompt = self.build_memory_prompt(query, context, query_type, language)

    # 回答生成
    answer = await self.generate_response(prompt)

    # 感情タグ決定
    emotion = self._determine_emotion(context, query_type)

    return {
        "answer": answer,
        "emotion": emotion,
        "metadata": {
            "agent": "MemoryAgent",
            "query_type": query_type,
            "context_messages_count": len(context["recent_messages"]),
        },
    }
```

---

### Step 3: Checkpointer基盤完全実装

#### 3.1 langgraph-checkpoint-postgres統合

`backend/utils/checkpointer.py`の`create_checkpointer()`を完全実装:

```python
def create_checkpointer() -> PostgresSaver:
    """Checkpointerを作成"""
    from langgraph.checkpoint.postgres import PostgresSaver

    db_uri = os.getenv("SUPABASE_DB_URI")
    if not db_uri:
        raise ValueError("SUPABASE_DB_URI is required")

    try:
        checkpointer = PostgresSaver.from_conn_string(db_uri)
        checkpointer.setup()  # テーブル初期化
        logger.info("PostgresSaver created successfully")
        return checkpointer
    except Exception as e:
        logger.error(f"Failed to create PostgresSaver: {e}")
        raise ConnectionError(f"Failed to connect to PostgreSQL: {e}")
```

#### 3.2 main_workflow.pyへの統合

`backend/workflows/main_workflow.py`の`_memory_node()`を完全実装:

```python
async def _memory_node(self, state: WorkflowState) -> dict:
    """メモリノード: 会話履歴とコンテキストを取得"""
    from backend.utils.memory_helper import get_memory_helper

    memory_helper = get_memory_helper()
    session_id = state.get("session_id", "")
    query = state.get("query", "")
    language = state.get("language", "ja")

    try:
        memory_context = await memory_helper.get_context(
            query=query,
            session_id=session_id,
            options={
                "include_knowledge_base": False,
                "language": language,
                "inherit_context": True
            }
        )

        return {
            "context": {
                **state.get("context", {}),
                "memory": memory_context
            }
        }
    except Exception as e:
        logger.error(f"Memory node error: {e}")
        return {"context": {**state.get("context", {}), "memory": {}}}
```

---

### Step 4: テストケース作成

#### 4.1 SimplifiedMemoryHelperのテスト

`backend/tests/test_memory_helper.py`を作成:

```python
import pytest
from backend.utils.memory_helper import SimplifiedMemoryHelper

@pytest.mark.asyncio
async def test_store_and_retrieve_message():
    """メッセージの保存と取得"""
    helper = SimplifiedMemoryHelper()

    # メッセージ保存
    await helper.store_message(
        role="user",
        content="エンジニアカフェの営業時間は？",
        session_id="test_session",
        metadata={"emotion": "curious"}
    )

    # コンテキスト取得
    context = await helper.get_context(
        query="さっき何を聞いた？",
        session_id="test_session",
        options={"language": "ja"}
    )

    assert len(context["recent_messages"]) > 0
    assert context["recent_messages"][0]["content"] == "エンジニアカフェの営業時間は？"

@pytest.mark.asyncio
async def test_request_type_extraction():
    """リクエストタイプの自動抽出"""
    helper = SimplifiedMemoryHelper()

    # 営業時間系
    request_type = helper._extract_request_type("営業時間は？")
    assert request_type == "hours"

    # 料金系
    request_type = helper._extract_request_type("料金はいくらですか？")
    assert request_type == "price"
```

#### 4.2 MemoryAgentのテスト

`backend/tests/test_memory_agent.py`を作成:

```python
import pytest
from backend.agents.memory_agent import MemoryAgent
from backend.utils.memory_helper import SimplifiedMemoryHelper

@pytest.mark.asyncio
async def test_memory_agent_question_history():
    """質問履歴への質問処理"""
    memory_helper = SimplifiedMemoryHelper()
    agent = MemoryAgent(memory_system=memory_helper)

    # 会話履歴を作成
    await memory_helper.store_message(
        "user", "エンジニアカフェの営業時間は？", "test_session"
    )
    await memory_helper.store_message(
        "assistant", "9:00〜22:00です。", "test_session"
    )

    # メモリ関連質問
    result = await agent.process_memory_query(
        query="さっき何を聞いた？",
        session_id="test_session",
        language="ja"
    )

    assert result["emotion"] == "relaxed"
    assert "営業時間" in result["answer"]
```

---

### Step 5: CI/CD確認

```bash
# Ruff
cd backend
ruff check .

# Black
black --check .

# Pytest
pytest tests/ -v
```

---

## 完了チェックリスト

- [ ] SimplifiedMemoryHelper完全実装
  - [ ] Supabaseクライアント初期化
  - [ ] store_message()完全実装
  - [ ] get_context()完全実装
  - [ ] get_previous_request_type()完全実装
- [ ] MemoryAgent完全実装
  - [ ] OpenRouter API統合
  - [ ] detect_memory_query_type()完全実装
  - [ ] build_memory_prompt()完全実装
  - [ ] generate_response()完全実装
  - [ ] process_memory_query()完全実装
- [ ] Checkpointer基盤完全実装
  - [ ] langgraph-checkpoint-postgres統合
  - [ ] main_workflow.pyへの統合
- [ ] テストケース作成
  - [ ] test_memory_helper.py
  - [ ] test_memory_agent.py
- [ ] CI/CDオールグリーン
  - [ ] Ruff
  - [ ] Black
  - [ ] Pytest

---

## 参考リンク

- [MemoryAgent仕様](./README.md)
- [フロントエンド実装](../../../frontend/src/lib/simplified-memory.ts)
- [LangGraph Persistence](../../../langgraph-reference/docs/docs/concepts/persistence.md)
- [Supabase テーブルスキーマ](../../../backend/supabase/migrations/20250529005253_init_engineer_cafe_navigator.sql)

---

## サポート

質問がある場合は、以下のドキュメントを参照するか、チームに相談してください:

- テリスケ（統括）
- YukitoLyn（サポート）
- Natsumi（サポート）
- Jun（サポート）
