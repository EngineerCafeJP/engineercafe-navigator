# OSS / License Posture

最終更新: 2026-05-10

この文書は、リポジトリ内で確認できる license / provenance 証跡を整理する運用メモです。法的助言ではありません。第三者コード、モデル、音声、画像、サービスの条件は、それぞれの配布元 license / terms を優先してください。

## リポジトリ license

- リポジトリ直下の `package.json` と `frontend/package.json` は `license: "ISC"` を宣言しています。
- ルートの [`LICENSE`](../LICENSE) は ISC License です。
- ルートの `package.json` は `private: true` です。これは npm package publish を止める設定であり、リポジトリの license 宣言そのものではありません。
- `backend/pyproject.toml` には Python package metadata としての license field はありません。Python distribution を公開する場合は、公開前に package metadata へ license 表記を追加してください。

ISC license は、このリポジトリで project-authored source / docs を配布するための根拠です。第三者依存、モデル重み、SaaS terms、商標、施設名、店舗名、ロゴ、公式サイト由来の文章、権利元が別にある media asset を再 license するものではありません。

## Third-party dependency posture

依存関係の棚卸しは [`../THIRD_PARTY_LICENSES.md`](../THIRD_PARTY_LICENSES.md) を正本にします。新しい dependency を追加した PR では、同じ PR で同ファイルを更新してください。

現在の棚卸しで特に確認が必要な license family:

| 項目 | 記録された license | 確認理由 |
| --- | --- | --- |
| `pymupdf` | AGPL-3.0 | hosted / commercial distribution posture を確認する |
| `pykakasi` | GPL-3.0 | distribution posture を確認する |
| `psycopg`, `psycopg-pool` | LGPL-3.0 | linking / packaging posture を確認する |
| `dompurify` | MPL-2.0 OR Apache-2.0 | selected license path を記録する |

`THIRD_PARTY_LICENSES.md` は人手の summary です。release 前は lockfile / environment から実際に解決された package version と upstream license を再確認してください。

## Models / audio / generated assets

現在の docs / scripts が示す voice stack:

| artifact family | repository evidence | required posture |
| --- | --- | --- |
| Qwen3-ASR | `backend/scripts/download_qwen_model.sh` downloads `Qwen/Qwen3-ASR-0.6B`; inventory lists Apache-2.0 | deployed model ID, revision, checksum, and upstream licenseを release evidence に残す |
| Qwen3-ASR ONNX candidate | `backend/scripts/download_qwen_onnx_model.sh` downloads `Daumee/Qwen3-ASR-0.6B-ONNX-CPU` when enabled | `QWEN_ONNX_HF_REPO`, `QWEN_ONNX_REVISION`, output checksums, and upstream licenseを release evidence に残す |
| Vosk STT models | `backend/scripts/download_vosk_models.sh` downloads `vosk-model-small-ja-0.22` and `vosk-model-small-en-us-0.15`; inventory lists Apache-2.0 | downloaded archive URL, extracted version, checksum, and upstream licenseを残す |
| Helsinki-NLP translation models | `backend/scripts/download_translation_models.sh` converts `opus-mt-en-jap` and `opus-mt-ja-en` to CTranslate2 int8 | Hugging Face model card license, converted artifact checksums, and tokenizer file provenanceを確認する |
| Piper / PiperPlus TTS | architecture docs say PiperPlus is current primary TTS; checked-in MP3/WAV assets exist | actual engine image/source, voice model, generated-output terms, generation date, and attribution needsを残す |
| VoiceVox / つくよみちゃん | inventory documents legacy/runtime options and attribution caveats | VoiceVox or つくよみちゃん outputを使う場合は terms / credit requirementを release notes に残す |
| OpenRouter / Google Cloud / Tavily / Supabase | runtime API/SaaS dependencies | code repository license does not cover provider terms or model output policy |

公開前に provenance が必要な checked-in media:

- `frontend/public/reception/audio/**`
- `backend/static/fillers/**`
- `frontend/public/reception/*.pdf`
- `frontend/public/assets/images/**`
- `frontend/public/backgrounds/**`
- `frontend/public/animations/**`

現時点では、これらの binary/media asset について per-file license manifest は見つかっていません。公開・再配布・商用運用前に、少なくとも source, owner, license/terms, generated-by, generated-at, and attribution requirement を記録してください。

受付スライド PDF / QR 更新の個別記録:

- [`assets/reception-slide-assets-2026-05-10.md`](assets/reception-slide-assets-2026-05-10.md)

## Deployed model artifact verification

operator は deploy ごとに次を確認してください。

1. Runtime env を記録する: `STT_PROVIDER`, `QWEN_ASR_MODEL_ID`, `HF_HOME`, Vosk model path, `STT_QWEN_ONNX_MODEL_DIR`, `QWEN_ONNX_HF_REPO`, `QWEN_ONNX_REVISION`, translation model dir, `TTS_PROVIDER`, Piper/PiperPlus image digest, voice model path/name。
2. Container image / build log / model cache から、実際に deploy された model ID, revision, file checksum, and license file/model card の有無を記録する。
3. `THIRD_PARTY_LICENSES.md` の model/license 行が実 artifact と一致することを確認する。
4. Static MP3/WAV/PDF/image/VRMA を更新した場合、asset provenance を同じ PR で更新する。
5. 上記 evidence が欠ける場合、その release を "OSS-ready" と表現しない。

## Engineer Cafe / Saino knowledge source

リポジトリ内の証跡:

- [`docs/reference/engineer-cafe-reference.md`](reference/engineer-cafe-reference.md) は docs と test fixture が参照する local staff reference です。
- `backend/knowledge/data/*.yaml` の entry は `source: "official"` と `verified: true` を持ちます。
- test fixture docs は public Engineer Cafe site と connpass URL を source reference として挙げています。

姿勢:

- Engineer Cafe / cafe&bar saino の事実情報は factual reference data として扱えます。ただし、この repository には official site copy, menu copy, logos, photos, store branding の個別 content license は含まれていません。
- official website や menu prose が ISC で再 license されたとは仮定しないでください。source URL と last-verified date を添えた短い factual summary を優先します。
- Saino の営業時間、menu item、価格は変更されやすい情報です。deploy 前に店舗または公式ページで確認してください。
- PDF、menu scan、写真、ロゴ、公式本文の長い引用を取り込む場合は、merge 前に permission/license と attribution requirement を記録してください。

## Contributor checklist

- Add or update `THIRD_PARTY_LICENSES.md` for new package, model, voice, SaaS, or generated media dependencies.
- For asset additions, include source, owner, license/terms, and attribution notes in the PR description or a provenance doc.
- For model changes, record model ID, provider, revision/checksum, license/terms, and whether weights are redistributed or downloaded at runtime/build time.
- Keep docs factual. Do not describe the project as fully cleared for redistribution unless the dependency, model, and asset evidence above is present.
