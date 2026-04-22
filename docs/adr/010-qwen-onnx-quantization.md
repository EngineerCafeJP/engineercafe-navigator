# ADR 010: Qwen3-ASR ONNX + INT4 量子化スパイク

作成日: 2026-04-22

## ステータス

提案: **現時点のスコープでは Phase 2 の ONNX/INT4 実装へ進まない（No-Go）**

## 背景

Issue #491 では、現在 PyTorch CPU で動かしている `Qwen/Qwen3-ASR-0.6B` を ONNX Runtime + INT4 量子化に変換し、STT レイテンシを現状の p50 約 4.0 秒から p50 1.5 秒へ下げることを狙っていた。

この ADR は Phase 1 スパイク結果だけを記録する。ランタイム実装はまだ変更していない。

理由:

- OpenCode が #487 で `backend/utils/language_processor.py` と `backend/workflows/main_workflow.py` を作業中。
- session-1771 が `backend/api/*` を作業中。
- Phase 1 指示では、Phase 2/3 に進む前に Go / No-Go 判定を出すことになっている。

## 現在の STT 実装

本番 Cloud Run は `STT_PROVIDER=qwen-primary` で動いている。

`backend/agents/stt_agent.py` の `qwen-primary` は次を使う。

- primary: `Qwen06BCpuSTTClient`
- fallback: `LocalSTTClient`、つまり Vosk
- timeout: `QWEN_STT_TIMEOUT`、現状は 10 秒

重要な挙動:

```python
qwen_result, vosk_result = await asyncio.gather(
    _run_qwen(), _run_vosk(), return_exceptions=True
)
```

これは「Qwen が先に成功したら即返す」実装ではない。Qwen と Vosk の両方が終わるまで待つ。つまり Qwen が速く終わっても、Vosk のモデルロードや CPU 競合が遅いと、リクエスト全体は Vosk を待って遅くなる。

もう1つ重要な点として、Qwen 成功時の補正は `STT_QWEN_POSTPROCESS_ENABLED` で制御されている。一方で Cloud Run に設定した `STT_LLM_POSTPROCESS=true` は、主に Vosk fallback 側または Vosk provider 側に効く。つまり Qwen が成功した場合、現状の `STT_LLM_POSTPROCESS=true` だけでは Qwen 出力の固有名詞補正が必ずしも有効にならない。

## Phase 1 実行環境

作業 worktree:

- `/tmp/engineer-cafe-navigator2025-work5-491`
- base: `origin/develop` の `b5a5299c6`

スパイク用に Work5 のローカル `.venv` にだけ入れた依存:

- `qwen-asr==0.0.6`
- `torch==2.11.0`
- `transformers==4.57.6`
- `optimum==2.1.0`
- `optimum-onnx==0.1.0`
- `onnx==1.21.0`
- `onnxruntime==1.24.4`

これらは Phase 1 の検証用であり、プロジェクトの依存ファイルには追加していない。

## ONNX export 可否

実行したコマンド:

```bash
uv run optimum-cli export onnx \
  --model Qwen/Qwen3-ASR-0.6B \
  --task automatic-speech-recognition \
  /tmp/qwen-asr-onnx-spike-fp32
```

結果: **失敗**。

エラー:

```text
ValueError: The checkpoint you are trying to load has model type `qwen3_asr`
but Transformers does not recognize this architecture.
```

原因:

- `qwen_asr.inference.qwen3_asr` を import すると、以下の登録が行われる。
  - `AutoConfig.register("qwen3_asr", Qwen3ASRConfig)`
  - `AutoModel.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)`
  - `AutoProcessor.register(Qwen3ASRConfig, Qwen3ASRProcessor)`
- しかし `optimum-cli` は `qwen_asr` を import する前に `AutoConfig.from_pretrained()` を呼ぶため、`qwen3_asr` という architecture を知らずに失敗する。

確認として、Python で先に `qwen_asr.inference.qwen3_asr` を import すれば Transformers は `qwen3_asr` を解決できる。

```text
Qwen3ASRConfig
model_type=qwen3_asr
AutoModel -> Qwen3ASRForConditionalGeneration
```

ただし、これだけでは Optimum の標準 export が使えるようにはならない。

## custom export の見込み

`Qwen3ASRForConditionalGeneration.forward` は通常の forward として実装されておらず、デフォルトの `_forward_unimplemented` のままだった。

実際の推論経路は次の形。

```python
inputs = processor(text=sub_text, audio=sub_wavs, return_tensors="pt", padding=True)
text_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)
decoded = processor.batch_decode(text_ids.sequences[:, inputs["input_ids"].shape[1]:])
```

つまり Qwen3-ASR は単純な encoder-only ASR モデルではなく、`generate()` を使う autoregressive generation モデルである。ONNX 化するには、decoder cache や生成ループを含む形で export / serving する必要がある。

これは「コマンド1つで ONNX export して INT4 量子化する」作業ではなく、独自の Optimum ORT model integration に近い。

FP32 ONNX graph が作れなかったため、INT4 量子化は未実施。

## ローカル PyTorch baseline

使用 sample:

- `frontend/e2e/fixtures/voice/sample.wav`
- sample rate: 16kHz
- duration: 1.811 秒
- 期待 transcript: `Tell me about Engineer Cafe.`

実行内容:

```python
model = Qwen3ASRModel.from_pretrained(
    "Qwen/Qwen3-ASR-0.6B",
    torch_dtype=torch.float32,
    device_map="cpu",
    low_cpu_mem_usage=True,
    max_new_tokens=256,
)
model.transcribe(audio=(pcm, 16000), language="English")
```

結果:

| 指標 | 結果 |
| --- | ---: |
| モデルロード | 5.348s |
| 1回目 | 0.601s |
| 2回目 | 0.490s |
| 3回目 | 0.293s |
| 4回目 | 0.294s |
| 5回目 | 0.293s |
| warm p50 | 0.294s |
| max | 0.601s |
| transcript | `Tell me about Engineer Cafe.` |

解釈:

- Qwen3-ASR 0.6B の PyTorch 推論そのものは、warm 状態では十分速い可能性がある。
- Cloud Run で観測している STT p50 約 4 秒は、Qwen PyTorch 単体の遅さだけでは説明しにくい。
- 現在の `qwen-primary` は Qwen と Vosk の両方を待つため、Vosk のモデルロードや CPU 競合が全体 latency を支配している可能性が高い。

## Piper Plus 実音声テスト

実行コマンド:

```bash
LIVE_BACKEND_URL=https://engineer-cafe-backend-639959525777.asia-northeast1.run.app \
LIVE_BACKEND_API_KEY="$(gcloud secrets versions access latest \
  --secret=API_SECRET_KEY --project=aipartner-426616)" \
uv run pytest --run-e2e tests/e2e/test_stt_japanese_accuracy.py -v -m e2e --no-header
```

このテストは、Cloud Run の live `/api/voice` TTS で日本語音声を生成し、その音声を live STT に戻す。現行 Cloud Run 設定では TTS は Piper Plus 経路である。

parametrize された最初の10サンプルの結果:

| サンプル | 結果 | transcript |
| --- | --- | --- |
| `proper_noun_cafe` | failed | `現地 に た` |
| `coworking_katakana` | passed | n/a |
| `business_hours` | passed | n/a |
| `event_info` | passed | n/a |
| `wifi_alphanumeric` | failed | `はい 日 の パスワード は あり ます か` |
| `reception_procedure` | failed | `駆けつけました。ご確認ください。` |
| `community_manager` | failed | `今年 に か な 姉 じゃあ に 澤田 し たい` |
| `meeting_reserve` | failed | `エンジニアカフェは予約できますか？` |
| `fukuoka_city` | passed | n/a |
| `basement_space` | failed | `下の子は、エンジニアカフェ(Engineer Cafe)にいます。` |

実質的な初回 pass rate: **4/10 = 40%**。

その後の aggregate test は `/api/voice` の rate limit に当たった。

```text
429 {"error":"Rate limit exceeded: 20 per 1 minute"}
```

解釈:

- Piper Plus 音声を使った live STT では、速度以前に accuracy が足りていない。
- 特に固有名詞、WiFi、受付、コミュニティマネージャー、ミーティングスペース、地下コワーキングが崩れている。
- aggregate test は同じ10サンプルをもう一度 TTS+STT するため、1分以内に20回以上 `/api/voice` を叩いて rate limit にかかる。これは follow-up #502 の妥当性を確認する結果でもある。

## 判断

現時点では Phase 2 の ONNX/INT4 実装へ進まない。

理由:

1. Optimum 標準 ONNX export が `qwen3_asr` 未登録で失敗する。
2. Qwen3-ASR は通常の `forward()` を持たず、`generate()` 経由の autoregressive model である。custom ONNX export はかなり重い。
3. ローカル PyTorch warm inference は 0.3 秒前後で、Qwen PyTorch 単体は十分速い可能性がある。
4. Cloud Run の 4 秒級 latency は、Qwen 単体ではなく `qwen-primary` が Vosk 完了まで待つ設計や、post-process flag の不整合に起因している可能性が高い。
5. Piper Plus 実音声テストは 4/10 pass に留まり、速度改善だけでは alpha 品質に届かない。

## 推奨する次アクション

#491 をいきなり ONNX/INT4 に進めるのではなく、まず次の小さい最適化に pivot する。

1. `qwen-primary` を `asyncio.gather()` から winner-race に変更する。
   - Qwen が成功したら即返す。
   - Vosk は Qwen failure / timeout 時だけ fallback として使う。
   - Qwen 成功後に Vosk を待たない。
2. post-process flag を揃える。
   - Cloud Run に `STT_QWEN_POSTPROCESS_ENABLED=true` を追加する。
   - もしくは `STT_LLM_POSTPROCESS=true` が Qwen 成功パスにも効くようにする。
3. #502 を先に直す。
   - 10サンプル live test が同じ TTS+STT を2回走らせないようにする。
   - 生成済み audio を使い回す、または aggregate test が per-sample 結果を再利用する。
4. その後に live STT p50/p95 と Piper Plus accuracy を再測定する。
5. それでも Qwen-only p50 が目標未達なら、改めて ONNX custom export を検討する。

## Go / No-Go

ONNX/INT4 Phase 2 は **No-Go**。

代わりに次は次の Phase 2 を推奨する。

- `qwen-primary` winner-race 実装
- Qwen post-process flag 整合
- #502 rate limit 回避
- その後に Cloud Run + Piper Plus 実音声で再測定

## 関連

- #491: Qwen3-ASR ONNX Runtime + INT4 量子化
- #484: OSSリリース準備
- #502: STT test rate limit follow-up
- #480 / #499: STT post-process と live Japanese accuracy suite
- #478 / #498: MP3 encoding event-loop blocker removal
