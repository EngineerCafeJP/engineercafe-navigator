# 📊 Event Source Spreadsheet 統合提案

> **対象**: 現在実装を担当しているエンジニア + terisuke
> **作成**: 2026-05-17, Claude Code session (terisuke 指示)
> **位置付け**: Phase 2 readiness handoff (#842) の追加候補 **FU-07** として位置付け。Event KB cron (FU-02) と密接に関連
> **背景**: Engineer Cafe スタッフが手動でメンテしている Discord 通知用スプレッドシートを EventAgent の第 3 のイベントソースとして取り込む提案

---

## 0. Executive Summary

### 何を解決するか

[FU-02 Event KB Cron Sync](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/844) で計画している ICS 同期は、ICS の構造的問題 (Busy だらけ、Cafe 主催イベント少) を解決できない。一方、Cafe スタッフは**別途スプレッドシート + Apps Script で Discord 通知**の運用を持っており、ここに **Cafe 主催の真のイベント一覧**が手動で整備されている。

このスプレッドシートを backend に統合することで:

| 現状 | After |
|---|---|
| ICS = 343 events 中 282 future (うち実イベント < 30 件、残りは Busy/個人予定) | Spreadsheet = Cafe 主催イベントのみ手動キュレーション |
| Connpass = 外部 API、Cafe 主催以外も混在 | Spreadsheet = Cafe 公式イベント定義の source of truth |
| EventAgent sources = `['google_calendar', 'connpass']` | EventAgent sources = `['spreadsheet', 'google_calendar', 'connpass']` (優先順) |
| Issue #517 Event KB cron deploy で同期するのは ICS のみ | spreadsheet も同期、KB に Cafe 公式の真のイベントが入る |

### 提案スコープ

| ID | タイトル | 工数 |
|---|---|---|
| **FU-07** | Engineer Cafe Event Spreadsheet を EventAgent の第 3 ソースに統合 | 2〜3日 |

---

## 1. Background — Apps Script 解析

terisuke 提供の Apps Script ([URL](https://script.google.com/home/projects/1nh9-irHMyCQ8RvcASOD98CJDd5r_cttfdo-hJL_aWj8a26k5cLjnkjUN/edit), 現在は未使用) から判明する仕様:

### スプレッドシート構造
- **シート名**: `alert_discord`
- **データ範囲**: `A3:B` (3 行目から最終行まで)
- **列構成**:
  - **A 列**: イベント名 (文字列)
  - **B 列**: イベント日付 (Date オブジェクトとして parse 可能)
- **ヘッダー**: A1〜A2 はヘッダー or 空 (data は A3 から)
- **無効値**: `#N/A` / 空セル は skip

### 運用フロー (Apps Script から推測)
1. Cafe スタッフが新規イベントを `alert_discord` シートに追加
2. `onEdit` トリガー → 5 分後にバッチ通知
3. Discord webhook で通知 (`@707897904446308404` メンション)
4. 通知内容: "新しいイベント告知情報が更新されました…HP, FB, Discord へのイベント作成をお願いします"
5. **重要**: Discord 通知 = "該当イベントのカレンダー情報をデフォルトから一般公開に切り替えてください" の運用を含む

→ **このスプレッドシートが Cafe イベントの実質的な source of truth**

### 現在は未使用 (Apps Script は停止)
terisuke コメント: "ここのスクリプトははつかってないよ"
→ Apps Script の Discord 通知自動化は廃止されているが、スプレッドシート自体は手動メンテ継続中の可能性大 (要確認)

---

## 2. 現状分析 — なぜ別の event source が必要か

### 既存 2 ソースの限界 (PR #841 / 本日 audit pass 4 で確認済)

#### Google Calendar ICS
- URL: `https://calendar.google.com/calendar/ical/c_78afu1co85di40hko55f0h9tdc@group.calendar.google.com/public/basic.ics`
- **15 日間で 82 fetch 成功** (HTTP 200 OK)
- **343 VEVENT 中 noise filter で 62 件除外** (Busy / Tentative / Free 等)
- 残った events も「お昼だよ」「キャンセル XRMTG」など個人予定 / 古いキャンセル予定が混入
- **Cafe 主催の純粋イベントは恐らく月 5-10 件程度** (5/13 ゆるもくXR / iPad Swift Playgrounds 等)

#### Connpass
- API v2 (`https://connpass.com/api/v2/events/`)
- prefecture=fukuoka でフィルタ
- **CONNPASS_API_KEY は PR #841 で配備済** (rev 00209 以降 not configured warning なし)
- 外部 API のため Cafe 主催以外の福岡県イベントも混在
- 5/17 today の応答: "3D プリンター講習" + "AkarengaLT vol.45" の 2 件取得 (正確)

### 3 ソース体制で得られるもの

```
EventAgent (新設計):
  ├── Spreadsheet (新規, 最優先)  — Cafe 公式・staff キュレーション、source of truth
  ├── Google Calendar ICS         — 内部スケジュール (補助、Busy filter 後)
  └── Connpass                    — 外部告知 (補助、Fukuoka prefecture filter)

Merge ルール (新提案):
  1. spreadsheet event は最優先 (verified=true として KB に格納)
  2. 同 title + date が calendar / connpass にあれば spreadsheet 側で上書き
  3. spreadsheet にない calendar / connpass event は priority=low で参考表示
```

---

## 3. 統合方式の比較

| 方式 | 認証 | 実装難度 | 運用負荷 | リアルタイム性 | 推奨度 |
|---|---|---|---|---|---|
| A. Sheets API + SA 認証 (private sheet) | Cloud Run SA に spreadsheet share | 中 | 低 | pull 5分 | ⭐⭐⭐ |
| B. Sheets API + API key (public sheet) | spreadsheet 全体公開 | 低 | 低 | pull 5分 | ⭐⭐ (公開リスク) |
| C. Apps Script Web App → backend push | onEdit で backend `/api/webhook/events` 叩く | 中 | 中 | 即時 | ⭐⭐ |
| D. Apps Script で Publish CSV → backend fetch | 公開 CSV URL | 最低 | 最低 | pull 5分 | ⭐ (URL 漏洩リスク) |
| **E. Cloud Scheduler + Sheets API + SA** | SA + Scheduler (FU-02 と同梱) | 高 | 低 | cron (5-15min) | ⭐⭐⭐⭐ |

**推奨**: **方式 E (Cloud Scheduler + Sheets API + SA)**

理由:
- **FU-02 (Issue #517 Event KB cron deploy) と同じ Cloud Scheduler 基盤を共有**できる
- spreadsheet 自体は社内公開 (リンク知ってる人だけ閲覧) のままで OK、SA だけに viewer 共有
- 既存 `event_kb_sync.py` の `EventSourceRecord` を spreadsheet record 用に extend するだけ
- ICS / Connpass / Spreadsheet の 3 系統が同じ Cron Sync で統合され、Knowledge Base への流入が一本化される

---

## 4. 提案実装設計 (FU-07)

### 4.1 Cloud Run SA 権限追加

現在の Cloud Run active SA: `639959525777-compute@developer.gserviceaccount.com` (default Compute Engine SA)

```bash
# Sheets API は既に有効化済 (確認済)
# gcloud services list --enabled | grep sheets → sheets.googleapis.com  ✅

# SA に必要な role 追加 (一度きり)
gcloud projects add-iam-policy-binding aipartner-426616 \
  --member="serviceAccount:639959525777-compute@developer.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# spreadsheet の共有設定 (terisuke が手動で実行)
# - スプレッドシートを開き「共有」
# - 上記 SA email を「閲覧者」として追加
```

### 4.2 backend 依存追加 (`backend/pyproject.toml`)

```toml
google-api-python-client = "^2.140.0"     # Sheets API v4
google-auth-httplib2 = "^0.2.0"
# google-auth は既存
```

### 4.3 SheetsEventSource service 新設

新設ファイル: `backend/services/sheets_event_source.py`

```python
"""
Spreadsheet を EventSource として読み取る service.

Cafe スタッフが手動メンテしている alert_discord シートを
EventSourceRecord 形式に変換して event_kb_sync に渡す。
"""

import os
import logging
from datetime import datetime
from typing import List

from google.oauth2 import service_account
from googleapiclient.discovery import build

from backend.services.event_kb_sync import EventSourceRecord

logger = logging.getLogger(__name__)

SPREADSHEET_ID_ENV = "ENGINEER_CAFE_EVENT_SHEET_ID"
SHEET_RANGE = "alert_discord!A3:B"  # A=title, B=date
EVENT_SOURCE_NAME = "spreadsheet"


class SheetsEventSource:
    """Engineer Cafe Event spreadsheet reader."""

    def __init__(self) -> None:
        self.spreadsheet_id = os.getenv(SPREADSHEET_ID_ENV, "").strip()
        if not self.spreadsheet_id:
            logger.warning(
                "%s not configured; SheetsEventSource will return empty",
                SPREADSHEET_ID_ENV,
            )

    def _client(self):
        # Cloud Run の default SA を使う (Application Default Credentials)
        credentials, _ = service_account.default(
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)

    def fetch_events(self) -> List[EventSourceRecord]:
        if not self.spreadsheet_id:
            return []

        try:
            client = self._client()
            result = (
                client.spreadsheets()
                .values()
                .get(spreadsheetId=self.spreadsheet_id, range=SHEET_RANGE)
                .execute()
            )
            rows = result.get("values", [])
        except Exception as exc:
            logger.warning("Spreadsheet fetch failed: %s", exc)
            return []

        records: List[EventSourceRecord] = []
        for row in rows:
            if len(row) < 2:
                continue
            title, date_str = row[0], row[1]
            if not title or not date_str or title == "#N/A" or date_str == "#N/A":
                continue
            try:
                start = self._parse_date(date_str)
            except ValueError as exc:
                logger.debug("Skipping invalid date row %s: %s", row, exc)
                continue
            records.append(
                EventSourceRecord(
                    external_id=f"sheet:{title}:{start}",
                    title=str(title).strip(),
                    start=start,
                    end="",
                    description="",
                    location="Engineer Cafe (default)",
                    url="",
                    source=EVENT_SOURCE_NAME,
                )
            )
        logger.info("SheetsEventSource fetched %d events", len(records))
        return records

    @staticmethod
    def _parse_date(value: str) -> str:
        """Convert spreadsheet date (e.g. '2026/05/20' or '2026-05-20') to ISO."""
        s = str(value).strip()
        for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        raise ValueError(f"Unrecognized date format: {value}")
```

### 4.4 Cloud Scheduler ジョブ拡張 (FU-02 と同梱)

[FU-02 の `sync_event_kb.py`](https://github.com/EngineerCafeJP/engineercafe-navigator/blob/develop/backend/scripts/sync_event_kb.py) を以下のように拡張:

```python
# CLI に --spreadsheet flag 追加
parser.add_argument(
    "--include-spreadsheet",
    action="store_true",
    help="Also fetch from Engineer Cafe alert_discord spreadsheet.",
)

# 実行 body
records = []
if args.ics_url or args.ics_file:
    records.extend(await parse_ics_event_records(...))
if args.include_spreadsheet:
    sheets = SheetsEventSource()
    records.extend(sheets.fetch_events())

await sync_event_kb_records(records, ...)
```

Cloud Scheduler ジョブ (FU-02 と同じ):
```bash
gcloud scheduler jobs create http event-kb-sync-daily \
  --location=asia-northeast1 \
  --schedule="0 0 * * *" \
  --uri="https://...event-kb-sync:run" \
  --http-method=POST \
  --message-body='{"args": ["--ics-url", "...", "--include-spreadsheet"]}'
```

### 4.5 EventAgent merge ロジック更新

[`backend/agents/event_agent.py:167`](backend/agents/event_agent.py:167) `_merge_events` の拡張:

```python
def _merge_events(
    self,
    calendar_result: Dict,
    connpass_result: Dict,
    spreadsheet_result: Dict | None = None,   # NEW
) -> List[Dict]:
    # 1. spreadsheet を最優先で投入 (verified=True)
    # 2. calendar / connpass で同 title + date を見つけたら spreadsheet 側を採用
    # 3. spreadsheet にない event は補助情報として priority=low
    ...
```

### 4.6 環境変数 / Secret Manager

```bash
# spreadsheet ID を Secret Manager に保存 (URL 含むため secret 推奨)
echo -n "<spreadsheet_id>" | \
  gcloud secrets create ENGINEER_CAFE_EVENT_SHEET_ID --data-file=- --project=aipartner-426616

# Cloud Run env に bind
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="ENGINEER_CAFE_EVENT_SHEET_ID=ENGINEER_CAFE_EVENT_SHEET_ID:latest"
```

---

## 5. 着手前の確認事項 (terisuke 案件)

- [ ] **スプレッドシート ID 提供** — Apps Script URL ではなく実 Spreadsheet の share URL or ID
- [ ] **スプレッドシートが現在も手動メンテされているか確認**
- [ ] **B 列の日付フォーマット確認** (`2026/05/20` か `2026-05-20` か Excel シリアル値か)
- [ ] **C 列以降の追加情報あるか** (場所、URL、説明文等あれば取り込み拡張)
- [ ] **SA email `639959525777-compute@developer.gserviceaccount.com` に spreadsheet 共有設定**
- [ ] **Cafe 側運用 SOP との整合** — Apps Script 廃止後の Discord 通知をどうするか (backend で代替するか、別の運用に切替済か)

---

## 6. Verification (FU-07 完了条件)

```bash
# 1. SheetsEventSource unit test
cd backend && pytest tests/services/test_sheets_event_source.py -v

# 2. Cron 経由で knowledge_base に spreadsheet 由来 record が入る確認
gcloud scheduler jobs run event-kb-sync-daily --location=asia-northeast1 --project=aipartner-426616

# Supabase で確認:
# SELECT count(*) FROM knowledge_base WHERE category='event' AND source LIKE 'event_bridge:spreadsheet%';
# → > 0 が PASS

# 3. EventAgent 経由でスプレッドシート由来 event が返るか
curl -X POST .../api/chat -H "X-API-Key: $KEY" \
  -d '{"query": "今週のイベント", "session_id": "verify-fu07", "language": "ja"}'

# response.metadata.sources に "spreadsheet" が含まれれば PASS
# Cafe 公式イベント (例: 5/20 のゆるもくXR) が回答に含まれれば PASS
```

---

## 7. Phase 2 readiness との位置付け

### 既存 FU との関係

| FU | 説明 | FU-07 との関係 |
|---|---|---|
| FU-02 (#844) Event KB Cron Sync deploy | Cloud Scheduler + sync_event_kb.py | **同 PR で同梱推奨** (`--include-spreadsheet` flag 追加だけ) |
| FU-04 (#846) memory_* / reception_* events 追加 | observability | event_kb_sync 経由で `event_kb_sync_run` event family も追加候補 |

### Phase 2 開始前に潰すべきか

**推奨判断**: **FU-02 と同梱**で半日〜1日の追加工数で実装可能。

理由:
- Phase 2 で Semantic Router 三段カスケード + critic_node を導入する際、EventAgent の応答精度が信頼できる前提となる
- ICS / Connpass だけだと「Cafe 主催イベント不明瞭」「Busy ノイズ」「過去イベント混入」の問題が常に背景に
- Spreadsheet 統合で「真のイベント = spreadsheet」と grounding できれば、critic_node の hallucination 判定も精度向上

---

## 8. Risk / 課題

| Risk | Mitigation |
|---|---|
| Spreadsheet が最新化されていない | terisuke / Cafe スタッフに「手動メンテ継続するか」を事前確認。継続なら採用、放置なら別案 (Apps Script Discord 自動化を backend で再現) |
| SA に閲覧権限を付与する手間 | spreadsheet 1 ファイルだけ「閲覧者」追加で OK (5 分作業) |
| 列構成が変更されたら parse 失敗 | A 列 / B 列固定の前提でテスト追加、ChangeLog 監視 (header row が変わったら structured_logger に WARN emit) |
| 過去イベントが累積して計算量が増える | sync_event_kb 側で 30 日より古い event は priority=low / 90 日より古いものは archive |
| spreadsheet が漏洩 | private のまま SA 認証経由なら問題なし。方式 D (CSV publish) を採用しないこと |

---

## 9. 関連ドキュメント

- [PR #849 Phase 2 readiness handoff](https://github.com/EngineerCafeJP/engineercafe-navigator/pull/849)
- [Issue #842 Epic](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/842) — FU-07 を sub-issue として追加候補
- [Issue #844 (FU-02)](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/844) — Event KB Cron Sync, FU-07 と同 PR 推奨
- [Issue #517](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/517) — Event KB live bridge (FU-02 で解消)
- `backend/services/event_kb_sync.py` — 既存の EventSourceRecord / sync_event_kb_records パターン
- `backend/tools/calendar_service.py` — ICS fetch + noise filter
- `backend/tools/connpass_service.py` — Connpass API v2 client
- `backend/agents/event_agent.py` — 3 ソース merge 対象 (`_merge_events`)

---

## 10. 推奨次アクション

1. **terisuke**: spreadsheet ID 共有 + Cloud Run SA に「閲覧者」権限付与 (5-10 分)
2. **エンジニア**: FU-07 sub-issue 起票 (本 doc を根拠として) → FU-02 PR にスコープ追加 or 別 PR
3. **本 doc を develop に commit**: 別 PR (`docs/plans/event-source-spreadsheet-integration-2026-05-17.md`) として PR #849 に追加 or 別 PR

---

**End of proposal.** FU-02 と統合実装すれば、Engineer Cafe イベント案内が「Cafe 公式 + ICS 補助 + Connpass 補助」の 3 段冗長化され、EventAgent の応答精度・信頼性ともに大幅改善が期待できます。
