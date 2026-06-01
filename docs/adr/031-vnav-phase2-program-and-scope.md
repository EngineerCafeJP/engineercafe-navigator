# ADR-031: VNav (Virtual Navigator 2026) Phase 2 Program and Scope

## Status

Proposed (2026-06-01) — Phase 2「バーチャルナビゲーター」構築プロジェクトのプログラム ADR。コードネーム・スコープ・既存 ADR/Issue との関係を固定し、後続の個別 ADR (032+) と Epic の親とする。計画原案は [`docs/plans/phase2-virtual-navigator-recruitment-2026.md`](../plans/phase2-virtual-navigator-recruitment-2026.md)。

## Context

Phase 1（2025-10〜11 キックオフ／説明会）で立ち上げた EngineerCafe Navigator を、本番運用を見据えた次世代「バーチャルナビゲーター」へリプレースする大型フェーズを 2026 夏〜秋に段階始動する。目標は以下の通り。

1. **コスト構造の転換** — Cloud Run 常時起動（`engineer-cafe-backend` minScale=5・4vCPU/8Gi・CPU 常時割当、`piper-plus` minScale=2）のベースラインだけで月 ¥20 万規模（構成 × 公開単価からの試算、実請求額は未検証）。これをミニ PC／自前サーバー＋ローカル LLM へ移し、ランニングを電気代＋少額 API 従量へ圧縮する。
2. **受付体験の完全統合** — 来場者が「話しかける／会員証を見せる／NFC カードをかざす」だけで受付が完結する IoT × AI 受付。
3. **疎結合アーキテクチャ** — backend / frontend を API 契約で分離し、UI を React 軽量化や将来の Unity 等へ差し替え可能にする。

体制はトータル 12 名（Frontend 4 / Backend 6 / IoT 2）。コア（業務従事・有償）＋お手伝い（コミュニティ）のハイブリッド。

### 「Phase 2」命名衝突

「Phase 2」が 3 つの異なる意味で併存しており混乱必至:

1. **本プログラム** — Phase 2 バーチャルナビゲーター（本 ADR）。
2. **ADR-029 / Epic [#899](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/899)** — 「Phase 2 LangGraph BP」（LangGraph 1.0+ ベストプラクティス採用、ADR-023 同時着手スコープ）。
3. **Issue [#380](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/380)** — Wave 7 / Epic #376 由来の「Phase 2 研究スパイク」（D-RAG）。

### ADR-024 が残した宿題

[ADR-024](./024-memory-and-reception-modernization.md)（Accepted, 2026-05-17）は Phase A4 で受付 dead code を削除し `public.users` を作らず visits ベースに統一する一方、**「OCR / NFC / 会員番号機能の将来パスは別 ADR で議論」「未確定なら A4 を後ろ倒し」と明記**している。実コード確認（2026-06-01）では A4 が一部実行済み:

- 削除済: `identify_by_member_number` / `_get_user_profile*` / `respond_reception` / `complete_reception`
- 残存（stub）: [`identify_by_nfc`](../../backend/services/visitor_identification_service.py:45)（`nfcs` テーブルが無く実質機能しない）
- 配線済: `trigger_type='nfc'` と `nfc_id`（[`backend/domain/reception/events.py:25`](../../backend/domain/reception/events.py:25), [`backend/workflows/reception_workflow.py:292`](../../backend/workflows/reception_workflow.py:292)）

本 ADR は ADR-024 が指す「別 ADR」そのものであり、これらの将来パスに回答する。

## Decision

### D1: コードネームを VNav に統一する

本プログラムを **VNav (Virtual Navigator 2026)** と呼称し、関連 Issue/ADR/ブランチに `[VNav]` を冠する。内部ステージは **VNav Stage A / B / C**（数字 + α/A の混在を避ける）。これにより上記命名衝突を解消する。ADR-029 系・#380 系の「Phase 2」は別物として扱う（#899 にはリネーム提案コメントを付す）。

### D2: VNav スコープを 10 項目で固定する

| # | スコープ | 既存カバレッジ | VNav での扱い |
|---|---|---|---|
| ① | 受付システムとの DB 統合（会員特定） | 🔶 ADR-024（会員 identify は削除） | 後続 ADR-032 で会員 DB スキーマ・特定フローを定義 |
| ② | 音声入出力の精度・速度向上 | ✅ #611 #584 #483（ただし一部クラウド前提） | ローカル STT/TTS 最適化 Issue を追加 |
| ③ | OCR 会員証認識の精度・速度向上 | ❌ ADR/Issue 共にゼロ | **新規 Issue 必須（最優先空白）** |
| ④ | NFC 発火（実機統合） | 🔶 ADR-030（nfc event 種別なし）/ stub のみ | ADR-030 へ `nfc` event 追加 + 実機統合 Issue |
| ⑤ | 混雑状況センシング | ❌ ADR/Issue 共にゼロ | **新規 ADR + Issue 必須** |
| ⑥ | Discord / X 連携 | 🔶 #113 一部 | 新規 Issue 必須 |
| ⑦ | Auth（会員/visitor 認証） | 🔶 ADR-021/025（API auth のみ） | 後続 ADR-032 に同梱 |
| ⑧ | フロントエンドスタック分離 | ✅ ADR-021 + ADR-025 | 実行 Issue 化 + Unity 選択肢を B3 判断に追加 |
| ⑨ | ローカル LLM / オンプレ移行 | 🔶 ADR-028（Proposed・portable のみ） | 後続 ADR-033 + ADR-028 承認先行 |
| ⑩ | オンボーディング / お作法 | ✅ CLAUDE.md / coding-style / ADR-008 | 専用 ADR 不要（任意で onboarding Issue） |

### D3: アーキテクチャ方針

- **LLM**: ローカルファースト＋クラウド補完。既存の `FAST_LLM_PRIMARY/FALLBACK/TERTIARY`・`DEEP_REASONING_MODEL`・`CEREBRAS_*` の二段ルーティングをそのまま活用し、FAST 層をローカル LLM（Ollama / llama.cpp 等）へ、DEEP 層はクラウド（OpenRouter / Cerebras）維持。
- **Embedding**: `text-embedding-3-small`（1536 次元）固定の制約により、ローカル化は `knowledge_base` 全件再埋め込みを伴うため VNav Stage C 以降で評価。当面クラウド維持。
- **Frontend 分離**: [ADR-021](./021-frontend-backend-separation-before-react-vite.md) / [ADR-025](./025-frontend-proxy-deletion-and-vite-migration.md) の proxy 削除 → スタック判断の順序を踏襲。将来 Unity 化を B3 go/no-go の選択肢に加える。
- **オンプレ基盤**: [ADR-028](./028-oss-portable-observability-and-infrastructure.md) の portable infra（docker-compose self-host / GCP SDK 除去 / OTel）を前提とする。ADR-028 は Proposed のため、VNav 着手前に承認を先行させる。

### D4: ADR-024 の OCR/NFC/会員番号「別 ADR」宿題に回答する

VNav はスコープ ①③④⑦ でこれらの機能を**本実装する**。したがって:

- ADR-024 A4 で削除された会員特定機能（`identify_by_member_number` 系）は、VNav では会員 DB を伴う形で**再導入**する（旧 `public.users` 直叩きの復活ではなく、後続 ADR-032 で再設計）。
- stub の `identify_by_nfc` は VNav で**本実装へ昇格**する。
- ADR-024 A4 の**さらなる削除（NFC stub 等）は VNav スコープ確定まで保留**する（ADR-024 自身の「未確定なら A4 後ろ倒し」に従う）。

### D5: 後続 ADR / Epic の付番

README の採番規約（027 以降運用）に従い、VNav 個別 ADR は **032 以降**で起票:

- **ADR-032（予定）**: 会員 DB・受付 DB 統合 + 会員/visitor Auth（スコープ ①⑦）
- **ADR-033（予定）**: オンプレ移行 — ローカル LLM 統合 + Supabase→セルフホスト Postgres データ移行（スコープ ⑨）
- **ADR-034（予定・要否判断）**: NFC カード ID 体系 + ADR-030 event 契約拡張（スコープ ④）／混雑センシング & プライバシー方針（スコープ ⑤）

Epic は GitHub に `[Epic][VNav]` で起票し、本 ADR と計画原案を親とする。

### D6: 既存 Issue の VNav 整合

- **#489（Cloud Monitoring ダッシュボード）**: ADR-028 の OTel/Grafana portable 化と方向性がズレるため、VNav 着手時に Grafana/Prometheus 前提へ読み替えるか再評価。
- **#611（動的 filler / Cerebras クラウド）**: FAST 層ローカル化方針（D3）と整合させ、ローカル filler 生成を選択肢に再検討。
- **#114（来訪者満足度フィードバック）/ #113（イベント参加ガイド）**: P2 post-alpha 棚上げから、VNav の FE-4 管理画面（⑤可視化）・⑥連携の正式スコープへ昇格候補。

## Consequences

### Positive

- 「Phase 2」3 重定義を VNav コードネームで解消し、Issue/ADR/ブランチが一意に追える。
- ADR-024 が先送りした OCR/NFC/会員番号の宿題に正式回答し、削除→再実装の手戻りを防ぐ（A4 保留）。
- スコープ別カバレッジを固定したことで、空白（③⑤⑥）と要承認（ADR-028）が可視化され、新規起票漏れを防げる。
- 既存の FAST/DEEP 二段 LLM 設計・ADR-021/025 の FE 分離設計を再利用でき、設計の連続性を保てる。

### Negative

- 後続 ADR-032/033 と新規 Issue 群が確定するまで、VNav の実装スコープは「枠」のみで詳細未確定。
- ADR-024 A4 を保留することで、reception 周りの dead code 整理が一部据え置きになる。
- オンプレ運用責任（死活監視・バックアップ・物理障害・ネットワーク）がチーム側へ移り、IoT 枠の負荷が増す。

## Open Questions（要相談・admin 確認待ち）

1. オンプレ・ハードの具体（GPU 集中 1 台 / CPU ミニ PC 複数台 / 中古サーバー、予算上限）。
2. 設置場所・ネットワーク（固定 IP / VPN / 外部公開の要否。NFC 受付はローカル完結でも Discord/X 連携・途中報告 LT は外向き通信が必要）。
3. 会員 DB・Auth の正体（既存会員管理の実体、NFC カードの発行主体・カード ID 体系・会員 DB スキーマ）。
4. NFC リーダー機種・規格（FeliCa / MIFARE）。
5. 混雑状況センシング方式（カメラ人数カウント等）とプライバシー配慮方針。
6. 体制最終確定（FE4/BE6/IoT2 で確定か）。
7. 有償／お手伝いの線引き（どのトラックのリードを業務扱いにするか）。
8. FE スタック方向性（Next.js 継続を初期前提にするか、最初から軽量スタック移行を要件化するか）。

## References

- 計画原案: [`docs/plans/phase2-virtual-navigator-recruitment-2026.md`](../plans/phase2-virtual-navigator-recruitment-2026.md)
- [ADR-021 Frontend/backend separation before React/Vite](./021-frontend-backend-separation-before-react-vite.md)
- [ADR-024 Memory & Reception modernization](./024-memory-and-reception-modernization.md)
- [ADR-025 Frontend proxy deletion → Vite migration](./025-frontend-proxy-deletion-and-vite-migration.md)
- [ADR-028 OSS-portable observability & infrastructure](./028-oss-portable-observability-and-infrastructure.md)
- [ADR-029 Phase 2 LangGraph 1.0+ best practices](./029-phase2-langgraph-1.0-best-practices.md)（命名衝突: 別物）
- [ADR-030 Kiosk device trigger & cooldown contract](./030-kiosk-device-trigger-and-cooldown-contract.md)
- 関連 Issue: #899（別「Phase 2」）, #489, #611, #114, #113, #774, #540, #515
