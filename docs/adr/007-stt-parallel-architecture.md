# ADR-007: STT 並列アーキテクチャ (Qwen3-ASR Primary + Vosk Fallback)

## Status

Proposed (2026-04-11)

## Context

Engineer Cafe Navigator のアルファテストに向けて、STT (Speech-to-Text) アーキテクチャを再設計する必要がある。

### 現行の課題

1. **Vosk の言語別モデル分離**: ja/en が別モデルで、`transcribe_auto_detect()` が `asyncio.gather()` で両モデルを並列実行。2 モデル同時ロードはメモリと CPU の無駄。
2. **Vosk + LLM 整形の 2 段パイプライン**: Vosk (100-300ms) + LLM 整形 (500-3000ms) = 合計 600-3300ms。精度改善のために追加レイテンシを払っている。
3. **多言語対応の限界**: Vosk には日英統合のマルチリンガルモデルが存在しない。zh/ko は対応外。
4. **固有名詞認識の弱さ**: Vosk small モデルは「エンジニアカフェ」等のドメイン固有名詞を高確率で誤認識。

### Qwen3-ASR 0.6B の利点

- 52 言語を 1 モデルで対応 (ja/en/zh/ko 含む)
- 言語自動検出内蔵 (外部 LanguageProcessor 不要)
- SOTA 精度 (open-source ASR 最高水準)
- CPU 推論可能 (GPU 不要)
- 既に `qwen-asr>=0.0.6` が requirements.txt に記載済み
- `Qwen06BCpuSTTClient` が `stt_agent.py` に実装済み

## Decision

**Qwen3-ASR 0.6B を STT プライマリ、Vosk を並列実行フォールバックとする。**

### アーキテクチャ

```
音声入力 ──┬──→ Qwen3-ASR 0.6B (asyncio.wait_for, timeout=10s)
           │     成功 → Qwen 結果返却 (provider="qwen-primary")
           │     タイムアウト/エラー ↓
           └──→ Vosk (asyncio.gather で同時実行済み)
                 Vosk 結果を即返却 (provider="vosk-fallback")
                 → STT_LLM_POSTPROCESS=true なら LLM 後処理適用
```

### 並列実行の詳細

- `asyncio.gather()` で Qwen と Vosk を**同時に開始**
- Qwen に `asyncio.wait_for(timeout=QWEN_STT_TIMEOUT)` を適用
- Vosk は通常 100-300ms で完了 → Qwen がタイムアウトした瞬間に結果が即座に利用可能
- Vosk フォールバック時のみ `_llm_post_process()` (PR #426) が適用される

### STT_PROVIDER の値

| 値 | 動作 | 用途 |
|---|---|---|
| `qwen-primary` | Qwen メイン + Vosk 並列フォールバック | **本番推奨** |
| `vosk` | Vosk のみ (従来動作) | 障害時ロールバック |
| `qwen0.6b-cpu` | Qwen のみ (フォールバックなし) | テスト/比較用 |
| `google` | Google Cloud STT のみ | テスト/比較用 |

### 環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `STT_PROVIDER` | `vosk` | STT プロバイダー選択 |
| `QWEN_STT_TIMEOUT` | `10` | Qwen タイムアウト (秒) |
| `STT_LLM_POSTPROCESS` | `false` | Vosk フォールバック時の LLM 後処理 |
| `HF_HOME` | `/app/.hf_cache` | HuggingFace モデルキャッシュ |

## Cloud Run 要件

| 項目 | 変更前 | 変更後 | 理由 |
|---|---|---|---|
| メモリ | 2GiB | **4GiB** | Qwen 0.6B: 最低 3GB / 推奨 4GB |
| CPU | 2 | 2 | 変更なし |
| min-instances | 1 | 1 | コールドスタート回避 (Qwen ロード 15-30s) |
| max-instances | 3 | 3 | 変更なし |
| Docker イメージ | ~1.2GB | **~2.5GB** | +1.2GB (Qwen モデル重み) |
| HF_HOME | 未設定 | `/app/.hf_cache` | 書き込み可能パス (`/nonexistent` 回避) |

## 実装ファイル

| ファイル | 変更内容 |
|---|---|
| `backend/agents/stt_agent.py` | `_transcribe_qwen_primary()` 追加、`speech_to_text()` に分岐追加 |
| `backend/Dockerfile` | `ENV HF_HOME` + `RUN download_qwen_model.sh` |
| `backend/scripts/download_qwen_model.sh` | 新規: HuggingFace モデル DL スクリプト |
| `.github/workflows/ci.yml` | `--memory 4Gi` + `STT_PROVIDER` 設定 |
| `backend/tests/agents/test_stt_agent.py` | 並列 STT テスト 6 件追加 |

## Consequences

### Positive

- 52 言語を 1 モデルで対応 — ja/en 切り替え問題が根本解消
- 精度向上 — Qwen は SOTA、Vosk small より高精度
- LLM 整形パイプライン不要 (Qwen 使用時) — レイテンシ削減
- Vosk フォールバックで障害耐性を維持

### Negative

- Docker イメージ +1.2GB — ビルド・プッシュ時間増加
- Cloud Run コスト増 — 2GiB → 4GiB (約 2 倍)
- Qwen コールドスタート 15-30s — min-instances=1 で回避するがスケールアウト時に遅延
- 並列実行でメモリピーク — Qwen + Vosk (ja/en) が同時にメモリに展開

### Risks

| リスク | 深刻度 | 軽減策 |
|---|---|---|
| Qwen モデルロードで OOM | HIGH | 4GiB 確保 + Cloud Run メモリモニタリング |
| コールドスタート 15-30s | HIGH | min-instances=1、Vosk が即座にフォールバック |
| Qwen が confidence を返さない | MEDIUM | 優先度ベース選択 (Qwen > Vosk) |
| 並列実行でメモリピーク | MEDIUM | Vosk small モデル維持 (48MB + 40MB) |

## References

- Epic Issue: #427
- 調査報告: `docs/plans/qwen-cloud-run-validation-2026-04-11.md`
- STT Migration Guide: `docs/STT-Migration-Guide-qwen3-asr.md`
- ADR-006: `docs/adr/006-langgraph-workflow-redesign.md` (tRAG 多言語対応)
- Qwen3-ASR: https://github.com/QwenLM/Qwen3-ASR
- Vosk Models: https://alphacephei.com/vosk/models
