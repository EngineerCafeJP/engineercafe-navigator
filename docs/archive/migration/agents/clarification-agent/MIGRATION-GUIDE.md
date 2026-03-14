# Clarification Agent - 移行ガイド

> Mastra (TypeScript) → LangGraph (Python) 移行手順

## 移行概要

### 現在の実装（Mastra/TypeScript）

```
engineer-cafe-navigator-repo/src/
├── mastra/agents/clarification-agent.ts    # 94行
└── lib/emotion-tagger.ts                   # 依存（動的インポート）
```

### 移行先（LangGraph/Python）

```
backend/
├── agents/
│   └── clarification_agent.py              # 新規作成
├── utils/
│   └── emotion_tagger.py                  # 新規作成（必要に応じて）
└── workflows/
    └── main_workflow.py                    # 既存（修正）
```

## 移行ステップ

### Step 1: 依存モジュールの移行

#### 1.1 EmotionTagger の移行

**元ファイル**: `engineer-cafe-navigator-repo/src/lib/emotion-tagger.ts`（動的インポート）

Clarification Agentでは、`EmotionTagger.addEmotionTag(message, 'surprised')` を使用して感情タグを付与しています。

```python
# backend/utils/emotion_tagger.py

def add_emotion_tag(message: str, emotion: str) -> str:
    """
    メッセージに感情タグを付与
    
    Args:
        message: 元のメッセージ
        emotion: 感情名（'surprised', 'happy', 'sad' など）
    
    Returns:
        感情タグ付きメッセージ（例: "[surprised]お手伝いさせていただきます！..."）
    """
    return f"[{emotion}]{message}"
```

**注意**: 既に他のエージェントでEmotionTaggerが実装されている場合は、それを再利用してください。

### Step 2: Clarification Agent 本体の移行

**元ファイル**: `engineer-cafe-navigator-repo/src/mastra/agents/clarification-agent.ts`

```python
# backend/agents/clarification_agent.py

from typing import TypedDict, Literal
from backend.utils.emotion_tagger import add_emotion_tag

SupportedLanguage = Literal["ja", "en"]

ClarificationCategory = Literal[
    "cafe-clarification-needed",
    "meeting-room-clarification-needed",
    "general-clarification-needed",
]

class ClarificationResult(TypedDict):
    """Clarification Agentの出力結果"""
    response: str                # 感情タグ付きテキスト
    emotion: Literal["surprised"]
    metadata: dict               # agent名, category, confidence など

class ClarificationAgent:
    """曖昧な質問の明確化を担当するエージェント"""
    
    def __init__(self):
        pass
    
    def handle_clarification(
        self,
        query: str,
        category: ClarificationCategory,
        language: SupportedLanguage
    ) -> ClarificationResult:
        """
        曖昧性解消の処理
        
        Args:
            query: ユーザーからの入力テキスト（現在は使用されないが、将来の拡張用）
            category: 曖昧性の種類
            language: 応答言語
        
        Returns:
            ClarificationResult: 感情タグ付きの応答とメタデータ
        """
        # カフェの曖昧性解消
        if category == 'cafe-clarification-needed':
            clarification_message = (
                "I'd be happy to help! Are you asking about:\n"
                "1. **Engineer Cafe** (the coworking space) - hours, facilities, usage\n"
                "2. **Saino Cafe** (the attached cafe & bar) - menu, hours, prices\n\n"
                "Please let me know which one you're interested in!"
                if language == 'en'
                else "お手伝いさせていただきます！どちらについてお聞きでしょうか：\n"
                      "1. **エンジニアカフェ**（コワーキングスペース）- 営業時間、設備、利用方法\n"
                      "2. **サイノカフェ**（併設のカフェ＆バー）- メニュー、営業時間、料金\n\n"
                      "お聞かせください！"
            )
            
            tagged_message = add_emotion_tag(clarification_message, 'surprised')
            
            return {
                "response": tagged_message,
                "emotion": "surprised",
                "metadata": {
                    "agent": "ClarificationAgent",
                    "confidence": 0.9,
                    "category": "cafe-clarification-needed",
                    "sources": ["clarification_system"]
                }
            }
        
        # 会議室の曖昧性解消
        if category == 'meeting-room-clarification-needed':
            clarification_message = (
                "I'd be happy to help! We have two types of meeting spaces:\n"
                "1. **Paid Meeting Rooms (2F)** - Private rooms with advance booking required (fees apply)\n"
                "2. **Basement Meeting Spaces (B1)** - Free open spaces for casual meetings\n\n"
                "Which one would you like to know about?"
                if language == 'en'
                else "お手伝いさせていただきます！会議スペースは2種類ございます：\n"
                      "1. **有料会議室（2階）** - 事前予約制の個室（有料）\n"
                      "2. **地下MTGスペース（地下1階）** - カジュアルな打ち合わせ用の無料スペース\n\n"
                      "どちらについてお知りになりたいですか？"
            )
            
            tagged_message = add_emotion_tag(clarification_message, 'surprised')
            
            return {
                "response": tagged_message,
                "emotion": "surprised",
                "metadata": {
                    "agent": "ClarificationAgent",
                    "confidence": 0.9,
                    "category": "meeting-room-clarification-needed",
                    "sources": ["clarification_system"]
                }
            }
        
        # デフォルトの曖昧性解消
        default_message = (
            "I'd be happy to help! Could you please provide more details about what you'd like to know?"
            if language == 'en'
            else "お手伝いさせていただきます！もう少し詳しくお聞かせいただけますか？"
        )
        
        tagged_message = add_emotion_tag(default_message, 'surprised')
        
        return {
            "response": tagged_message,
            "emotion": "surprised",
            "metadata": {
                "agent": "ClarificationAgent",
                "confidence": 0.7,
                "category": "general-clarification-needed",
                "sources": ["clarification_system"]
            }
        }
```

### Step 3: ワークフローへの統合

**修正ファイル**: `backend/workflows/main_workflow.py`

```python
# 既存のmain_workflow.pyを修正

from backend.agents.clarification_agent import ClarificationAgent

class MainWorkflow:
    def __init__(self):
        self.clarification_agent = ClarificationAgent()
        self.graph = self._build_graph()
    
    def _clarification_node(self, state: WorkflowState) -> dict:
        """明確化ノード: 曖昧なクエリを明確化"""
        query = state.get("query", "")
        language = state.get("language", "ja")
        
        # Router Agentから設定されたcategoryを取得
        category = state.get("metadata", {}).get("routing", {}).get("category", "general-clarification-needed")
        
        # categoryがclarification系でない場合はデフォルトにフォールバック
        if category not in [
            "cafe-clarification-needed",
            "meeting-room-clarification-needed",
            "general-clarification-needed"
        ]:
            category = "general-clarification-needed"
        
        # ClarificationAgentを使用
        result = self.clarification_agent.handle_clarification(
            query=query,
            category=category,
            language=language
        )
        
        return {
            "answer": result["response"],
            "emotion": result["emotion"],
            "metadata": {
                **state.get("metadata", {}),
                **result["metadata"],
                "requires_followup": True,  # ユーザーの回答待ち
                "clarification_type": category
            }
        }
```

## 移行チェックリスト

### Phase 1: 準備

- [ ] 既存のTypeScriptコードを完全に理解した
- [ ] Pythonの依存パッケージを確認した（langchain, langgraph等）
- [ ] テスト環境を準備した
- [ ] EmotionTaggerの実装状況を確認した（既存実装があるか）

### Phase 2: 依存モジュール

- [ ] `emotion_tagger.py` を作成した（または既存のものを確認した）
- [ ] `add_emotion_tag()` 関数を実装した
- [ ] 単体テストを作成・通過した」

### Phase 3: ClarificationAgent本体

- [ ] `clarification_agent.py` を作成した
- [ ] 3つのカテゴリ（cafe, meeting-room, general）の処理を実装した
- [ ] 日本語/英語の両方のメッセージを実装した
- [ ] 感情タグの付与を実装した
- [ ] 単体テストを作成・通過した

### Phase 4: ワークフロー統合

- [ ] `main_workflow.py` の `_clarification_node` を実装した
- [ ] Router Agentからのcategoryを受け取る処理を実装した
- [ ] メタデータに `requires_followup` を設定した
- [ ] エンドツーエンドテストを通過した

### Phase 5: 検証

- [ ] カフェ曖昧性解消のテスト（日本語/英語）
- [ ] 会議室曖昧性解消のテスト（日本語/英語）
- [ ] デフォルト曖昧性解消のテスト（日本語/英語）
- [ ] 感情タグが正しく付与されることを確認した
- [ ] メタデータが正しく設定されることを確認した

## トラブルシューティング

### よくある問題

| 問題 | 原因 | 解決策 |
|-----|------|-------|
| categoryが正しく取得できない | メタデータのパスが間違っている | `state["metadata"]["routing"]["category"]` のパスを確認 |
| 感情タグが付与されない | `add_emotion_tag()` が未実装 | `emotion_tagger.py` を確認・実装 |
| メッセージが表示されない | ワークフローのエッジ設定が不正 | `main_workflow.py` のエッジ定義を確認 |
| 日本語メッセージが文字化け | エンコーディングの問題 | UTF-8で保存されているか確認 |

## 実装のポイント

### 1. シンプルな実装

Clarification Agentは非常にシンプルな実装です。LLMを使用せず、固定メッセージを返すだけです。これにより：
- 高速な応答（LLM呼び出し不要）
- 一貫性のある応答
- 低コスト

### 2. 感情タグの統一

すべての応答に `[surprised]` タグを付与します。これは「えっ、どちらですか？」というニュアンスを表現するためです。

### 3. メタデータの設定

`requires_followup: True` を設定することで、ワークフローがユーザーの回答を待つことを示します。

### 4. ユーザー回答後の処理

ユーザーが選択肢に回答した後は、Router Agentが再度ルーティングを行い、適切なエージェント（BusinessInfoAgent等）に転送されます。

## 参考リンク

- [LangGraph ドキュメント](https://langchain-ai.github.io/langgraph/)
- [Mastra ドキュメント](https://mastra.dev)
- [元実装: clarification-agent.ts](../../engineer-cafe-navigator-repo/src/mastra/agents/clarification-agent.ts)
- [技術仕様書: SPEC.md](./SPEC.md)
- [README: README.md](./README.md)
