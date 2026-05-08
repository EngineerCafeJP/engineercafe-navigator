# ADR-007: STT 並列アーキテクチャ (Qwen3-ASR Primary + Vosk Fallback)

## Status

Accepted (2026-04-11)

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
音声入力 ──┬──→ Qwen3-ASR 0.6B (asyncio.wait_for, timeout=QWEN_STT_TIMEOUT)
           │     成功 → Qwen 結果返却 (provider="qwen-primary")
           │     hedge delay 超過 ↓
           └──→ Vosk fallback を開始
                 Vosk が先に完了しても、短い grace window で Qwen 完了を待つ
                 Qwen が間に合えば Qwen、間に合わなければ Vosk を返却
                 → STT_LLM_POSTPROCESS=true なら LLM 後処理適用
```

### 並列実行の詳細

- Qwen を先行開始し、`QWEN_STT_HEDGE_DELAY_SECONDS` を超えた場合のみ Vosk fallback を開始
- Qwen に `asyncio.wait_for(timeout=QWEN_STT_TIMEOUT)` を適用
- Vosk が先に完了した場合も `QWEN_STT_HEDGE_GRACE_SECONDS` の範囲で Qwen を待ち、品質が高い Qwen 結果を優先する
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
| `STT_PROVIDER` | コード既定: production=`google`, non-production=`qwen0.6b-cpu`; Cloud Run deploy は `qwen-primary` を明示設定 | STT プロバイダー選択 |
| `QWEN_STT_TIMEOUT` | `24` | Qwen hard timeout (秒)。Cloud Run は `45` |
| `QWEN_STT_HEDGE_DELAY_SECONDS` | `2` | Qwen 先行後、Vosk fallback を開始するまでの soft latency budget |
| `QWEN_STT_HEDGE_GRACE_SECONDS` | `6` | Vosk fallback 完了後も Qwen を優先するために待つ grace window |
| `STT_LLM_POSTPROCESS` | `false` | Vosk フォールバック時の LLM 後処理 |
| `HF_HOME` | `/app/.hf_cache` | HuggingFace モデルキャッシュ |

この ADR が意図する本番構成は `qwen-primary` であり、実際の Cloud Run デプロイも `.github/workflows/ci.yml` から `STT_PROVIDER=qwen-primary` を明示している。`STTAgent` クラスの未設定時フォールバック値はローカル/移行互換のために残っている実装詳細であり、本番ではそれに依存しない。

## Cloud Run 要件

| 項目 | 変更前 | 変更後 | 理由 |
|---|---|---|---|
| メモリ | 2GiB | **8GiB** | Qwen 0.6B (~2.5GB) + Vosk (~900MB) + Python (~500MB)。4GiB では OOM 発生 (4270 MiB) |
| CPU | 2 | 2 | 変更なし |
| min-instances | 1 | 1 | コールドスタート回避 (Qwen ロード 15-30s) |
| max-instances | 3 | 3 | 変更なし |
| Docker イメージ | ~1.2GB | **~3GB** | +1.8GB (Qwen モデル重み + 依存) |
| HF_HOME | 未設定 | `/app/.hf_cache` | 書き込み可能パス (`/nonexistent` 回避) |

## 実装ファイル

| ファイル | 変更内容 |
|---|---|
| `backend/agents/stt_agent.py` | `_transcribe_qwen_primary()` 追加、`speech_to_text()` に分岐追加 |
| `backend/Dockerfile` | `ENV HF_HOME` + `RUN download_qwen_model.sh` |
| `backend/scripts/download_qwen_model.sh` | 新規: HuggingFace モデル DL スクリプト |
| `.github/workflows/ci.yml` | `--memory 8Gi` + `STT_PROVIDER` 設定 |
| `backend/tests/agents/test_stt_agent.py` | 並列 STT テスト 6 件追加 |

## Consequences

### Positive

- 52 言語を 1 モデルで対応 — ja/en 切り替え問題が根本解消
- 精度向上 — Qwen は SOTA、Vosk small より高精度
- LLM 整形パイプライン不要 (Qwen 使用時) — レイテンシ削減
- Vosk フォールバックで障害耐性を維持

### Negative

- Docker イメージ +1.8GB — ビルド・プッシュ時間増加
- Cloud Run コスト増 — 2GiB → 8GiB (約 4 倍)
- Qwen コールドスタート 15-30s — min-instances=1 で回避するがスケールアウト時に遅延
- 並列実行でメモリピーク — Qwen + Vosk (ja/en) が同時にメモリに展開

### Risks

| リスク | 深刻度 | 軽減策 |
|---|---|---|
| Qwen モデルロードで OOM | HIGH | 8GiB 確保 + Cloud Run メモリモニタリング (4GiB では OOM 確認済み) |
| コールドスタート 15-30s | HIGH | min-instances=1、Vosk が即座にフォールバック |
| Qwen が confidence を返さない | MEDIUM | 優先度ベース選択 (Qwen > Vosk) |
| 並列実行でメモリピーク | MEDIUM | Vosk small モデル維持 (48MB + 40MB) |

## 本番検証結果 (2026-04-12)

Cloud Run revision 00077-rjb にデプロイし、本番環境で検証を実施。

### メモリ
- 4GiB: OOM 発生 (4270 MiB 使用、signal 9 で kill)
- **8GiB: 安定稼働** — Qwen (~2.5GB) + Vosk JA/EN (~900MB) + Python (~500MB)

### STT 精度 (TTS合成音声 roundtrip)

| 言語 | 入力 | 認識結果 | confidence | 判定 |
|------|------|----------|-----------|------|
| en | "Tell me about Engineer Cafe" | "tell me about engineer cafe" | 1.0 | ✅ |
| ja | "エンジニアカフェについて教えて" | "現地にカフェについてはせて" | 0.83 | ❌ |

### レスポンス時間
- 初回リクエスト: ~40s (モデルロード) → 500 エラー
- 2回目以降: 2-5s (モデル常駐)
- min-instances=1 でコールドスタート回避

### 2026-04-13 時点の追加運用確認
- GitHub Actions の `frontend-playwright-voice-live` が live backend に対するブラウザ音声 round-trip を merge gate として実行
- このジョブは UI 音声入力経路、`/api/qa` プロキシ、LangGraph 応答、TTS 応答の接続健全性を継続的に確認する

### 未解決課題
1. **日本語 STT 精度**: カタカナ語 ("エンジニア") の認識が弱い
2. **初回リクエスト失敗**: モデルロード中のタイムアウト対策が必要

## References

- Epic Issue: #427
- 調査報告: `docs/plans/qwen-cloud-run-validation-2026-04-11.md`
- STT Migration Guide: `docs/STT-Migration-Guide-qwen3-asr.md`
- ADR-006: `docs/adr/006-langgraph-workflow-redesign.md` (tRAG 多言語対応)
- Qwen3-ASR: https://github.com/QwenLM/Qwen3-ASR
- Vosk Models: https://alphacephei.com/vosk/models
