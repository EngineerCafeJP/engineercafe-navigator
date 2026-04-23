# Third-Party Licenses

本ドキュメントは Engineer Cafe Navigator (engineercafe-navigator) プロジェクトが依存する
サードパーティソフトウェア・モデル・サービスとその License を一覧化したものです。

プロジェクト自体のライセンスは [LICENSE](./LICENSE) を参照してください（OSS リリース時）。

最終更新: 2026-04-24

---

## 1. Python Backend 依存 (`backend/pyproject.toml`)

### LangGraph / LangChain Ecosystem

| Package | Version | License | Project |
|---|---|---|---|
| langgraph | ^1.0 (<1.2) | MIT | https://github.com/langchain-ai/langgraph |
| langgraph-checkpoint-postgres | ^2.0.0 | MIT | https://github.com/langchain-ai/langgraph |
| langchain | ^0.3.0 | MIT | https://github.com/langchain-ai/langchain |
| langchain-openai | ^0.2.0 | MIT | https://github.com/langchain-ai/langchain |
| langsmith | ^0.3.12 | MIT | https://github.com/langchain-ai/langsmith-sdk |

### Web Framework / Runtime

| Package | Version | License | Project |
|---|---|---|---|
| fastapi | ^0.115.0 | MIT | https://github.com/tiangolo/fastapi |
| uvicorn | ^0.30.0 | BSD-3-Clause | https://github.com/encode/uvicorn |
| httpx | ^0.27.0 | BSD-3-Clause | https://github.com/encode/httpx |
| python-multipart | ^0.0.9 | Apache-2.0 | https://github.com/andrew-d/python-multipart |
| python-dotenv | ^1.0.0 | BSD-3-Clause | https://github.com/theskumar/python-dotenv |
| slowapi | >=0.1.9 | MIT | https://github.com/laurentS/slowapi |

### Data / Validation

| Package | Version | License | Project |
|---|---|---|---|
| pydantic | ^2.0.0 | MIT | https://github.com/pydantic/pydantic |
| pydantic-settings | ^2.0.0 | MIT | https://github.com/pydantic/pydantic-settings |
| numpy | ^1.24.0,<2.0 | BSD-3-Clause | https://github.com/numpy/numpy |
| scipy | ^1.10.0 | BSD-3-Clause | https://github.com/scipy/scipy |

### Database / Storage

| Package | Version | License | Project |
|---|---|---|---|
| psycopg | ^3.1.0 | LGPL-3.0 | https://github.com/psycopg/psycopg |
| psycopg-pool | ^3.1.0 | LGPL-3.0 | https://github.com/psycopg/psycopg |
| supabase (python) | ^2.0.0 | MIT | https://github.com/supabase/supabase-py |

### Search / AI Services

| Package | Version | License | Project |
|---|---|---|---|
| tavily-python | ^0.5.0 | MIT | https://github.com/tavily-ai/tavily-python |
| google-auth | ^2.0.0 | Apache-2.0 | https://github.com/googleapis/google-auth-library-python |

### Audio / STT / TTS

| Package | Version | License | Project |
|---|---|---|---|
| vosk | ^0.3.45 | Apache-2.0 | https://github.com/alphacep/vosk-api |
| soundfile | ^0.12.1 | BSD-3-Clause | https://github.com/bastibe/python-soundfile |
| pykakasi | ^1.2.0 | GPL-3.0 | https://github.com/miurahr/pykakasi |

### Document Processing

| Package | Version | License | Project |
|---|---|---|---|
| pymupdf | ^1.24.0 | AGPL-3.0 | https://github.com/pymupdf/PyMuPDF |

> **Note**: pymupdf (AGPL-3.0) は商用利用時にライセンス交換 (Artifex 経由の商用ライセンス) を検討してください。

---

## 2. Frontend 依存 (`frontend/package.json`)

### React Stack

| Package | Version | License | Project |
|---|---|---|---|
| react | ^19.1.0 | MIT | https://github.com/facebook/react |
| react-dom | ^19.1.0 | MIT | https://github.com/facebook/react |
| next | ^15.3.9 | MIT | https://github.com/vercel/next.js |

### UI Libraries

| Package | Version | License | Project |
|---|---|---|---|
| @headlessui/react | ^2.2.4 | MIT | https://github.com/tailwindlabs/headlessui |
| lucide-react | ^0.511.0 | ISC | https://github.com/lucide-icons/lucide |
| react-hot-toast | 2.5.2 | MIT | https://github.com/timolins/react-hot-toast |
| @uiw/react-md-editor | 4.0.7 | MIT | https://github.com/uiwjs/react-md-editor |
| react-markdown | 10.1.0 | MIT | https://github.com/remarkjs/react-markdown |
| remark | ^15.0.1 | MIT | https://github.com/remarkjs/remark |
| remark-html | ^16.0.1 | MIT | https://github.com/remarkjs/remark-html |
| gray-matter | ^4.0.3 | MIT | https://github.com/jonschlinkert/gray-matter |

### VRM / 3D

| Package | Version | License | Project |
|---|---|---|---|
| @pixiv/three-vrm | ^3.4.1 | MIT | https://github.com/pixiv/three-vrm |
| @pixiv/three-vrm-animation | 3.4.1 | MIT | https://github.com/pixiv/three-vrm |
| three | ^0.176.0 | MIT | https://github.com/mrdoob/three.js |

### Voice Activity Detection

| Package | Version | License | Project |
|---|---|---|---|
| @ricky0123/vad-react | 0.0.36 | ISC | https://github.com/ricky0123/vad |
| Silero VAD (bundled models) | v5 / legacy | MIT | https://github.com/snakers4/silero-vad |

### Slide Rendering (Marp)

| Package | Version | License | Project |
|---|---|---|---|
| @marp-team/marp-cli | ^4.1.2 | MIT | https://github.com/marp-team/marp-cli |
| @marp-team/marp-core | ^4.1.0 | MIT | https://github.com/marp-team/marp-core |
| @marp-team/marpit | ^3.1.3 | MIT | https://github.com/marp-team/marpit |

### AI SDK

| Package | Version | License | Project |
|---|---|---|---|
| ai (Vercel AI SDK) | ^4.1.15 | Apache-2.0 | https://github.com/vercel/ai |
| openai | 5.8.2 | Apache-2.0 | https://github.com/openai/openai-node |

### Data / Storage

| Package | Version | License | Project |
|---|---|---|---|
| @supabase/supabase-js | ^2.49.8 | MIT | https://github.com/supabase/supabase-js |
| @upstash/redis | 1.34.9 | MIT | https://github.com/upstash/upstash-redis |
| swr | 2.3.3 | MIT | https://github.com/vercel/swr |

### Document / Security / Util

| Package | Version | License | Project |
|---|---|---|---|
| pdfjs-dist | 4.10.38 | Apache-2.0 | https://github.com/mozilla/pdf.js |
| dompurify | 3.3.3 | (MPL-2.0 OR Apache-2.0) | https://github.com/cure53/DOMPurify |
| zod | ^3.24.4 | MIT | https://github.com/colinhacks/zod |
| uuid | 11.1.0 | MIT | https://github.com/uuidjs/uuid |
| cron | 4.3.1 | MIT | https://github.com/kelektiv/node-cron |
| ws | ^8.18.2 | MIT | https://github.com/websockets/ws |
| copy-webpack-plugin | 12.0.2 | MIT | https://github.com/webpack-contrib/copy-webpack-plugin |

### Build / Dev

| Package | Version | License | Project |
|---|---|---|---|
| typescript | ^5.8.3 | Apache-2.0 | https://github.com/microsoft/TypeScript |
| eslint | 9.27.0 | MIT | https://github.com/eslint/eslint |
| eslint-config-next | 15.3.3 | MIT | https://github.com/vercel/next.js |
| tailwindcss | ^3.4.17 | MIT | https://github.com/tailwindlabs/tailwindcss |
| postcss | ^8.4.47 | MIT | https://github.com/postcss/postcss |
| autoprefixer | ^10.4.20 | MIT | https://github.com/postcss/autoprefixer |
| @playwright/test | 1.58.2 | Apache-2.0 | https://github.com/microsoft/playwright |
| tsx | ^4.19.4 | MIT | https://github.com/privatenumber/tsx |
| dotenv | 16.5.0 | BSD-2-Clause | https://github.com/motdotla/dotenv |
| node-fetch | 3.3.2 | MIT | https://github.com/node-fetch/node-fetch |
| ignore-loader | ^0.1.2 | MIT | https://github.com/cherrry/ignore-loader |
| node-loader | ^2.1.0 | MIT | https://github.com/webpack-contrib/node-loader |

---

## 3. STT / TTS / Voice Models

### STT Models

| Model | License | Source | Notes |
|---|---|---|---|
| Vosk Small JA (`vosk-model-small-ja-0.22`) | Apache-2.0 | https://alphacephei.com/vosk/models | `backend/Dockerfile: RUN bash scripts/download_vosk_models.sh models` |
| Qwen3-ASR 0.6B | Apache-2.0 | https://huggingface.co/Qwen/Qwen3-ASR-0.6B | `backend/Dockerfile: RUN bash scripts/download_qwen_model.sh` |
| Whisper (optional fallback) | MIT | https://github.com/openai/whisper | OpenAI Whisper model weights |

### TTS Engines & Voices

| Engine / Voice | License | Source | Notes |
|---|---|---|---|
| Piper-plus TTS | MIT | https://github.com/OHF-voice/piper1-gpl | `docker/piper-plus/README.md` 参照、ja+en bilingual |
| VoiceVox Engine | LGPL-3.0 | https://github.com/VOICEVOX/voicevox_engine | `docker-compose.yml: image: voicevox/voicevox_engine:latest` |
| Tsukuyomi-chan (VoiceVox 話者) | 独自 (VoiceVox 利用規約) | https://tyc.rei-yumesaki.net/ | つくよみちゃん利用規約準拠、クレジット表記必要 |
| Google Cloud Text-to-Speech | Google Cloud 利用規約 | https://cloud.google.com/text-to-speech | ランタイム依存、ローカル再配布なし |

### Voice Activity Detection

| Model | License | Source | Notes |
|---|---|---|---|
| Silero VAD v5 / Legacy | MIT | https://github.com/snakers4/silero-vad | `@ricky0123/vad-web` 経由でバンドル |

---

## 4. 外部サービス (Runtime 依存, ランタイム接続のみ)

以下は API / SaaS 経由のサービスで、本 repo には license 対象のコード/モデルは含まれません。
利用時は各サービスの利用規約に従ってください。

| Service | Purpose | Terms |
|---|---|---|
| Google Cloud Platform (Cloud Run, STT, TTS, Secret Manager) | Backend host + voice | https://cloud.google.com/terms |
| OpenRouter | LLM (Gemini) + Embeddings (text-embedding-3-small) | https://openrouter.ai/terms |
| Supabase | PostgreSQL + pgvector + Auth | https://supabase.com/terms |
| Tavily | Web search fallback for GeneralKnowledgeAgent | https://tavily.com/terms |
| Vercel | Frontend hosting + Edge Functions | https://vercel.com/legal/terms |
| Google Calendar | ICS event data (`GOOGLE_CALENDAR_ICAL_URL`) | https://workspace.google.com/terms |

---

## 5. 独立系の Static Assets / 音声アセット

本 repo に含まれる音声ファイル (`frontend/public/audio/` など) は以下のソースに由来します:

- ナレーション音源: プロジェクト内生成 (Piper-plus / VoiceVox / Google TTS のいずれか)
- 効果音・BGM: 該当なし (2026-04-24 時点)

> プロジェクト内で生成された TTS 出力については、元エンジン (VoiceVox/Piper-plus/GCP TTS) の
> ライセンス・利用規約が派生物にも適用されます。特に **つくよみちゃん** を使った TTS 出力は
> つくよみちゃん利用規約 (https://tyc.rei-yumesaki.net/about/terms/) の記載に従い、
> 商用利用・公開時にクレジット表記が必要です。

---

## 6. ライセンス全文

各 License の全文は [Choose a License](https://choosealicense.com/) および各プロジェクトの
リポジトリを参照してください。本文書は summary であり、法的拘束力ある license 本文は
各配布元の LICENSE ファイルを権威ソースとしてください。

---

## 7. 更新方針

- 新規依存追加時は本ファイルも同一 PR で更新すること (`hooks/enforce-doc-update-scope.sh` 参照)
- `pnpm add <pkg>` / `pip install <pkg>` / `uv add <pkg>` 実行後、本表に 1 行追記
- license 不明なパッケージは追加前に精査、AGPL/GPL 系はプロジェクト方針 (OSS MIT/Apache 寄り) と整合するか確認
- Related: Epic #484 (OSSリリース準備)、Issue #490 (本ドキュメント起源)
