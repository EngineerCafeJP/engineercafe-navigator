# ADR-025: Frontend Proxy Deletion → Vite Migration

## Status

Accepted (2026-05-17) — 実装は次セッション以降。ADR-021 を Phase に分解した operational ADR。

## Context

[ADR-021](021-frontend-backend-separation-before-react-vite.md) で「Vite 化より先に FE/BE 分離を行う」と Accepted 済み。本 ADR はその方針を **Phase 別実装計画に分解** し、ADR-023 (Routing + Critic) + ADR-024 (Memory + Reception) との依存タイミングを定義する。

### 2026-05-17 時点の実数（[docs/plans/post-adr023-investigation-2026-05-17.md](../plans/post-adr023-investigation-2026-05-17.md) より）

| 項目 | 値 |
|---|---|
| `frontend/src/**/*.{ts,tsx}` ファイル数 (excl. tests) | 178 |
| 総行数 | 35,348 |
| `frontend/src/app/api/**/route.ts` 数 | **28** (ADR-021 時点 29 から 1 減) |
| Top 3 巨大コンポーネント | `VoiceInterface.tsx` 1,824 / `CharacterAvatar.tsx` 1,555 / `ReceptionPdfGuide.tsx` 1,304 |
| Next.js | 15.3.9 (App Router) |
| React | 19.1.0 |
| Tailwind | 3.4.17 (CLAUDE.md: v4 にしない) |

### 28 API route handlers の分類

```
frontend/src/app/api/
├── admin/knowledge/*        (8 routes)  ← admin auth migration が前提
├── alerts/webhook            (1)
├── animations                (1)
├── backgrounds               (1)
├── calendar                  (1)
├── character                 (1)
├── cron/update-knowledge-base (1)        ← BE cron に移譲推奨
├── health/knowledge          (1)
├── monitoring/*              (2)
├── ocr                       (1)
├── qa                        (1)        ← Issue #358 既存タスク
├── reception/*               (5)        ← ADR-024 Phase A4 で 2 routes 削除予定
├── slides                    (1)
└── voice/*                   (2)
```

### ADR-023 / ADR-024 との依存関係

- ADR-023 Phase 0 で BE が **LangSmith runtime guardrails** を持つ
- ADR-024 Phase A1-A3 で BE が **memory ownership** を固める
- BE responsibilities が増えるタイミングで FE proxy 削除を進めると、`/api/qa` / `/api/voice` / `/api/reception/*` の直接呼び出しが楽になる
- Vite 移行は **proxy が 0 になってから判断**（kiosk 用途で SEO 不要 = SSR 不要なので Vite SPA が筋）

参考: [Designrevision: Vite vs Next.js 2026](https://designrevision.com/blog/vite-vs-nextjs), [TECHSY: Next.js vs React + Vite 2026](https://techsy.io/en/blog/nextjs-vs-react-vite)

## Decision

ADR-021 の Accepted 方針を **4 Phase に分解** し、ADR-024 と並列実行する。Phase B3 (Vite 移行) は B0-B2 完了後に**改めて判断**する（自動的に走らせない）。

### D1: Phase B0 — `/api/qa` proxy 廃止

#### スコープ
- 既存タスク [Issue #358](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/358) の完遂
- [`frontend/src/app/api/qa/route.ts`](../../frontend/src/app/api/qa/route.ts) 削除
- 各 caller を直接 BE `/api/chat` 呼び出しに書き換え
- BE 側で kiosk-origin token 認証配線 (短寿命 token を frontend が取得する設計)

#### 完了条件
- `/api/qa` proxy ファイル削除
- Playwright E2E green
- LangSmith trace で `/api/chat` 直叩きが確認できる (ADR-023 Phase 0 後)
- CSP / CORS が backend 単体で完結

### D2: Phase B1 — `/api/voice/*` + `/api/reception/*` proxy 廃止

#### スコープ
- [`frontend/src/app/api/voice/route.ts`](../../frontend/src/app/api/voice/route.ts) + [`voice/filler/route.ts`](../../frontend/src/app/api/voice/filler/route.ts) 削除
- reception proxy (ADR-024 Phase A4 で respond/complete は削除済み):
  - [`frontend/src/app/api/reception/start/route.ts`](../../frontend/src/app/api/reception/start/route.ts) 削除
  - [`frontend/src/app/api/reception/sensor-status/[…]/route.ts`](../../frontend/src/app/api/reception/sensor-status/route.ts) 削除
  - sensor-trigger / status も同様
- STT / TTS のタイムアウト挙動 + CORS を BE 直叩きで再計測
- BE Cloud Run の egress 帯域確認

#### 完了条件
- voice + reception proxy ファイル削除 (5 routes 想定)
- Playwright voice-live E2E green ([`.github/workflows/voice-e2e-nightly.yml`](../../.github/workflows/voice-e2e-nightly.yml))
- p95 latency 改善 or 維持

### D3: Phase B2 — `/api/admin/knowledge/*` proxy 廃止

#### スコープ
- 前提: admin auth migration (admin token / session 設計を BE 側で確立)
- [`frontend/src/app/api/admin/knowledge/**/*.ts`](../../frontend/src/app/api/admin/knowledge/) (8 routes) 削除
- アップロード / preview / categories / templates / editor-config を BE 直叩きに
- 既存 admin UI コンポーネント ([`frontend/src/app/(admin)/admin/knowledge/`](../../frontend/src/app/(admin)/admin/knowledge/)) を BE API client 経由に書き換え

#### 完了条件
- admin/knowledge proxy ファイル全削除 (8 routes)
- admin auth migration の DEMO / 試験運用済
- knowledge 投入 / preview の手動テスト pass

### D4: Phase B3 — 残 proxy 棚卸し + Vite 移行可否判断

#### スコープ
- 残 proxy (alerts / animations / backgrounds / calendar / character / cron / health / monitoring / ocr / slides) を棚卸し
- 削除可能なものは削除、BE 直叩きが現実的でないものは「Next を保持する積極理由」をドキュメント化
- proxy が **0 になった** or **保持理由が固定された** タイミングで:
  - bundle 計測スパイク (Vite 42KB vs Next 92KB ベンチマーク)
  - SSR / SEO 必要箇所の有無確認
  - kiosk / admin で異なる構成にする選択肢検討
- 結果を別 ADR (ADR-026 等) として起票して **Vite 移行可否を再判断**

#### 完了条件
- 残 proxy 数の最終確定
- Vite 移行可否判断レポート作成
- ADR-026 (Vite migration go/no-go) 起票

## Consequences

### Positive
- **BE が auth / CORS / rate-limit / API contract を所有** = ADR-005 "Backend-first logic" の完遂
- **proxy 削除で frontend が薄くなる** = 認知負荷低下、CI ビルド時間短縮
- **Vite 移行が「事故」ではなく「測定後の選択」**になる
- **ADR-024 Phase A4** とタイミング同期できる (reception/respond proxy も Phase A4 + B1 で同時削除)

### Negative
- proxy 削除の度に BE 側の auth / CORS 設計工数
- admin auth migration (Phase B2 前提) は別途設計コスト
- ローカル開発時の dev server 構成変更 (現状 Next で完結している)
- Vercel deploy の意義が薄れる → BE Cloud Run + 静的 SPA host への切り替え判断が必要に

### Risk Mitigation
| Risk | Mitigation |
|---|---|
| voice proxy 削除で CORS / timeout の細かい挙動が壊れる | Phase B1 で staging 1 週間 shadow 検証、Playwright voice-live で fail 検知 |
| admin auth migration が pending で Phase B2 着手不可 | Phase B2 着手前に admin auth ADR が Accepted されているか確認 |
| Vite 移行で kiosk の VRM + Canvas ロードに問題発生 | Phase B3 はあくまで判断、決定後別 ADR で実装。事前に bundle 計測 spike を必ず行う |
| Vercel 切り捨てで preview deploy が失われる | B3 で Vite + 別 host (Cloudflare Pages 等) を比較、preview 機能の代替を確保 |

## Rollout Plan

| Phase | 内容 | 期間 | 担当候補 | 完了条件 |
|---|---|---|---|---|
| **B0** | /api/qa proxy 廃止 (#358 完遂) | 3–5日 | frontend-developer + backend-developer | Playwright E2E green、`/api/chat` 直叩き確認 |
| **B1** | /api/voice + /api/reception proxy 廃止 | 1週間 | frontend-developer + backend-developer | voice-live E2E green、p95 latency 維持 |
| **B2** | /api/admin/knowledge proxy 廃止 | 1週間（admin auth migration 前提） | frontend-developer + backend-developer | admin auth migration DEMO、knowledge UI 動作確認 |
| **B3** | 残 proxy 棚卸し + Vite 判断 | 1週間 | architect + frontend-developer | Vite migration go/no-go レポート、ADR-026 起票 |

### Phase 別 PR 規律 (CLAUDE.md / ADR-023 / ADR-024 と同じ)
- ブランチ命名: `feat/fe-phaseB{N}-{slug}`
- 全 PR `--base develop`
- code-reviewer + Codex CLI 経路 A レビュー必須
- frontend PR は **frontend エンジニアのレビュー必須** ([MEMORY.md](../../) ルール)
- 各 Phase 完了時に `MEMORY.md` の Session Status 更新

## Alternatives Considered

### A1: Vite 移行を最優先に進める
**却下理由**: ADR-021 で既に「FE/BE 分離が先」と Accept 済み。proxy 28 ファイルが残るうちは Vite 化単体では削除サーフェスが消えない。先に proxy 削除を進めて初めて Vite の意味が出る。

### A2: Vite 移行を見送り、現状の Next を恒久維持
**保留**: B3 完了時に再判断。kiosk 用途で SSR / SEO 不要なら Vite SPA の方が bundle 軽い + host 自由度高。ただし VRM / Canvas / shadcn 等の動作影響が未測定なので決定はしない。

### A3: ADR-024 と同時並行ではなく順次進行
**却下理由**: ADR-024 Phase A4 で reception/respond proxy が削除されるタイミングが Phase B1 と重なる = 同時に進める方が手戻りが少ない。

### A4: 28 proxy を 1 PR で一括削除
**却下理由**: 1 PR = 1 意図 規約違反。auth / CORS / rate-limit のような cross-cutting concerns を 1 つずつ確認しながら進めるべき。

## Approvals

- Proposed: Claude Code (2026-05-17) — ADR-021 の operational 分解 + 2026/05 web research
- Accepted: Terada Kousuke (terisuke, 2026-05-17) — ADR-024 と同タイミングで起票・並列進行を選択

## References

### 本リポジトリ内
- [ADR-005: Backend-first logic](005-backend-first-logic.md) — 本 ADR の上位方針
- [ADR-021: Frontend/backend separation before React/Vite migration](021-frontend-backend-separation-before-react-vite.md) — 本 ADR が具体化する元 ADR
- [ADR-023: Semantic Router + LangGraph runtime self-evaluation](023-semantic-router-and-runtime-self-evaluation.md) — backend ownership 強化と同期
- [ADR-024: Memory & Reception Modernization](024-memory-and-reception-modernization.md) — Phase A4 が Phase B1 と reception proxy 削除で同期
- [docs/plans/post-adr023-investigation-2026-05-17.md](../plans/post-adr023-investigation-2026-05-17.md) — 本 ADR の根拠調査報告書
- [Issue #358](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/358) — Phase B0 の既存タスク
- [`.github/workflows/voice-e2e-nightly.yml`](../../.github/workflows/voice-e2e-nightly.yml) — Phase B1 の検証 gate

### 外部 (2026/05 時点)
- [Designrevision: Vite vs Next.js Complete Comparison (2026)](https://designrevision.com/blog/vite-vs-nextjs)
- [TECHSY: Next.js vs React + Vite 2026 — Need a Framework?](https://techsy.io/en/blog/nextjs-vs-react-vite)
- [Next.js: Migrating from Vite (official)](https://nextjs.org/docs/app/guides/migrating/from-vite)
- [Patterns.dev: React Stack Patterns 2026](https://www.patterns.dev/react/react-2026/)
