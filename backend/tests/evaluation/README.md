# LangChain Evaluations 拡張

マルチエージェントシステム向けのLLM-as-Judge評価とルーティング精度評価を提供します。

## 概要

このモジュールは以下の評価機能を提供します：

| 評価器 | 用途 |
|--------|------|
| `LLMJudgeEvaluator` | LLMを使用した回答品質評価（accuracy, relevance, completeness, tone） |
| `RoutingAccuracyEvaluator` | ルーティング精度評価（precision, recall, F1, 混同行列） |
| `EvaluationReportGenerator` | 評価結果のレポート生成・比較・トレンド分析 |

## テスト実行

```bash
# 全評価テスト実行
python -m pytest tests/evaluation/ -v

# ルーティング精度評価テスト
python -m pytest tests/evaluation/test_routing_accuracy.py -v

# LLM Judge評価テスト（API不要のモック版）
python -m pytest tests/evaluation/test_llm_judge.py -v

# LLM APIを使用した実テスト（要OPENAI_API_KEY）
python -m pytest tests/evaluation/test_llm_judge.py -v --run-llm

# レポート生成テスト
python -m pytest tests/evaluation/test_report_generator.py -v
```

## 使用例

### ルーティング精度評価

```python
from tests.utils.evaluators.routing_accuracy import (
    RoutingAccuracyEvaluator,
    RoutingTestCase,
)
from tests.fixtures.dataset_loader import DatasetLoader

# テストケース読み込み
test_cases = DatasetLoader.load_routing_test_cases(language="ja")

# 評価実行
evaluator = RoutingAccuracyEvaluator()
for case in test_cases:
    # 実際のルーティング結果を取得（例）
    actual_agent = router.route(case.query)

    await evaluator.evaluate_single(
        test_case=case,
        actual_agent=actual_agent,
        confidence=0.9,
    )

# メトリクス計算
metrics = evaluator.compute_metrics()
print(f"Overall Accuracy: {metrics.overall_accuracy:.2%}")
print(f"Macro F1: {metrics.macro_f1:.2%}")

# エージェント別メトリクス
for agent_name, agent_metrics in metrics.agent_metrics.items():
    print(f"{agent_name}: P={agent_metrics.precision:.2%}, R={agent_metrics.recall:.2%}")
```

### LLM Judge評価

```python
from tests.utils.evaluators.llm_judge import LLMJudgeEvaluator, QualityDimension

evaluator = LLMJudgeEvaluator(model_name="gpt-4o-mini")

# 回答品質評価
results = await evaluator.evaluate_answer_quality(
    question="Wi-Fiのパスワードを教えてください",
    answer="Wi-Fiのパスワードは「engineer2025」です。",
    language="ja",
    dimensions=[QualityDimension.ACCURACY, QualityDimension.RELEVANCE],
)

for result in results:
    print(f"{result.dimension}: {result.score:.2f} ({'PASS' if result.passed else 'FAIL'})")
```

### レポート生成

```python
from tests.utils.evaluators.report_generator import EvaluationReportGenerator

generator = EvaluationReportGenerator()

# レポート生成
report = generator.generate_report(
    routing_metrics=metrics,
    llm_judge_results=llm_results,
    confidence_analysis=evaluator.analyze_confidence_thresholds(),
)

# JSON保存
filepath = generator.save_report(report)
print(f"Report saved: {filepath}")

# トレンド分析
trend = generator.get_trend_data("overall_accuracy", limit=10)
```

## ファイル構成

```
tests/
├── evaluation/
│   ├── __init__.py
│   ├── conftest.py              # テストフィクスチャ
│   ├── test_llm_judge.py        # LLM Judge評価テスト
│   ├── test_routing_accuracy.py # ルーティング精度テスト
│   ├── test_report_generator.py # レポート生成テスト
│   └── README.md                # このファイル
├── fixtures/
│   ├── __init__.py
│   ├── dataset_loader.py        # データセットローダー
│   ├── golden_datasets/         # ゴールデンデータセット
│   │   ├── routing_test_cases.json
│   │   └── answer_quality.json
│   └── README.md                # データセット説明
├── utils/
│   └── evaluators/
│       ├── __init__.py
│       ├── llm_judge.py         # LLM Judge評価器
│       ├── routing_accuracy.py  # ルーティング精度評価器
│       └── report_generator.py  # レポート生成器
└── reports/                     # 生成されたレポート（gitignore対象）
```

## 注意事項

### テストデータについて

`tests/fixtures/golden_datasets/` 内のデータは**評価ロジックのテスト用ダミーデータ**です。

- Wi-Fiパスワード、営業時間などは**実際のエンジニアカフェの情報とは異なります**
- 評価器の動作確認が目的であり、本番データではありません
- 本番環境での評価には、実際の情報を含むデータセットを別途用意してください

詳細は `tests/fixtures/README.md` を参照してください。

## 依存関係

追加インストール不要（既存の依存関係のみ使用）：
- `langsmith` - 既存
- `langchain-openai` - 既存（LLM Judge使用時）
- `pytest`, `pytest-asyncio` - 既存
