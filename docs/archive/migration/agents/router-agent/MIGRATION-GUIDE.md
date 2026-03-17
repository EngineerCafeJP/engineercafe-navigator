# Router Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
engineer-cafe-navigator-repo/src/
├── mastra/agents/router-agent.ts    # 290行
├── lib/query-classifier.ts          # 455行
└── lib/language-processor.ts        # 196行
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── router_agent.py              # 新規作成
├── utils/
│   ├── query_classifier.py          # 新規作成
│   └── language_processor.py        # 新規作成
└── workflows/
    └── main_workflow.py             # 既存（修正）
```

## 移行ステップ

### Step 1: 依存モジュールの移行

#### 1.1 LanguageProcessor の移行

**元ファイル**: `src/lib/language-processor.ts`

```python
# backend/utils/language_processor.py

from typing import TypedDict, Literal
import re

SupportedLanguage = Literal["ja", "en"]

class LanguageDetectionResult(TypedDict):
    detected_language: SupportedLanguage
    confidence: float
    is_mixed: bool
    languages: dict | None

class LanguageProcessor:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def detect_language(self, text: str) -> LanguageDetectionResult:
        """クエリの言語を検出"""
        normalized_text = text.lower()

        # 日本語文字のパターン
        japanese_pattern = re.compile(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9faf]')
        has_japanese = bool(japanese_pattern.search(text))

        # 英語の一般的な単語
        english_words = [
            'what', 'where', 'when', 'how', 'why', 'is', 'are', 'the',
            'engineer', 'cafe', 'about', 'tell', 'me', 'please', 'hours'
        ]
        english_word_count = sum(1 for word in english_words if word in normalized_text)

        # 日本語の助詞・文末表現
        japanese_particles = ['は', 'が', 'を', 'に', 'で', 'の', 'か', 'です', 'ます']
        has_japanese_particles = any(p in text for p in japanese_particles)

        # 混合言語の検出
        has_latin = bool(re.search(r'[a-zA-Z]', text))
        is_mixed = has_japanese and has_latin

        # 判定ロジック
        if has_japanese and (has_japanese_particles or not has_latin):
            return {
                "detected_language": "ja",
                "confidence": 0.9 if has_japanese_particles else 0.7,
                "is_mixed": is_mixed,
                "languages": {"primary": "ja", "secondary": "en"} if is_mixed else {"primary": "ja"}
            }
        elif not has_japanese and english_word_count >= 2:
            return {
                "detected_language": "en",
                "confidence": 0.9,
                "is_mixed": False,
                "languages": {"primary": "en"}
            }

        # デフォルト
        return {
            "detected_language": "ja",
            "confidence": 0.5,
            "is_mixed": False,
            "languages": {"primary": "ja"}
        }

    def determine_response_language(
        self,
        query_language: LanguageDetectionResult,
        force_language: SupportedLanguage | None = None
    ) -> SupportedLanguage:
        """応答言語を決定"""
        if force_language:
            return force_language
        return query_language["detected_language"]
```

#### 1.2 QueryClassifier の移行

**元ファイル**: `src/lib/query-classifier.ts`

```python
# backend/utils/query_classifier.py

from typing import TypedDict
import re

class QueryClassificationResult(TypedDict):
    category: str
    confidence: float
    debug_info: dict | None

class QueryClassifier:
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

    def classify(self, question: str, conversation_context: dict | None = None) -> str:
        """クエリを分類（カテゴリのみ返す）"""
        result = self.classify_with_details(question, conversation_context)
        return result["category"]

    def classify_with_details(
        self,
        question: str,
        conversation_context: dict | None = None
    ) -> QueryClassificationResult:
        """詳細情報付きでクエリを分類"""
        normalized = self._normalize_query(question)
        lower_question = normalized.lower()

        # 現在時刻チェック（最優先）
        if self._is_current_time_query(normalized):
            return {
                "category": "current-time",
                "confidence": 1.0,
                "debug_info": {"reason": "Current time keywords detected"}
            }

        # カレンダー/イベント
        if self._is_calendar_query(normalized):
            return {
                "category": "calendar",
                "confidence": 0.9,
                "debug_info": {"reason": "Calendar/event keywords detected"}
            }

        # エンジニアカフェ特定
        if self._is_engineer_cafe_specific(normalized):
            return {
                "category": "facility-info",
                "confidence": 1.0,
                "debug_info": {"reason": "Engineer Cafe specific"}
            }

        # Sainoカフェ
        if self._is_saino_cafe_query(normalized):
            return {
                "category": "saino-cafe",
                "confidence": 0.9,
                "debug_info": {"reason": "Saino cafe detected"}
            }

        # カフェ曖昧性チェック
        cafe_check = self._check_cafe_ambiguity(normalized, conversation_context)
        if cafe_check.get("needs_clarification"):
            return {
                "category": cafe_check["category"],
                "confidence": cafe_check["confidence"],
                "debug_info": cafe_check.get("debug_info")
            }
        if cafe_check.get("category"):
            return {
                "category": cafe_check["category"],
                "confidence": cafe_check["confidence"],
                "debug_info": cafe_check.get("debug_info")
            }

        # 施設情報
        if self._is_facility_query(normalized):
            return {
                "category": "facility-info",
                "confidence": 0.8,
                "debug_info": {"reason": "Facility keywords detected"}
            }

        # デフォルト
        return {
            "category": "general",
            "confidence": 0.5,
            "debug_info": {"reason": "No specific category matched"}
        }

    def _normalize_query(self, query: str) -> str:
        """クエリを正規化"""
        normalized = query.lower()
        replacements = [
            ('coffee say no', 'saino cafe'),
            ('才能', 'saino'),
            ('say no', 'saino'),
            ('セイノ', 'saino'),
            ('サイノ', 'saino'),
        ]
        for old, new in replacements:
            normalized = normalized.replace(old, new)

        # 文頭のフィラー除去
        normalized = re.sub(r'^(じゃあ|じゃ|では|それでは|えっと|えーと|あの|その)\s*', '', normalized)
        normalized = re.sub(r'^(well|then|so|um|uh)\s*', '', normalized, flags=re.IGNORECASE)

        return normalized.strip()

    # ... 他のヘルパーメソッドも同様に移行
```

### Step 2: Router Agent 本体の移行

**元ファイル**: `src/mastra/agents/router-agent.ts`

```python
# backend/agents/router_agent.py

from typing import TypedDict, Literal
from backend.utils.query_classifier import QueryClassifier
from backend.utils.language_processor import LanguageProcessor, SupportedLanguage

class RouteResult(TypedDict):
    agent: str
    category: str
    request_type: str | None
    language: SupportedLanguage
    confidence: float
    debug_info: dict

class RouterAgent:
    def __init__(self):
        self.query_classifier = QueryClassifier()
        self.language_processor = LanguageProcessor()

    async def route_query(self, query: str, session_id: str) -> RouteResult:
        """メインルーティング処理"""
        # 言語検出
        language_result = self.language_processor.detect_language(query)
        response_language = self.language_processor.determine_response_language(language_result)

        # メモリ関連チェック
        if self._is_memory_related_question(query):
            return {
                "agent": "MemoryAgent",
                "category": "memory",
                "request_type": None,
                "language": response_language,
                "confidence": 1.0,
                "debug_info": {
                    "language_detection": language_result,
                    "classification": {"reason": "Memory-related question detected"}
                }
            }

        # クエリ分類
        classification = self.query_classifier.classify_with_details(query)

        # リクエストタイプ抽出
        request_type = self._extract_request_type(query)

        # 文脈依存クエリの処理
        if self._is_context_dependent_query(query) and not request_type:
            # TODO: メモリシステムから前回のrequest_typeを取得
            pass

        # エージェント選択
        selected_agent = self._select_agent(
            classification["category"],
            request_type,
            query
        )

        return {
            "agent": selected_agent,
            "category": classification["category"],
            "request_type": request_type,
            "language": response_language,
            "confidence": classification["confidence"],
            "debug_info": {
                "language_detection": language_result,
                "classification": classification.get("debug_info")
            }
        }

    def _select_agent(
        self,
        category: str,
        request_type: str | None,
        query: str | None = None
    ) -> str:
        """エージェント選択ロジック"""
        # 文脈依存クエリの処理
        if query and self._is_context_dependent_query(query):
            lower_query = query.lower()
            if 'saino' in lower_query:
                return "BusinessInfoAgent"
            if any(kw in lower_query for kw in ['土曜', '日曜', '平日']):
                return "BusinessInfoAgent"

        # 曖昧性解消が必要な場合
        if category in ['cafe-clarification-needed', 'meeting-room-clarification-needed']:
            return "ClarificationAgent"

        # request_typeに基づくルーティング
        if request_type:
            if request_type in ['price', 'hours', 'location']:
                return "BusinessInfoAgent"
            if request_type in ['wifi', 'facility', 'basement']:
                return "FacilityAgent"
            if request_type == 'event':
                return "EventAgent"

        # カテゴリマッピング
        agent_map = {
            'facility-info': "BusinessInfoAgent",
            'saino-cafe': "BusinessInfoAgent",
            'calendar': "EventAgent",
            'events': "EventAgent",
            'current-time': "TimeAgent",
            'general': "GeneralKnowledgeAgent",
            'memory': "MemoryAgent",
        }

        return agent_map.get(category, "GeneralKnowledgeAgent")

    def _extract_request_type(self, query: str) -> str | None:
        """リクエストタイプを抽出"""
        lower_question = query.lower()

        # Wi-Fi関連
        if any(kw in lower_question for kw in ['wi-fi', 'wifi', 'インターネット', 'ネット']):
            return 'wifi'

        # 営業時間関連
        if any(kw in lower_question for kw in ['営業時間', 'hours', '何時まで', '何時から', '開いて', 'open']):
            return 'hours'

        # 料金関連
        if any(kw in lower_question for kw in ['料金', 'price', 'いくら', '値段', 'cost']):
            return 'price'

        # 場所関連
        if any(kw in lower_question for kw in ['場所', 'location', 'どこ', 'where', 'アクセス']):
            return 'location'

        # 地下施設関連
        if any(kw in lower_question for kw in ['地下', 'basement', 'b1', 'mtgスペース', '集中スペース']):
            return 'basement'

        # イベント関連
        if any(kw in lower_question for kw in ['イベント', 'event', '勉強会', 'セミナー']):
            return 'event'

        return None

    def _is_memory_related_question(self, question: str) -> bool:
        """メモリ関連の質問かどうか判定"""
        lower_question = question.lower()

        # ビジネス関連は除外
        business_keywords = ['メニュー', 'menu', '料金', 'price', '営業時間', 'hours',
                           '場所', 'location', '設備', 'facility', 'saino']
        if any(kw in lower_question for kw in business_keywords):
            return False

        # メモリ関連キーワード
        memory_keywords = [
            # 日本語
            'さっき', '前に', '覚えて', '記憶', '質問', '聞いた', '話した',
            'どんな', '何を', '言った', '会話', '履歴', '先ほど',
            # 英語
            'remember', 'recall', 'earlier', 'before', 'previous', 'asked',
            'said', 'mentioned', 'conversation', 'history'
        ]

        return any(kw in lower_question for kw in memory_keywords)

    def _is_context_dependent_query(self, question: str) -> bool:
        """文脈依存クエリかどうか判定"""
        import re
        trimmed = question.strip()

        context_patterns = [
            r'^土曜[日]?[はも].*',
            r'^日曜[日]?[はも].*',
            r'^平日[はも].*',
            r'^saino[のは方も]?.*',
            r'^そっち[のはも]?.*',
            r'^あっち[のはも]?.*',
        ]

        return any(re.match(pattern, trimmed) for pattern in context_patterns)
```

### Step 3: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
# 既存のmain_workflow.pyを修正

from backend.agents.router_agent import RouterAgent

class MainWorkflow:
    def __init__(self):
        self.router_agent = RouterAgent()
        self.graph = self._build_graph()

    async def _router_node(self, state: WorkflowState) -> dict:
        """ルーターノード"""
        query = state.get("query", "")
        session_id = state.get("session_id", "")

        # RouterAgentを使用
        route_result = await self.router_agent.route_query(query, session_id)

        return {
            "routed_to": route_result["agent"],
            "language": route_result["language"],
            "metadata": {
                **state.get("metadata", {}),
                "routing": {
                    "agent": route_result["agent"],
                    "category": route_result["category"],
                    "request_type": route_result["request_type"],
                    "confidence": route_result["confidence"]
                }
            }
        }

    def _route_decision(self, state: WorkflowState) -> str:
        """ルーティング決定"""
        routed_to = state.get("routed_to", "GeneralKnowledgeAgent")

        # エージェント名をノード名にマッピング
        agent_to_node = {
            "BusinessInfoAgent": "business_info",
            "FacilityAgent": "facility",
            "EventAgent": "event",
            "MemoryAgent": "memory",
            "GeneralKnowledgeAgent": "general_knowledge",
            "ClarificationAgent": "clarification",
            "TimeAgent": "time",
        }

        return agent_to_node.get(routed_to, "general_knowledge")
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Pythonの依存パッケージを確認した（langchain, langgraph等）
- [ ] テスト環境を準備した

### Phase 2: 依存モジュール

- [ ] `language_processor.py` を作成した
- [ ] `query_classifier.py` を作成した
- [ ] 単体テストを作成・通過した

### Phase 3: RouterAgent本体

- [ ] `router_agent.py` を作成した
- [ ] 全メソッドを移行した
- [ ] 単体テストを作成・通過した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` にRouterAgentを統合した
- [ ] 条件付きエッジを正しく設定した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] 全ルーティングパターンをテストした
- [ ] パフォーマンスを計測した（目標: 100ms以下）
- [ ] ログ出力を確認した

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| 日本語が正しく検出されない | 正規表現のエンコーディング | `re.compile(r'[\u3040-\u309f]')` を使用 |
| async/await エラー | 非同期処理の不整合 | 全ての呼び出し元を確認 |
| ルーティング先が不正 | エージェント名のタイポ | 定数を使用して定義 |

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)
- [元実装: router-agent.ts](../../engineer-cafe-navigator-repo/src/mastra/agents/router-agent.ts)
