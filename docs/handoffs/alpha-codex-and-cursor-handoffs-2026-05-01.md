# Alpha 並列ハンドオフ — Codex (バックエンド) + Cursor (フロントエンド) (2026-05-01)

> **役割分担サマリ**
> - **Codex 経路C** (自律 1 worker): バックエンド latency / routing / filler API / 観測性
> - **Cursor** (4 worker 推奨): フロントエンド Welcome UX / filler 並列再生 / SlideAgent / 拒否UI
> - ファイル境界は完全に分離 (backend/* vs frontend/*) → 競合なしで同時着手可能

---

## 🛡️ ワークツリー分離 (絶対遵守 — Codex / Cursor / Claude Code が同時稼働)

**前提**: Codex (バックエンド) と Cursor (フロントエンド) と Claude Code (監督) が **同じリポジトリの異なるワークツリーで並列稼働** する。メインのチェックアウト (`/Users/teradakousuke/Developer/engineer-cafe-navigator2025`, branch=`develop`) は Claude Code の監督用に保護する。

### ワークツリー割り当て

| 担当 | ワークツリーパス | ブランチ | base |
|---|---|---|---|
| Claude Code (監督) | `/Users/teradakousuke/Developer/engineer-cafe-navigator2025` | `develop` | — |
| **Codex** (BE) | `/Users/teradakousuke/Developer/engineer-cafe-navigator2025-codex-backend` | `feat/alpha-backend-latency-routing` | `develop` |
| **Cursor** (FE) | `/Users/teradakousuke/Developer/engineer-cafe-navigator2025-cursor-frontend` | `feat/alpha-frontend-ux-redesign` | `develop` |

### 作成コマンド

```bash
# Claude Code 監督用ワークツリー (= 既存のメイン) は触らない、develop のまま
cd /Users/teradakousuke/Developer/engineer-cafe-navigator2025
git fetch origin develop
git checkout develop && git pull --ff-only origin develop

# Codex 用ワークツリー (codex-parallel.sh が自動で作るため、手動 add は不要)
# ※ codex-parallel.sh が ../engineer-cafe-navigator2025-codex-backend を自動生成

# Cursor 用ワークツリー (terisuke が手動で作る)
git worktree add \
  /Users/teradakousuke/Developer/engineer-cafe-navigator2025-cursor-frontend \
  -b feat/alpha-frontend-ux-redesign \
  origin/develop

# 確認
git worktree list
# → 3 つのワークツリーが並ぶこと
```

### 厳守ルール

1. **Codex は `backend/*` と `docs/handoffs/*` 以外を編集しない** (frontend/, .github/, vercel.json などに触らない)
2. **Cursor は `frontend/*` と `docs/handoffs/*` 以外を編集しない** (backend/, supabase/, scripts/ などに触らない)
3. **メインの develop ワークツリーは Claude Code 専用**。Codex/Cursor のワークツリーから git push 後は、メインで `git fetch && git checkout develop && git pull` で同期するだけ
4. **ワークツリー削除はマージ後**:
   ```bash
   git worktree remove /Users/teradakousuke/Developer/engineer-cafe-navigator2025-codex-backend
   git worktree remove /Users/teradakousuke/Developer/engineer-cafe-navigator2025-cursor-frontend
   git branch -d feat/alpha-backend-latency-routing  # マージ済みなら -d、未マージなら -D 禁止
   git branch -d feat/alpha-frontend-ux-redesign
   ```
5. **クリーン状態の保証**: 各ワークツリーで実装着手前に必ず以下を実行
   ```bash
   git status                  # untracked/dirty が無いことを確認
   pnpm install --frozen-lockfile  # frontend ワークツリーのみ
   # backend ワークツリーは mise + pip install -r backend/requirements.txt
   ```
6. **ワークツリー横断のファイル参照禁止**: 例えば Cursor 側から `../engineer-cafe-navigator2025-codex-backend/backend/main.py` を read するのは NG。必要なら一旦 develop に push してから fetch
7. **Hook 衝突回避**: Codex/Cursor のワークツリーは `.claude/` をメインから継承するので、`.claude/state/*` の lock ファイル衝突に注意。Codex が PR 作成 hook を発火している間、Cursor は git push を待つ

---

## Part 1: Codex 経路C 委任 — バックエンド統合改修

## Codex 委任理由

Codex は「**長大で複雑な単一タスクを自律的に解決する**」のが得意。本件は LangGraph state machine、orchestrator routing、LLM model registry、新規エンドポイント、テスト追加を **横断的に一貫設計** で改修する必要があり、ファイル数 8-10、推定 3-4 day 規模。並列分割するより 1 つの自律ワーカーが context を保持したまま整合性を持って改修するほうが品質が高い。

## 出典 (Cloud Run logs / コード fact-check 2026-05-01 確認)

- **Cloud Run rev**: `engineer-cafe-backend-00139-nnv` (2026-04-29 18:28 deploy, 最新)
- **Backend image SHA**: `36980bcbee5f99f0d3f25cd31b1fb8e10fbb93f635e40781328f0968a0b9106d`
- **Vercel timeout**: 全エンドポイント `maxDuration: 60` (`frontend/vercel.json:13-30`、PR #637 で 30s → 60s に修正済)
- **Cloud Run logs (24h, severity>=WARNING)**: 0件 ← つまり「予期しないエラー」の主因はもう Cloud Run 内部エラーではなく、**LLM 重さ × 直列処理** に移行している
- **実機実測 (#614 / #613 onsite 2026-04-29 21:48 JST)**:
  - STT `qwen-primary` 2.96s + chat `general_knowledge + web_search` 10.10s + TTS PiperPlus 4.04s = **17.1s** (ユーザーは 30s 待つ前にエラーと感じる)
  - 21:57 JST turn では STT 単体で **14.14s**

## 親 Issue / Sub-issues

- Epic: #614 (Alpha onsite 実機 UX blockers)
- Epic: #612 (Phase 4 後継)
- 直接対応: **#613** (latency), **#617** (stale request_type), **#618** (model split), **#610** (バックエンド側)
- 関連: #615 (PR #620 で部分対応済 → コード上は OK だが live 検証で証跡が必要)

---

## タスク 1: Stale `request_type` 持ち越しによる SlideAgent 誤ルート修正 (#617)

### 真因 (コード fact-check)

- `backend/utils/memory_helper.py:172`
  ```python
  if inherit_context:
      inherited_request_type = await self.get_previous_request_type(session_id)
  ```
  `inherit_context` が True (デフォルト) のとき、**新ターンの query が明示的に別 intent (例: 「明日のイベント」 = event keyword) でも、前ターンの `request_type=basement` が `inherited_request_type` として後段に渡る**。
- `backend/agents/general_knowledge_agent.py:290` で `inherited_request_type` を context に注入
- 結果: orchestrator が fast routing でも LLM routing でも前回の `request_type` の影響を受け、SlideAgent / FacilityAgent に誤ルート

### 受け入れ基準

- 同一 session で「basement (前ターン)」 → 「明日のイベント」 と発話したとき、新ターンは `EventAgent` に route される
- `inherit_context=True` でも、**新ターン query から明示 intent が抽出できる場合は、それを優先**するロジックを追加 (`extract_request_type(query)` の結果が non-None なら inherited を上書き)
- live route test (`backend/tests/integration/test_routing_live.py` 系) に「stale request_type cross-mode」シナリオを 6 ケース追加 (basement→event / wifi→hours / facility→event / slide→event / reception→general / event→slide)
- `Found previous request type:` ログには `query_intent_override=true/false` フィールドを追加

### 実装ファイル

- `backend/utils/memory_helper.py:170-213` — inherited 判定ロジック修正
- `backend/utils/request_type_extractor.py` (or 同等) — `extract_request_type()` の優先度ロジック確認
- `backend/agents/general_knowledge_agent.py:290` — context.inherited_request_type の利用箇所
- `backend/agents/orchestrator_agent.py:316` — fast routing fallback での extract_request_type 結合
- `backend/tests/integration/test_routing_live.py` — シナリオ追加

---

## タスク 2: `general_knowledge` 軽量化と web_search 厳格化 (#618)

### 真因

- `backend/llm/models.py:131-138`
  ```python
  "general_knowledge": ModelConfig(
      model_id=SupportedModel.GEMINI_3_1_PRO,   # ← deep reasoning, 10s 超
      temperature=0.7,
      max_tokens=1024,
      fallback_model=SupportedModel.GEMINI_2_5_PRO,
      ...
  ),
  ```
  `general_knowledge` use_case が **frontier deep-reasoning model** に貼られている。`assistant_profile` / `daily_conversation` は `general_knowledge_agent.py:93/142` で canonical fast path に分岐するので Pro モデルを使わないが、**それ以外 (例: 「Pythonって何ですか」「福岡の天気」)** はすべて Pro + web_search に流れる。
- `web_search` 起動条件は `general_knowledge_agent.py:533` の `_should_use_web_search` で `TavilySearchTool.should_use_web_search()` に委譲。`current_info` mode 以外でも安易に発火する余地あり。

### 受け入れ基準

- `general_knowledge` を **flash-lite class** (例: `GEMINI_3_1_FLASH_LITE` 既定) に降格、p95 chat latency `< 3s`
- 現在の `GEMINI_3_1_PRO` 経路は **新規 use_case `deep_reasoning`** として残し、**「弁証法的考察」「複雑推論」「比較分析」など明示 keyword でしか起動しない**
- `web_search` は **明示 current-info intent (today, 今日, 現在, 最新, weather, news, ニュース 等)** がある場合のみ発火。default で OFF
- general fallback chat の `chat_response.latency_ms` p95 `< 3000`、live 30 ケースで `web_search_used=true` 比率 `< 20%`
- 既存の `assistant_profile` / `daily_conversation` canonical path は壊さない (回帰テスト追加)

### 実装ファイル

- `backend/llm/models.py:131` — `general_knowledge` を flash-lite に変更、`deep_reasoning` use_case 新設
- `backend/agents/general_knowledge_agent.py:533, 512` — `_should_use_web_search` / `_should_use_web_search_adaptive` を strict mode 化
- `backend/agents/general_knowledge_agent.py:148, 175` — needs_web_search 判定の閾値見直し
- `backend/tools/tavily_search.py` — `should_use_web_search()` の current-info keyword リスト見直し
- `backend/tests/test_general_knowledge_agent.py` — flash-lite 経路 + strict web_search のテスト追加

---

## タスク 3: `/api/voice/filler` エンドポイント新設 (#610 バックエンド側)

### 背景

- 現状フロントは STT → chat → TTS を直列で待つため、体感 latency が `8-17s`
- 解決案: STT 完了直後に **pre-recorded フィラー音声を即座に返すエンドポイント** を新設、フロントが並列で叩く
- Phase 2 (Cerebras 動的 #611) は本件の上位互換、まず Phase 1 で 0 ランタイムコストの基盤を作る

### 受け入れ基準

- 新エンドポイント `POST /api/voice/filler`、`Depends(verify_api_key)` 必須、rate limit `60/minute`
- リクエスト: `{"query": str, "language": "ja"|"en"|"zh"|"ko"}`
- レスポンス: `{"audioResponse": base64, "intent": str, "audioFormat": "audio/wav", "fillerText": str, "source": "static"}`
- p99 latency `< 100ms` (intent classify + WAV 読み込みのみ)
- intent → WAV カタログ: 10 intent × 4 lang = 40 ファイル以上、`backend/static/fillers/{intent}_{lang}.wav` に配置
- intent 種別: `greeting`, `business_info`, `facility`, `event`, `wifi`, `general`, `thinking`, `fallback`, `emergency`, `slide`
- 起動時 / build 時に PiperPlus を叩いて WAV 生成するスクリプト `backend/scripts/generate_fillers.py` を実装 (Dockerfile への組込みは別ジョブで OK、最低限スクリプトは動く状態)
- intent classify は `OrchestratorAgent._try_fast_routing()` のキーワード判定ロジックを共通ヘルパに extract して再利用 (二重実装禁止)
- 失敗時は HTTP 200 + `audioResponse: ""` で返し、フロントが degrade できるようにする

### 実装ファイル

- `backend/main.py` — 新エンドポイント追加 (既存 `/api/voice` の下)
- `backend/scripts/generate_fillers.py` — 新規、PiperPlus 経由で WAV 生成
- `backend/static/fillers/` — 新規ディレクトリ、生成された WAV を格納 (gitignore 検討)
- `backend/utils/intent_classifier.py` (新規) — fast keyword classify を `OrchestratorAgent` から extract
- `backend/agents/orchestrator_agent.py:366` — `_try_fast_routing` を新ヘルパで refactor、回帰なし確認
- `backend/tests/test_filler_api.py` — 新規、p99 latency と intent 判定の単体テスト
- `Dockerfile` (backend) — `RUN python scripts/generate_fillers.py` を必要に応じて追加 (PiperPlus が build 段階で reachable でない場合は **runtime startup hook** に切り替え、要 Codex 判断)

---

## タスク 4: 観測性強化 (#613 受入基準のうち observability 部分)

### 背景

- フロントの「予期しないエラー」が **request_id / phase / upstream status を持たない** ため再現不能
- Cloud Run 側に `request_id` を発行し、Vercel proxy → Cloud Run → 各 agent まで一貫して trace できる必要がある

### 受け入れ基準

- `backend/main.py` middleware で incoming request に `X-Request-Id` を発行・付与 (既存があれば再利用、無ければ uuid4)
- 各 structured log line (`stt_overall_duration_ms`, `chat_response.latency_ms`, `tts_overall_duration_ms`) に `request_id` フィールドを追加
- `/api/voice` `/api/chat` レスポンスに `requestId`, `phase`, `upstreamStatus` メタデータを含める (フロントがエラー時にユーザー表示できるよう)
- フロントの error UI が拾えるよう Cloud Run side に schema documentation を残す (docstring レベル可)

### 実装ファイル

- `backend/main.py` — middleware 追加
- `backend/utils/logging_helper.py` (or 同等) — log formatter に request_id 追加
- `backend/agents/voice_agent.py:777` — TTS log に request_id 追加
- `backend/agents/stt_agent.py:1095` — STT log に request_id 追加
- `backend/agents/orchestrator_agent.py` — chat log に request_id 追加

---

## 横断要件 / 制約

### 必須遵守 (CLAUDE.md / .claude/rules/*)

- **Black/Ruff line length: 100** (`backend/pyproject.toml`)
- **CI**: `cd backend && ruff check . && black --check . && pytest -m "not ragas and not slow"` 全パス必須
- **テスト**: 新規ロジックはユニット + 統合テスト、カバレッジ 80%+ 維持
- **ブランチ**: `feat/alpha-backend-latency-routing` (develop ベース)
- **PR target**: `--base develop` 必須、main 直接禁止
- **PR完了条件**: CI green + code-reviewer LGTM + Codex CLI 経路A レビュー LGTM
- **コミット粒度**: 1 タスク = 1 コミット (タスク 1-4 を 4 コミットに分割推奨、最終的な 1 PR に集約)
- **`--update-env-vars` / `--update-secrets`** を使うこと、`--set-*` 禁止 (`MEMORY.md` 参照)

### 触ってはいけない領域

- `frontend/` 全般 (フロント側は Cursor が並行で触る)
- `frontend/vercel.json` (PR #637 で完了済、変更不要)
- `backend/agents/general_knowledge_agent.py:93/142, 617, 644` の **canonical assistant_profile / daily_conversation 経路** (PR #620 で安定済、回帰禁止)
- `frontend/public/reception/engineer-cafe-{ja,en}.pdf` および narration md (PR #629 で配置済)

### live 検証フロー (PR マージ前必須)

1. develop 経由で Cloud Run staging deploy (自動)
2. `gh workflow run alpha-live-verification.yml -f suites=all -f require_deployed_sha_match=true`
3. 全 step success + 以下の追加 gate
   - 実機相当 turn の `chat_response.latency_ms` p95 `< 3000ms`
   - filler endpoint p99 `< 100ms` (新規テスト)
   - cross-mode routing test 6/6 pass (タスク1)
4. 結果を #613 / #617 / #618 / #610 にコメントで貼付

---

## 工数見積

| タスク | 工数 |
|---|---|
| 1. Stale request_type 修正 | 0.5 day |
| 2. general_knowledge 軽量化 | 1 day |
| 3. `/api/voice/filler` 新設 | 1.5 day |
| 4. 観測性強化 | 0.5 day |
| 統合テスト + live 検証 + レビュー対応 | 1 day |
| **合計** | **約 4 day** |

## Codex ハンドオフ実行コマンド (terisuke 手元用)

```bash
# Codex CLI 経路C (実装) — codex-orchestrate.sh で 1 worker, 自律
scripts/codex-orchestrate.sh \
  --prompt-file docs/handoffs/alpha-codex-and-cursor-handoffs-2026-05-01.md \
  --section "Part 1" \
  --branch feat/alpha-backend-latency-routing \
  --base develop \
  --max-context-budget 0.85
```

---

## Part 2: Cursor 委任 — フロントエンド UX 一括再設計

## Cursor 委任理由

Cursor は「**素早く幅広い UI 領域を一気に書き換える**」のが得意。本件は VoiceInterface / Welcome / SlideAgent / filler 統合 / 権限拒否 UI など **複数 UI 領域を横断する独立性の高い改修クラスタ** で、各サブタスクの依存が浅く、Cursor の編集スピード × diff 把握能力にフィット。バックエンド大改修 (Codex 別線) とは **ファイル境界が完全に分離** しているので競合しない。

## 出典 (実機 / コード fact-check 2026-05-01 確認)

- **Vercel deployment**: https://frontend-delta-six-20.vercel.app/ (Production = `develop` branch)
- **直近 merged PR**: #639 (Safari mic + avatar 補正), #637 (vercel.json 60s + Safari audio + slide z-50), #629 (landscape PDF narration)
- **未対応 P0/P1 alpha-gate (オープン)**: #616 (Welcome UX), #610 (filler フロント), #621/#622/#624/#625 (SlideAgent), #638 (getUserMedia 拒否時 UI 伝播)
- **既存 narration assets**: `frontend/public/reception/engineer-cafe-{ja,en}.pdf` + `engineer-cafe-narration-{ja,en}.md` (PR #629)
- **VoiceInterface**: `frontend/src/app/components/VoiceInterface.tsx` (PR #639 で gesture 内 mic init 修正済)
- **ReceptionPdfGuide**: `frontend/src/app/components/ReceptionPdfGuide.tsx:202-203` で narration md fetch + Web Speech API 再生 (PiperPlus 未統合)
- **AudioQueue priority**: `frontend/src/lib/audio-queue.ts:13-42` に既に実装済 (filler を高 priority で挿入可能)

## Cursor 親 Issue / Sub-issues

- Epic: #614 (Alpha onsite 実機 UX blockers)
- Epic: #612 (Phase 4 後継)
- 直接対応: **#616, #610 (フロント側), #621, #622, #624, #625, #638**

---

## タスク A: Welcome を voice-first に再設計 (#616)

### 真因 (コード fact-check)

- 現状 Welcome → クリック → `kiosk-welcome-ocr-overlay` (会員証カメラ) が即起動 (`frontend/e2e/reception-flow.spec.ts` で実際にこの動作を expect している)
- カメラ permission prompt が初対面ユーザーに対して心理的ハードル
- 音声応対ボタンが toggle 形式で Push-to-talk か toggle か明示されない

### 受け入れ基準

- 初期画面 (Welcome) クリック直後は **会話開始導線**。カメラ permission prompt は **出ない**
- 会員証 OCR は **明示的な「会員証で受付」ボタン** または「会員証ありますか？」音声 yes 後のみ起動
- 音声応対は **以下のいずれか 1 つに統一**:
  - 推奨: **Push-to-talk** (押下中録音、release で送信)
  - 代替: tap-to-start / tap-to-stop + 録音中の全画面 affordance + 経過秒 + 停止 CTA
  - 代替: VAD auto-stop (無音検知で自動送信)
- 録音中 / 認識中 / 回答生成中 / 音声合成中 / 再生中 を **画面上部に常時 mode バッジで表示**
- e2e 追加: 「Welcome click → camera permission prompt が出ない」「会員証ボタン経由でのみ camera が起動」「音声 PTT 押下→release で STT 送信」

### 実装ファイル

- `frontend/src/app/page.tsx` — Welcome step ロジック、`kiosk-welcome-ocr-overlay` 起動条件を「会員証ボタン押下後のみ」に
- `frontend/src/app/components/VoiceInterface.tsx` — PTT 化 / 状態 UI 強化 (PR #639 の gesture 内 mic init を踏襲)
- `frontend/src/app/components/MemberCardCapture.tsx` (or 同等) — 明示ボタンから起動するよう entry point 整理
- `frontend/e2e/reception-flow.spec.ts` — 期待を更新 (camera 自動起動の expect を削除、新フロー追加)
- `frontend/e2e/welcome-voice-first.spec.ts` (新規) — voice-first 導線の e2e

---

## タスク B: pre-recorded filler 並列再生 (#610 フロント側)

### 背景

- バックエンド側で `POST /api/voice/filler` が **Codex 別線で同時実装** される (Part 1 タスク 3 参照)
- フロント実装はバックエンド完成を待たず **モック → 実エンドポイント** の順で進めて OK

### 受け入れ基準

- STT (`/api/voice` action=`speech_to_text`) 完了直後に `/api/voice/filler` と `/api/qa` を **`Promise.all` で並列起動**
- filler レスポンスを `audioQueue.add({ id: 'filler', priority: 10, audioData: ... })` で即座に enqueue
- 主応答 TTS は `priority: 5` で続けて enqueue
- 体感 latency: STT 完了 → 最初の可聴音 `< 1s` (現状 8-17s)
- filler エンドポイントが 5xx / null を返したら無音 fallback、UI degrade なし
- VRM `thinking` ポーズに切替 (`emotion-manager.ts`)、主応答 enqueue 時に `speaking` に戻す
- e2e: filler モック後に「STT mock → filler audio enqueue → 主応答 audio enqueue」を Playwright で観測

### 実装ファイル

- `frontend/src/app/components/VoiceInterface.tsx:710-720` — STT → 並列フェッチに改修
- `frontend/src/lib/audio-queue.ts` — priority sort は既存、変更不要だが回帰テスト追加
- `frontend/src/lib/emotion-manager.ts` — `thinking` ↔ `speaking` 切替フック
- `frontend/src/app/api/voice/route.ts` — `/api/voice/filler` proxy ハンドラ追加 (Vercel maxDuration: 60 のまま)
- `frontend/e2e/voice-filler.spec.ts` (新規) — filler モック e2e

---

## タスク C: SlideAgent kiosk autoplay + landscape gate + e2e (#621/#622/#624/#625)

### 背景

- PR #629 で landscape PDF narration が入ったが、以下が残っている:
  - **#622**: 横画面ロック / portrait 警告 + 自動 landscape 起動
  - **#625**: PiperPlus 経由 per-slide narration (現状 `ReceptionPdfGuide.tsx:202-203` は Web Speech API のみ、PiperPlus 未統合)
  - **#624**: e2e validation gate
  - **#621**: 親 epic 全体の close 条件

### 受け入れ基準

- portrait 検知時に「横画面に回してください」のフルスクリーン UI、landscape 検知で自動起動
- スライド遷移ごとに `/api/voice` action=`text_to_speech` (PiperPlus) を呼び、narration md の text を **per-slide で再生**
- Web Speech API は **キャッシュ未到着フォールバック** として残す
- 5-page deck 全 page で ja/en narration が再生される
- e2e: `frontend/e2e/slide-pdf-narration.spec.ts` を拡張、5 page 全部の audio enqueue を assert
- live 検証: Vercel Production で iPhone Safari / Pixel Chrome で 5-page deck を最後まで通せる

### 実装ファイル

- `frontend/src/app/components/ReceptionPdfGuide.tsx:130-720` — orientation gate + per-slide narration fetch + PiperPlus 統合
- `frontend/src/lib/reception/parse-reception-narration-md.ts` — slide-index → text mapping を返すように
- `frontend/src/app/components/MarpViewer.tsx` (該当する場合) — 同等の autoplay
- `frontend/e2e/reception-pdf-guide.spec.ts` — 拡張
- `frontend/e2e/slide-pdf-narration.spec.ts` (新規) — 5-page narration 完走 e2e

---

## タスク D: getUserMedia 拒否時の UI 伝播 + 復帰 (#638, #634 フォローアップ)

### 真因

- Playwright WebKit emulator (iPhone 15 / iOS 17.5) で `navigator.mediaDevices.getUserMedia` を `NotAllowedError` reject に上書きすると、UI は「録音中」のまま固定、`pageerror` 0件
- PR #639 で `voiceController.endManualSession()` を catch で呼ぶ実装済だが、UI state 反映ロジックに欠落あり

### 受け入れ基準

- 拒否時に「マイクの許可が必要です。ブラウザ設定から許可してください」UI 表示 (具体的な復帰手順含む)
- 「録音中」UI が即座に消える
- 再度ボタン押下で再 attempt できる (recovery)
- error.name 別の分岐: `NotAllowedError` / `NotFoundError` / `InvalidStateError` / `SecurityError` で **個別メッセージ**
- e2e: Playwright WebKit で getUserMedia reject scenario を 4 ケース追加 (各 error.name 1 ケース)
- 実機 iOS Safari (BrowserStack 推奨) での permission 拒否確認結果を PR description に貼付

### 実装ファイル

- `frontend/src/app/components/VoiceInterface.tsx` — startRecorderCapture catch ブロック
- `frontend/src/lib/voice-recorder.ts:151-172` — error.name 別 onError 経路
- `frontend/src/lib/error-messages.ts` — `MIC_PERMISSION_DENIED`, `MIC_NOT_FOUND`, `MIC_INVALID_STATE`, `MIC_SECURITY_ERROR` テンプレ追加
- `frontend/e2e/voice-permission-denial.spec.ts` (新規) — Playwright WebKit シナリオ

---

## Cursor 横断要件 / 制約

### 必須遵守 (CLAUDE.md / .claude/rules/*)

- **Tailwind v3.4.17 維持** (v4 アップグレード禁止、`postcss.config.js` の `tailwindcss: {}` のままに)
- **CI**: `cd frontend && pnpm lint && pnpm typecheck && pnpm build` 全パス必須
- **E2E**: `pnpm test:e2e` 関連スイート全パス
- **ブランチ**: `feat/alpha-frontend-ux-redesign` (develop ベース)
- **PR target**: `--base develop` 必須
- **PR完了条件**: CI green + code-reviewer LGTM + **フロントエンドエンジニア (takegg0311 or NKMAK) のレビュー必須** (`MEMORY.md` ルール)
- **コミット粒度**: タスク A/B/C/D を分けて 4 commit、最終 1 PR に統合
- **`pnpm-lock.yaml`** 変更時は VRM 手動確認も必要 (`MEMORY.md`)

### 触ってはいけない領域

- `backend/` 全般 (Codex が並行で触る)
- `frontend/vercel.json` (PR #637 で完了済、追加変更不要)
- `frontend/src/app/components/CharacterAvatar.tsx` の position 補正 (PR #639 で `+0.15` 復元済、回帰禁止)
- 既存の **PR #639 で動作確認済の Safari MediaRecorder 起動経路** (gesture 内 sync init は維持)
- `frontend/e2e/voice-live.spec.ts` および nightly workflow (`.github/workflows/voice-e2e-nightly.yml`) — `BACKEND_API_KEY` secret 関連の改修禁止

### live 検証フロー (PR マージ前必須)

1. PR push → Vercel Preview deploy
2. Preview URL で iPhone Safari / Pixel Chrome / iPad で **以下 3 ケース実機確認**:
   - Welcome → 音声応対 → 「営業時間は？」 → filler → 主応答 (体感 < 1s で audio start)
   - Welcome → 「会員証で受付」ボタン → カメラ起動
   - Slide guide ボタン → landscape 起動 → 5-page narration 完走
3. スクショ + 動画を PR description に貼付
4. nightly voice-e2e workflow を `gh workflow run voice-e2e-nightly.yml` で手動 dispatch、green 確認

---

## Cursor 並列実行戦略 (4 worker 推奨)

| Worker | タスク | 主編集ファイル | 想定工数 |
|---|---|---|---|
| W-A | Welcome voice-first | `page.tsx`, `VoiceInterface.tsx`, `MemberCardCapture.tsx` | 1.5 day |
| W-B | filler 並列再生 | `VoiceInterface.tsx`, `audio-queue.ts`, `emotion-manager.ts`, `api/voice/route.ts` | 1 day |
| W-C | SlideAgent autoplay | `ReceptionPdfGuide.tsx`, `parse-reception-narration-md.ts`, e2e | 1.5 day |
| W-D | getUserMedia 拒否 UI | `VoiceInterface.tsx`, `voice-recorder.ts`, `error-messages.ts`, e2e | 0.5 day |

**競合注意**: W-A / W-B / W-D が `VoiceInterface.tsx` を共有する。次の順序で逐次マージ推奨:
1. W-D (拒否 UI) ← 触る範囲が catch ブロック中心で最小
2. W-B (filler) ← STT 完了 hook を追加
3. W-A (Welcome) ← 全体 step ロジックを書き換え (W-B/W-D の追加を取り込む)
4. W-C (SlideAgent) ← 別ファイル、並行可能

または **1 worker に逐次実行** させても合計 4-5 day なので OK。

---

## Cursor 工数見積

| タスク | 工数 |
|---|---|
| A. Welcome voice-first | 1.5 day |
| B. filler 並列再生 | 1 day |
| C. SlideAgent autoplay + e2e | 1.5 day |
| D. getUserMedia 拒否 UI | 0.5 day |
| 統合テスト + 実機検証 + レビュー対応 | 1 day |
| **合計** | **約 5.5 day** |

## Cursor ハンドオフ実行 (terisuke 手元用)

Cursor 起動後、本ファイルを Composer に投げる:

```
@docs/handoffs/alpha-codex-and-cursor-handoffs-2026-05-01.md

Part 2 (Cursor) のタスク A〜D を順に並列 worker で実装してください。
ブランチは feat/alpha-frontend-ux-redesign、--base develop で PR 作成。
CI green + フロントエンジニア review 必須、merge は terisuke 承認後。
```

---

## 並列実行の同期ポイント

| ステップ | 内容 |
|---|---|
| 1 | Codex Part 1 タスク 3 (`/api/voice/filler` 新設) を **最優先** で実装 → develop merge |
| 2 | Cursor Part 2 タスク B はモックで先行着手、Codex タスク 3 merge 後に実エンドポイントに切替 |
| 3 | Cursor Part 2 タスク A/C/D は Codex 完了を待たず並行実装可 |
| 4 | Codex Part 1 全完了 + Cursor Part 2 全完了後、`alpha-live-verification.yml` を `--all-suites` で 1 回 dispatch、緑なら #614 に GO 候補コメント |
| 5 | 現地 2h kiosk run (#585) と 127 ケース RAGAS 完走 (#583) は **本ハンドオフのスコープ外**、別途 terisuke が手配 |

---

## 実装完了 — Codex Part 1 (2026-05-01)

### 実装コミット

- タスク 1 (#617 stale request_type): `41dc6a4`
- タスク 2 (#618 general_knowledge 軽量化 + web_search 厳格化): `c49ff15`
- タスク 3 (#610 BE /api/voice/filler): `0a0b15d`
- タスク 4 (#613 observability): `5db355c`

### Test 結果

- `cd backend && ruff check .` — pass
- `cd backend && black --check .` — pass
- `cd backend && pytest -m 'not ragas and not slow' --tb=short -q` — pass
  (`3088 passed, 226 skipped, 57 deselected`)
- filler static catalog: `backend/static/fillers/*.wav` 40 files generated

### PR / live 検証

- PR URL: `PENDING_PR_URL`
- alpha-live-verification.yml run URL: staging deploy / workflow dispatch 待ち

### Operationally Ready 備考

- Env vars / secrets: 新規必須 env var なし。API key は既存 `API_SECRET_KEY` を継続利用。
- CORS: 既存 `X-Request-ID` allowed header を継続利用。新 endpoint は既存 FastAPI CORS 下。
- MIME / assets: filler response `audioFormat=audio/wav`、static WAV catalog 40 files committed。
- Permissions / IAM: 新規権限なし。
- Schedulers / workflows / migrations / Terraform: 変更なし。
- Docker/runtime: `backend/scripts/generate_fillers.py` は PiperPlus が無い環境では有効な fallback WAV を生成。
