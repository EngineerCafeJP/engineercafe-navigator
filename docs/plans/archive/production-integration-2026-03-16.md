> Status: completed (2026-05-18); archived by FU-29 and superseded by `docs/plans/wave3-engineer-handoff-master-2026-05-18.md`.

# Production Integration Plan — 2026-03-16

## Goal

フロントエンド（Vercel）→バックエンド（Cloud Run）のプロキシ統合を完全に機能させ、
デプロイ済みUIから全機能が動作する状態にする。

---

## Wave 1: BROKEN修正 — プロダクション動作の復旧 ✅ COMPLETE

**完了日**: 2026-03-16
**PRs**: #262, #266, #268, #269
**Issues Closed**: #257, #258, #263, #264, #267

### Task 1.1: Vercel環境変数設定 (#264) ✅
- [x] `BACKEND_API_URL` / `BACKEND_API_KEY` Vercelに設定
- [x] localhost fallback 削除（PR #266）
- [x] Vercel CI/CD prod deploy 追加（PR #268）
- [x] VERCEL_TOKEN GitHub Secrets 登録
- [x] 疎通確認: Chat API, Character API, Knowledge API 全OK

### Task 1.2: /api/character GET 契約修正 (#263-1) ✅
- [x] supported_features action追加、manifest.json読み込み + fallback
- [x] regression test追加

### Task 1.3: 受付フロー triggerType 修正 (#263-2) ✅ (PR #266)

### Task 1.4: Marp audioResponse 修正 (#263-3) ✅ (PR #266)

### Task 1.5: DB接続プール修正 (#267) ✅ (PR #269)
- [x] ResilientAsyncPostgresSaver with AsyncConnectionPool
- [x] alist async generator retry (CRITICAL code review fix)
- [x] stale_pool race condition guard
- [x] Cloud Run cold start verified

### Task 1.3: 受付フロー triggerType 修正 (#263-2)
- [ ] `useReception.ts` の `triggerType='manual'` → backend許可値に変更
  - `button_press` が最も近い代替
- [ ] `ReceptionPanel.tsx` のdefault triggerTypeも修正
- [ ] 動作確認: 受付開始→応答→完了の一連フロー

### Task 1.4: Marp audioResponse 契約修正 (#263-3)
- [ ] `MarpViewer.tsx` の `audioResponse` 参照を修正
  - backend `/api/slides` のレスポンス構造に合わせる
  - またはナレーション再生を別経路（TTS API直接呼び出し）に変更
- [ ] 動作確認: スライド表示 + ナレーション

---

## Wave 2: 安定化 — 契約整合性 + env最適化

**目標**: WARNING級の不整合をゼロにし、env管理を完全に整理
**Issue**: #261 (env最適化), #259 (VRM Animation), #265 (route移行), #272 (CSP)
**開始日**: 2026-03-17
**PRマージ済み**: #260 (VRM修正), #271 (VRM表情統合+happy誤発火), #273 (Swagger CSP)

### Task 2.1: env深層最適化 (#261) ✅ DONE
**完了**: PR #274 (2026-03-18)
- [x] frontend全ファイルをgrepし、実際に使用されているenv変数を特定
- [x] `frontend/.env.example` から未使用変数を削除（Google Cloud, NextAuth, Gemini, OPENAI等）
- [x] `frontend/src/lib/env.ts` required→BACKEND_API_URL/KEY、未使用optional削除
- [x] `backend/.env.example` に不足変数を追加（API_SECRET_KEY, ALLOWED_ORIGINS, TTS, LangSmith, Discord）
- [x] README/docsにenv変更を記載（backend/README.md, frontend/CLAUDE.md）

### Task 2.2: VRM Animation プルダウン修正 (#259) ✅ DONE
**完了**: PR #260 (2026-03-17) + PR #271 (VRM表情統合)
- [x] VRMAファイル差し替え（Mixamoアニメーション5種追加）
- [x] プルダウン表示修正（APIレスポンス正規化）
- [x] VRM表情・リップシンク統合
- [x] エラー時 happy 誤発火修正

### Task 2.3+2.4: route移行 + 未露出endpoint露出 (#265) ✅ DONE
**完了**: PR #276 (2026-03-18)
- [x] `/api/admin/knowledge/editor-config` proxy route追加
- [x] `/api/admin/stt/vocabulary/test` proxy route追加（`?action=test`でルーティング）
- [x] `knowledge.ts` client をeditor-config endpointに切り替え
- [ ] `/api/calendar` → backend endpoint未実装のため保留（将来対応）

### Task 2.5: voice/slides/qa GET契約修正 ✅ DONE
**完了**: PR #275 (2026-03-18)
- [x] 共通ヘルパー `backend-error-response.ts` 追加（6 route適用）
- [x] backend 4xx→500変換を修正（元のステータスコードを保持）
- [x] `/api/slides` GET ハードコード削除（backend GETなし確認済み）
- [x] regression test追加（`api-proxy-contract.test.ts`）

### Task 2.6: Swagger UI CSP修正 (#272) ✅ DONE
**完了**: PR #273 (2026-03-17)
- [x] `/docs` `/redoc` 限定でCSP緩和（cdn.jsdelivr.net許可）

---

## Wave 3a: プロダクション安定化 — CRITICAL/HIGH修正 ✅ COMPLETE

**完了日**: 2026-03-18 (PR #278 マージ)
**目標**: プロダクトレビューで発見されたCRITICAL/HIGH問題を修正し、CI/CDパイプラインを安全にする
**開始日**: 2026-03-18
**根拠**: code-explorer全体レビュー (2026-03-18実施)

### Task 3a.0: CI frontend-deploy-production ジョブ削除 ✅ DONE
- [x] Vercel Git連携に移行 → CIジョブ不要化
- [x] ci.yml から削除 (2026-03-18)
- [x] Vercel Dashboard で Production Branch = `develop` に設定 (Deploy Hook)

### Task 3a.1: CI `--set-secrets` → `--update-secrets` 修正 [CRIT-1] ✅ DONE
- [x] `ci.yml` の `--set-secrets` → `--update-secrets` に変更
- [x] `API_SECRET_KEY` を Secret Manager に移行し `--update-secrets` リストに追加
- [x] CORS `ALLOWED_ORIGINS` を `--update-env-vars` に追加（CRIT-2も同時修正）
- [x] CI deploy後のsmoke testを認証付き（`X-API-Key`ヘッダー）に変更
- [x] 手動deploy → traffic切替 → ブラウザからのCORS確認

### Task 3a.2: CORS デフォルトオリジン修正 [CRIT-2] ✅ DONE
- [x] `backend/main.py` ALLOWED_ORIGINS のデフォルトを Vercel URL に変更
- [x] Cloud Run env vars に `ALLOWED_ORIGINS` を追加

### Task 3a.3: `backendFetch` タイムアウト追加 [HIGH-1] ✅ DONE
- [x] `frontend/src/lib/api/backend-proxy.ts` に `AbortSignal.timeout(35_000)` 追加
- [x] `backend/workflows/main_workflow.py` の `ainvoke` を `asyncio.wait_for(..., timeout=30)` でラップ
- [x] テスト追加

### Task 3a.4: admin editor-config N+4クエリ最適化 [HIGH-2] ✅ DONE
- [x] `backend/api/knowledge.py` の4連続SELECT → `SELECT DISTINCT` 1クエリに統合
- [x] `asyncio.to_thread()` でevent loop非ブロック化（MED-3も同時修正）

### Task 3a.5: `invoke_agent` session_id null-guard [HIGH-3] ✅ DONE
- [x] `backend/main.py` invoke_agent: `body.session_id or str(uuid4())`

### Task 3a.6: `BACKEND_API_KEY` 起動時検証 [HIGH-4] ✅ DONE
- [x] `frontend/instrumentation.ts` で `validateServerEnv()` を呼び出し、未設定時はfail-fast

### Task 3a.7: `ci-success` ゲート修正 [HIGH-5] ✅ DONE
- [x] `ci-success` のconditionを修正: `skipped` 許容、`failure`/`cancelled` でfail

### Task 3a.8: Alert webhook Zod検証 [MED-2] ✅ DONE
- [x] `frontend/src/app/api/alerts/webhook/route.ts` に Zod schema追加
- [x] `processAlert` 呼び出し前にバリデーション

---

## Wave 3b: プロダクション品質修正 + P1改善 (2026-03-21 開始)

**目標**: 本番ブロッカー修正（embedding/ffmpeg/TAVILY）→ P1品質改善
**Issue**: #279 (RAG一貫性), #189 (音声テスト), #265 (calendar), #139 (E2E), #141/#137 (RAG品質), #138 (多言語), #140 (負荷テスト)
**開始日**: 2026-03-21

### Wave 3b-0: 本番ブロッカー修正（独立・並列実行）

#### Task 3b-0a: knowledge_base embedding 80件一括再生成 (#279 根本修正)
**担当**: Claude Code（本番API操作）
**根本原因**: migration `20260214000001` が content_embedding カラムを DROP→再CREATE したため全80件のembeddingがNULLに
- [ ] バッチスクリプトで PUT /api/knowledge/{id} → embedding自動再生成
- [ ] 再生成後に search_knowledge_base RPC が正常動作することを検証
- [ ] #279 の根本原因（embedding NULL）を解消

#### Task 3b-0b: Dockerfile に ffmpeg 追加 (#189 blocker)
**担当**: Agent Team (worktree)
**根本原因**: pydub の WebM→WAV変換が ffprobe/ffmpeg に依存するが Dockerfile に未インストール
- [ ] `backend/Dockerfile` の apt-get install に `ffmpeg` 追加
- [ ] CI/CD で新イメージビルド・デプロイ

#### Task 3b-0c: TAVILY_API_KEY を Cloud Run に追加
**担当**: Claude Code（GCP操作）
- [x] GCP Secret Manager に TAVILY_API_KEY 作成
- [x] Cloud Run service account に secretAccessor 付与
- [x] `gcloud run services update --update-secrets` で追加 → rev 00038 稼働
- [ ] CI deploy コマンドにも `TAVILY_API_KEY=TAVILY_API_KEY:latest` 追加

#### Task 3b-0d: Cloudflare 残骸削除 + Vercel 重複プロジェクト整理
**担当**: Agent Team + 先輩（Vercelダッシュボード手動操作）
- [ ] `frontend/.open-next/` ディレクトリ削除（ローカルビルド残骸）
- [ ] Vercel 重複プロジェクト (`engineer-cafe-navigator2025`, `engineer-cafe-navigator`) 削除
- [ ] 手順書: `~/Desktop/vercel-cleanup-guide.md` に作成済み

#### Task 3b-0e: 開発環境セットアップガイド (#189 チームサポート)
**担当**: Agent Team
- [ ] `docs/setup-guide.md` 作成（日本語）
- [ ] 前提条件、backend/frontend セットアップ、env vars、トラブルシューティング

### Wave 3b-1: route移行 + 品質改善

#### Task 3b.0: calendar backend endpoint + proxy (#265 残)
**担当**: Codex CLI（経路C）
- [ ] backend に `/api/calendar` GET エンドポイント実装（既存 `calendar_service.py` を活用）
- [ ] frontend `/api/calendar/route.ts` を `backendFetch('/api/calendar')` にプロキシ化
- [ ] `GOOGLE_CALENDAR_ICAL_URL` を frontend から完全削除（backend側で管理）
- [ ] #265 クローズ

### Task 3b.1: Playwright E2E テスト整備 (#139)
**担当**: Codex CLI（経路C）— テスト作成 / Claude Code — テスト実行
- [ ] 基本シナリオ: ページ表示 → チャット → 応答表示
- [ ] VRMキャラクター表示確認
- [ ] スライド表示・ナビゲーション
- [ ] admin ナレッジ管理CRUD
- [ ] CI統合（playwright.yml）

### Task 3b.2: RAG precision 改善 (#141)
**担当**: Claude Code（対話的）
- [ ] context_precision ベースライン測定
- [ ] ばらつき原因分析（検索クエリ、embedding品質、チャンク戦略）
- [ ] RAGAS評価パイプライン実行
- [ ] 改善パラメータ適用

### Task 3b.3: answer_correctness 0.7+ (#137)
**担当**: Claude Code（対話的）
- [ ] ベースライン測定
- [ ] プロンプト・検索パラメータ調整
- [ ] RAGAS再評価で0.7+確認

### Task 3b.4: 多言語対応改善 (#138)
**担当**: Claude Code（対話的）
- [ ] 英語応答品質の現状測定
- [ ] 言語検出精度の確認
- [ ] プロンプト多言語対応

### Task 3b.5: 負荷テスト (#140)
**担当**: Codex CLI（経路C）
- [ ] k6/locust スクリプト作成
- [ ] チャットAPI、音声API の同時接続テスト
- [ ] ボトルネック特定・レポート

---

## Issue Status Map (2026-03-21 更新)

| Issue | Wave | Status | 備考 |
|-------|------|--------|------|
| #257 | W1 | ✅ Closed | バックエンドデプロイ完了 |
| #258 | W1 | ✅ Closed | #262で部分完了、残は#261で完了 |
| #259 | W2 | ✅ Closed | PR #260 VRM Animation |
| #261 | W2 | ✅ Closed | PR #274 env深層最適化 |
| #263 | W1 | ✅ Closed | PR #266 API契約不一致（3件） |
| #264 | W1 | ✅ Closed | PR #266 Vercel→Cloud Run認証 |
| #265 | W3b | 🔧 Open | route移行（admin完了、calendar→Codex CLI実行中） |
| #270 | W2 | ✅ Closed | PR #271 happy誤発火 |
| #272 | W2 | ✅ Closed | PR #273 Swagger CSP |
| #279 | W3b | 🔧 NEW | RAG Knowledge Base 検索・保存の一貫性問題（embedding NULL→再生成中） |
| — | W3a | ✅ PR#278 | CI `--set-secrets`→`--update-secrets` [CRIT-1] |
| — | W3a | ✅ PR#278 | CORS デフォルトオリジン修正 [CRIT-2] |
| — | W3a | ✅ PR#278 | backendFetch/ainvoke タイムアウト [HIGH-1] |
| — | W3a | ✅ PR#278 | editor-config N+4クエリ [HIGH-2] |
| — | W3a | ✅ PR#278 | invoke_agent session_id null-guard [HIGH-3] |
| — | W3a | ✅ PR#278 | BACKEND_API_KEY 起動時検証 [HIGH-4] |
| — | W3a | ✅ PR#278 | ci-success ゲート修正 [HIGH-5] |
| — | W3a | ✅ PR#278 | Alert webhook Zod検証 [MED-2] |
| — | W3b | 🔧 進行中 | Dockerfile ffmpeg追加（#189 blocker） |
| — | W3b | ✅ DONE | TAVILY_API_KEY Cloud Run追加（rev 00038） |
| #209 | — | ⏳ Backlog | テキストバブル表示 |
| #211 | — | ⏳ Backlog | 対応VRMAの追加（PR #260で部分完了） |
| #192-189 | W3b | ⏳ テスト中 | 統合テスト（Jun #189テスト報告あり） |
| #165 | — | ⏳ Backlog | Reception境界分析 |
| #141 | W3b | 📋 P1 | RAG precision（embedding再生成後に着手） |
| #140 | W3b | 📋 P1 | 負荷テスト |
| #139 | W3b | 📋 P1 | E2Eテスト |
| #138 | W3b | 📋 P1 | 多言語対応 |
| #137 | W3b | 📋 P1 | answer_correctness |
| #128 | — | ⏳ P1 研究 | デバイス検知 |
| #117 | — | ⏳ P0 | 自律受付フロー（W1で部分対応） |
| #114 | — | ⏳ P2 | 満足度フィードバック |
| #113 | — | ⏳ P2 | イベント登録ガイド |

## 並列実行戦略

```
Wave 1 (BROKEN修正) ✅ COMPLETE
Wave 2 (安定化)     ✅ COMPLETE

Wave 3a (プロダクション安定化) ── 2026-03-18 開始
├── Task 3a.0 (CI cleanup)        ─── ✅ DONE
├── Task 3a.1 (--set-secrets fix) ─── Claude Code（CRIT-1+CRIT-2、即対応）
├── Task 3a.3 (timeout)           ─── Codex CLI（並列）
├── Task 3a.4 (N+4 query)         ─── Codex CLI（並列）
├── Task 3a.5 (session_id guard)  ─── Codex CLI（並列）
├── Task 3a.6 (env validation)    ─── Codex CLI（並列）
├── Task 3a.7 (ci-success gate)   ─── Claude Code（3a.1と同時）
└── Task 3a.8 (webhook Zod)       ─── Codex CLI（並列）

Wave 3b (P1改善) ── Wave 3a完了後
├── Task 3b.0 (calendar proxy)    ─── Codex CLI（独立、先行可）
├── Task 3b.1 (E2E)               ─── Codex CLI + Claude Code
├── Task 3b.2 (RAG precision)     ─── Claude Code (対話的)
├── Task 3b.3 (correctness)       ─── Claude Code (対話的、3b.2と直列)
├── Task 3b.4 (多言語)            ─── Claude Code (対話的)
└── Task 3b.5 (負荷テスト)        ─── Codex CLI（3b.1完了後）
```

## プロダクトレビュー追跡 (2026-03-18実施)

レビュー手法: code-explorer エージェントによるフルスキャン

### 全指摘一覧

| ID | 深刻度 | 領域 | 説明 | Wave | 対応状況 |
|---|---|---|---|---|---|
| CRIT-1 | CRITICAL | CI/CD | `--set-secrets` が `API_SECRET_KEY` を消す | 3a.1 | 📋 |
| CRIT-2 | CRITICAL | CORS | デフォルトオリジンが workers.dev (旧CF) | 3a.2 | 📋 |
| HIGH-1 | HIGH | Integration | backendFetch/ainvoke にタイムアウトなし | 3a.3 | 📋 |
| HIGH-2 | HIGH | Database | editor-config N+4 unbounded クエリ | 3a.4 | 📋 |
| HIGH-3 | HIGH | Backend | invoke_agent: nullable session_id の unsafe cast | 3a.5 | 📋 |
| HIGH-4 | HIGH | Security | BACKEND_API_KEY 未設定時サイレント失敗 | 3a.6 | 📋 |
| HIGH-5 | HIGH | CI/CD | ci-success が skipped を pass 扱い | 3a.7 | 📋 |
| MED-1 | MEDIUM | Observability | console.error 17箇所、構造化ログなし | Backlog | ⏳ |
| MED-2 | MEDIUM | Security | Alert webhook 未検証で emergencyShutdown | 3a.8 | 📋 |
| MED-3 | MEDIUM | Performance | sync Supabase calls blocking event loop | 3a.4 | 📋 (HIGH-2と同時) |
| MED-4 | MEDIUM | Reliability | Upload proxy タイムアウトなし | Backlog | ⏳ |
| MED-5 | MEDIUM | Reliability | Calendar proxy タイムアウト・Content-Type未検証 | 3b.0 | 📋 (calendar移行時) |
| MED-6 | MEDIUM | Config | ENVIRONMENT=production だがコメントは staging | 3a.1 | 📋 (コメント修正) |
| MED-7 | MEDIUM | Security | local toErrorBody が payload spread で内部漏洩 | Backlog | ⏳ |
| LOW-1 | LOW | CI/CD | Deploy失敗が未通知 | Backlog | ⏳ |
| LOW-2 | LOW | UX | Reception start body 未検証 | Backlog | ⏳ |
| LOW-3 | LOW | Correctness | ocr/route.ts response.ok 未チェック | Backlog | ⏳ |
| LOW-4 | LOW | Config | BACKEND_API_KEY required in schema but optional in usage | 3a.6 | 📋 (同時修正) |
| LOW-5 | LOW | Security | /health が infra state を無認証公開 | Backlog | ⏳ (意図的) |
| LOW-6 | LOW | Reliability | Reception session store 非レプリケーション | Backlog | ⏳ |

### アーキテクチャ観察（将来対応）
- Mastra agents (`frontend/src/mastra/`) はdead weight — 本番バンドルから除外推奨
- `should_continue_or_end` は常にEND — no-opプレースホルダー
- keyword-based fast routing (200行超) はデータ駆動に移行推奨
