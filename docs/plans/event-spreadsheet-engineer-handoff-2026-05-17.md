# 📋 Engineer Cafe Event Spreadsheet — Engineer / Staff Handoff (2026-05-17)

> **対象**: スプレッドシート管理者 (terisuke) + Backend 実装担当エンジニア + Cafe スタッフ (運用)
> **作成**: 2026-05-17, Claude Code session (terisuke 指示)
> **位置付け**: FU-07 (#851) の **実装ハンドオフ**。設計 doc (`docs/plans/event-source-spreadsheet-integration-2026-05-17.md`) と Wave 2 Theme C (#858) の合流点。
> **背景**: terisuke が `alert_discord` シートの管理権限を取得。これを Backend EventAgent の **第 3 ソース (最優先)** として正式統合する。
> **前提**: FU-02 (#844, Cloud Scheduler `event-kb-sync-daily`) は ✅ 完了 (deployed 2026-05-17)

---

## 0. Executive Summary

terisuke の管理権限取得を機に、`alert_discord` シートを **Cafe 公式イベントの source of truth** として確立する。本ハンドオフは以下を定義する:

1. **新スプレッドシート構造 (events シート)** — 既存 `alert_discord` (A=name, B=date) を拡張
2. **Backend が読み取るカラム仕様** — Sheets API + Service Account 経由
3. **Cafe スタッフが書き込む運用フロー** — staff 向け簡易マニュアル
4. **共有 / 権限フロー** — Service Account viewer 共有 + 編集権限管理
5. **マイグレーション手順** — 既存 `alert_discord` データの保存 + 新シートへの移行

| 担当 | 主担当ロール |
|------|------------|
| **terisuke** | スプレッドシート権限管理 / SA 共有 / Apps Script 設定 |
| **Backend engineer** (Wave 2 Theme C) | `SheetsEventSource` 実装 / `sync_event_kb.py` 拡張 |
| **Cafe staff** | events シートへの記入運用 |

---

## 1. スプレッドシート全体構造

### 1.1 シート一覧

| シート名 | 用途 | 編集者 | Backend 参照 |
|---------|------|-------|------------|
| `events` (**新規**) | Cafe 公式イベント一覧 (SoT) | Cafe staff | ✅ 読込 |
| `alert_discord` (既存) | 旧 Discord 通知用 | (凍結) | ❌ 参照停止予定 |
| `config` (新規, optional) | timezone / default venue 等 | terisuke | ✅ 読込 (optional) |
| `_archive` (新規, optional) | 過去イベント (完了/キャンセル) | auto | ❌ |

**重要**: 既存 `alert_discord` は破壊せず **凍結保存** (rename `alert_discord_legacy` 推奨)。新 `events` シートが SoT となる。

### 1.2 ID と URL

スプレッドシート ID (terisuke が下記を取得し Secret Manager に登録):
```
URL 例: https://docs.google.com/spreadsheets/d/<SPREADSHEET_ID>/edit
        ↑                                       ↑
        固定                                    44 文字程度の英数字
```

登録手順 (terisuke):
```bash
# Secret Manager に保存 (URL 全体ではなく ID のみ)
SHEET_ID="<spreadsheet_id_from_url>"
echo -n "$SHEET_ID" | gcloud secrets create ENGINEER_CAFE_EVENT_SHEET_ID \
  --data-file=- --project=aipartner-426616

# Cloud Run service に bind
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="ENGINEER_CAFE_EVENT_SHEET_ID=ENGINEER_CAFE_EVENT_SHEET_ID:latest"
```

---

## 2. `events` シートのカラム仕様

### 2.1 スキーマ定義 (推奨: 14 列)

> **設計方針**:
> - **Tier 1 (必須 5 列, A〜E)**: MVP として最低限イベント情報が成立する
> - **Tier 2 (推奨 9 列, F〜N)**: 多言語対応 / 詳細情報 / 自動化のため強く推奨
> - すべての列にヘッダー行を必須化 (行 1 = ヘッダー、行 2 以降 = データ)

| Col | Header (1行目) | 型 | 必須 | 例 | 説明 / Backend 利用 |
|----|---------------|----|------|-----|---------------------|
| **A** | `status` | enum | ✅ | `scheduled` | `scheduled` / `cancelled` / `completed` / `draft` のいずれか |
| **B** | `title_ja` | string | ✅ | `ゆるもくXR 2026-05` | 日本語タイトル (200 文字以内) |
| **C** | `date_start` | date | ✅ | `2026-05-20` | ISO 8601 形式 (YYYY-MM-DD)、JST 基準 |
| **D** | `time_start` | time | ✅ | `19:00` | HH:MM (24h, JST) |
| **E** | `time_end` | time | ✅ | `21:00` | HH:MM (24h, JST)。終了時刻不明なら開始 +2h を staff が記入 |
| F | `title_en` | string | 推奨 | `Yurumoku XR May 2026` | 英訳。空欄なら Backend が title_ja をそのまま使用 |
| G | `date_end` | date | optional | `2026-05-20` | 複数日イベント時のみ指定 (defaults to date_start) |
| H | `venue` | string | 推奨 | `Engineer Cafe メイン` | 場所。空欄なら `Engineer Cafe` (default) |
| I | `description_ja` | string | 推奨 | `XR 開発もくもく会...` | 日本語説明 (1000 文字以内) |
| J | `description_en` | string | optional | `XR development meetup...` | 英語説明 |
| K | `capacity` | int | optional | `15` | 定員。空欄/0 なら未定/無制限 |
| L | `registration_url` | string | 推奨 | `https://connpass.com/event/...` | Connpass / Peatix / HP |
| M | `last_updated` | timestamp | auto | `2026-05-17T15:00:00+09:00` | Apps Script で onEdit 時自動更新 (§3.3 参照) |
| N | `event_id` | string | auto | `evt_20260520_yurumoku_xr` | 一意 ID。Apps Script で自動採番 (空なら Backend 側で `sheet:<row>:<title>:<date>` を生成) |

### 2.2 ヘッダー行サンプル (コピペ用)

`events` シートの **1 行目** に下記をそのまま貼り付け:

```
status	title_ja	date_start	time_start	time_end	title_en	date_end	venue	description_ja	description_en	capacity	registration_url	last_updated	event_id
```

(タブ区切り — Google Sheets で「貼り付け」すると 14 列に自動展開される)

### 2.3 データ行サンプル

| status | title_ja | date_start | time_start | time_end | title_en | date_end | venue | description_ja | description_en | capacity | registration_url | last_updated | event_id |
|--------|----------|-----------|-----------|----------|----------|----------|-------|---------------|---------------|----------|------------------|--------------|----------|
| scheduled | ゆるもくXR 2026-05 | 2026-05-20 | 19:00 | 21:00 | Yurumoku XR May 2026 | | Engineer Cafe メイン | XR 開発もくもく会。VR/AR どちらでも OK。 | XR development meetup. VR/AR welcome. | 15 | https://connpass.com/event/123456/ | 2026-05-17T15:00:00+09:00 | evt_20260520_yurumoku_xr |
| scheduled | iPad Swift Playgrounds 体験会 | 2026-05-25 | 14:00 | 16:00 | iPad Swift Playgrounds Workshop | | Engineer Cafe サブ | Swift Playgrounds で初めての iOS アプリ開発。 | First iOS app dev with Swift Playgrounds. | 8 | https://engineercafe.jp/events/swift-pg | 2026-05-17T15:05:00+09:00 | evt_20260525_swift_pg |
| cancelled | 中止: 朝活もくもく 5/18 | 2026-05-18 | 08:00 | 10:00 | (CANCELLED) Morning Meetup 5/18 | | | 主催者都合により中止。 | Cancelled by organizer. | | | 2026-05-17T15:10:00+09:00 | evt_20260518_morning |

### 2.4 バリデーション規約 (staff 向け)

- **status**: 必ず `scheduled` / `cancelled` / `completed` / `draft` のいずれか (小文字)
  - `draft` は Backend が無視 (公開しない)
  - `cancelled` は Backend が「中止イベント」として明示 (FU-19 のキャンセル除外と矛盾しないよう、応答時に「中止」ラベル付与)
- **date_start**: 必ず `YYYY-MM-DD` (例: `2026-05-20`)。`2026/5/20` は不可 (Backend がパース失敗)
- **time_start / time_end**: 必ず `HH:MM` (24h, 例: `19:00`)。`7:00 PM` は不可
- **title_ja**: 200 文字以内、改行不可
- **description_ja / description_en**: 1000 文字以内、改行可 (Sheets セル内改行 `Alt+Enter`)

---

## 3. Apps Script 自動化 (推奨, optional)

### 3.1 目的

スタッフの入力ミスを減らし、`last_updated` と `event_id` を自動化する。

### 3.2 Apps Script 設置場所

`events` シートを開いた状態で:
1. メニュー「拡張機能」→「Apps Script」
2. 既存 `alert_discord` 用 GAS は **無効化** (Discord 通知は停止運用)
3. 下記コードを新規 `Code.gs` に貼り付け

### 3.3 推奨スクリプト

```javascript
/**
 * events シートの onEdit トリガー
 * - last_updated 自動記入
 * - event_id 自動採番 (空欄時のみ)
 * - status / date / time の簡易バリデーション (赤色ハイライト)
 */
function onEditEvents(e) {
  const range = e.range;
  const sheet = range.getSheet();
  if (sheet.getName() !== 'events') return;

  const row = range.getRow();
  if (row < 2) return; // ヘッダー行スキップ

  const lastCol = 14; // N 列まで
  const headerRange = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
  const dataRange = sheet.getRange(row, 1, 1, lastCol);
  const data = dataRange.getValues()[0];

  // last_updated (col M = index 12) を更新
  const lastUpdatedIdx = headerRange.indexOf('last_updated');
  if (lastUpdatedIdx >= 0) {
    const now = Utilities.formatDate(new Date(), 'Asia/Tokyo', "yyyy-MM-dd'T'HH:mm:ssXXX");
    sheet.getRange(row, lastUpdatedIdx + 1).setValue(now);
  }

  // event_id (col N = index 13) 空なら自動採番
  const eventIdIdx = headerRange.indexOf('event_id');
  const titleIdx = headerRange.indexOf('title_ja');
  const dateIdx = headerRange.indexOf('date_start');
  if (eventIdIdx >= 0 && !data[eventIdIdx] && data[titleIdx] && data[dateIdx]) {
    const slug = String(data[titleIdx])
      .toLowerCase()
      .replace(/[^a-z0-9぀-ヿ一-鿿]+/g, '_')
      .replace(/^_|_$/g, '')
      .substring(0, 30);
    const dateStr = String(data[dateIdx]).replace(/-/g, '');
    sheet.getRange(row, eventIdIdx + 1).setValue(`evt_${dateStr}_${slug}`);
  }

  // 簡易バリデーション (status / date format)
  const statusIdx = headerRange.indexOf('status');
  const validStatus = ['scheduled', 'cancelled', 'completed', 'draft'];
  if (statusIdx >= 0 && data[statusIdx] && !validStatus.includes(String(data[statusIdx]).toLowerCase())) {
    sheet.getRange(row, statusIdx + 1).setBackground('#ffcdd2');
  }
  if (dateIdx >= 0 && data[dateIdx] && !/^\d{4}-\d{2}-\d{2}$/.test(String(data[dateIdx]))) {
    sheet.getRange(row, dateIdx + 1).setBackground('#ffcdd2');
  }
}
```

### 3.4 トリガー設定

Apps Script エディタで:
1. 左サイドバー「トリガー」→「+ トリガーを追加」
2. 関数: `onEditEvents`
3. イベントのソース: スプレッドシートから
4. イベントの種類: 編集時
5. 保存

---

## 4. Backend 統合フロー (Wave 2 Theme C で実装)

### 4.1 認証 — Service Account 共有

Cloud Run の active SA を spreadsheet に **閲覧者** として共有:

**SA email** (確認方法):
```bash
gcloud run services describe engineer-cafe-backend \
  --region=asia-northeast1 \
  --format='value(spec.template.spec.serviceAccountName)'
```

現状の確認結果 (2026-05-17 時点 / 未設定なら default Compute SA):
```
639959525777-compute@developer.gserviceaccount.com
```

または明示的に `engineer-cafe-navigator@aipartner-426616.iam.gserviceaccount.com` を Cloud Run service に割り当てる方針なら、そちらを共有する。

**手順** (terisuke):
1. スプレッドシートを開く
2. 右上「共有」をクリック
3. 上記 SA email を入力
4. 権限: **「閲覧者」** (Editor は不要、`readonly` scope で十分)
5. 「通知を送信」**チェックを外す** (SA はメール受信不可)
6. 「共有」をクリック

### 4.2 必要な GCP API

```bash
# Sheets API 有効化 (すでに有効済を確認)
gcloud services list --enabled --project=aipartner-426616 | grep sheets
# expect: sheets.googleapis.com
```

未有効の場合:
```bash
gcloud services enable sheets.googleapis.com --project=aipartner-426616
```

### 4.3 環境変数

| 変数名 | 値 | 設置場所 |
|-------|----|---------|
| `ENGINEER_CAFE_EVENT_SHEET_ID` | スプレッドシート ID (44 文字) | Secret Manager → Cloud Run |
| `ENGINEER_CAFE_EVENT_SHEET_NAME` | `events` (default) | Cloud Run env (optional) |
| `ENGINEER_CAFE_EVENT_SHEET_RANGE` | `events!A2:N` (default) | Cloud Run env (optional) |

### 4.4 Backend 実装スケッチ (Wave 2 Theme C 担当エンジニア向け)

新設: `backend/services/sheets_event_source.py`

```python
"""Engineer Cafe Event Spreadsheet を EventSourceRecord に変換する service."""

import os
import logging
from datetime import datetime, time
from typing import List
from zoneinfo import ZoneInfo

import google.auth
from googleapiclient.discovery import build

from backend.services.event_kb_sync import EventSourceRecord, EVENT_KB_SOURCE_PREFIX
from backend.utils.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

SPREADSHEET_ID_ENV = "ENGINEER_CAFE_EVENT_SHEET_ID"
SHEET_RANGE = os.getenv("ENGINEER_CAFE_EVENT_SHEET_RANGE", "events!A2:N")
EVENT_SOURCE_NAME = "spreadsheet"
JST = ZoneInfo("Asia/Tokyo")

# 列インデックス (0-indexed, ヘッダー行のカラム順序に対応)
COL = {
    "status": 0, "title_ja": 1, "date_start": 2, "time_start": 3, "time_end": 4,
    "title_en": 5, "date_end": 6, "venue": 7, "description_ja": 8,
    "description_en": 9, "capacity": 10, "registration_url": 11,
    "last_updated": 12, "event_id": 13,
}
VALID_STATUS = {"scheduled", "completed"}  # cancelled / draft は除外

_SOURCE_LABEL = f"{EVENT_KB_SOURCE_PREFIX}:{EVENT_SOURCE_NAME}"


class SheetsEventSource:
    def __init__(self) -> None:
        self.spreadsheet_id = os.getenv(SPREADSHEET_ID_ENV, "").strip()
        if not self.spreadsheet_id:
            logger.warning("%s not set; SheetsEventSource disabled", SPREADSHEET_ID_ENV)

    def _client(self):
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    def fetch_events(self) -> List[EventSourceRecord]:
        if not self.spreadsheet_id:
            return []

        try:
            result = (
                self._client().spreadsheets().values()
                .get(spreadsheetId=self.spreadsheet_id, range=SHEET_RANGE)
                .execute()
            )
            rows = result.get("values", [])
        except Exception as exc:
            logger.warning("Spreadsheet fetch failed: %s", exc)
            return []

        records: List[EventSourceRecord] = []
        for idx, row in enumerate(rows, start=2):  # row 2 = data start
            rec = self._row_to_record(row, idx)
            if rec:
                records.append(rec)
        logger.info("SheetsEventSource fetched %d events", len(records))
        return records

    def _row_to_record(self, row, row_num) -> EventSourceRecord | None:
        # 必須列が欠けていたら skip
        if len(row) < 5:
            return None
        status = str(row[COL["status"]]).strip().lower()
        if status not in VALID_STATUS:
            return None  # cancelled / draft は KB に入れない

        title_ja = sanitize_input(str(row[COL["title_ja"]]).strip(), 200)
        if not title_ja:
            return None

        try:
            start_dt = self._parse_datetime(
                row[COL["date_start"]], row[COL["time_start"]]
            )
            end_dt = self._parse_datetime(
                row[COL["date_end"]] if len(row) > COL["date_end"] and row[COL["date_end"]] else row[COL["date_start"]],
                row[COL["time_end"]] if len(row) > COL["time_end"] else row[COL["time_start"]],
            )
        except ValueError as exc:
            logger.debug("Skipping row %d (date/time parse): %s", row_num, exc)
            return None

        title_en = sanitize_input(str(row[COL["title_en"]]).strip(), 200) if len(row) > COL["title_en"] else ""
        venue = sanitize_input(str(row[COL["venue"]]).strip(), 100) if len(row) > COL["venue"] else "Engineer Cafe"
        desc_ja = sanitize_input(str(row[COL["description_ja"]]).strip(), 1000) if len(row) > COL["description_ja"] else ""
        url = str(row[COL["registration_url"]]).strip() if len(row) > COL["registration_url"] else ""
        event_id = str(row[COL["event_id"]]).strip() if len(row) > COL["event_id"] and row[COL["event_id"]] else f"sheet:{row_num}:{title_ja}"

        return EventSourceRecord(
            external_id=event_id,
            title=f"{title_ja}" + (f" / {title_en}" if title_en else ""),
            start=start_dt.isoformat(),
            end=end_dt.isoformat(),
            description=desc_ja,
            location=venue or "Engineer Cafe",
            url=url,
            source=EVENT_SOURCE_NAME,
        )

    @staticmethod
    def _parse_datetime(date_str, time_str) -> datetime:
        s_date = str(date_str).strip()
        s_time = str(time_str).strip()
        d = None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                d = datetime.strptime(s_date, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            raise ValueError(f"date parse failed: {date_str}")

        t = None
        for fmt in ("%H:%M", "%H:%M:%S"):
            try:
                t = datetime.strptime(s_time, fmt).time()
                break
            except ValueError:
                continue
        if t is None:
            t = time(0, 0)

        return datetime.combine(d, t, tzinfo=JST)
```

### 4.5 sync_event_kb.py 拡張 (Cloud Scheduler 経由で実行)

既存 `backend/scripts/sync_event_kb.py` に `--include-spreadsheet` flag を追加:

```python
parser.add_argument(
    "--include-spreadsheet",
    action="store_true",
    help="Also fetch from Engineer Cafe events spreadsheet (SoT).",
)

# ...
records = []
if args.ics_url or args.ics_file:
    records.extend(await parse_ics_event_records(...))
if args.include_spreadsheet:
    from backend.services.sheets_event_source import SheetsEventSource
    records.extend(SheetsEventSource().fetch_events())

await sync_event_kb_records(records, ...)
```

Cloud Scheduler ジョブ更新 (既存 `event-kb-sync-daily` の body に flag 追加):
```bash
gcloud scheduler jobs update http event-kb-sync-daily \
  --location=asia-northeast1 \
  --project=aipartner-426616 \
  --message-body='{"args": ["--ics-url", "<url>", "--include-spreadsheet"]}'
```

### 4.6 EventAgent merge 優先順位

`_merge_events` (`backend/agents/event_agent.py:575`) の優先順位:

```
1. spreadsheet (source="spreadsheet")  ← SoT、最優先
2. connpass    (source="connpass")     ← 外部告知
3. calendar    (source="google_calendar") ← 補助
```

同 title + 同 date の重複は spreadsheet 側が勝つ。spreadsheet に **ない** イベントは connpass / calendar からそのまま採用 (Cafe 主催以外の外部イベント補完用)。

---

## 5. Cafe Staff 向け運用マニュアル (簡易版)

### 5.1 新規イベント追加手順

1. スプレッドシート (`events` シート) を開く
2. データ行末尾の **次の空行** に下記を入力:
   - **A 列 `status`**: `scheduled` (確定) or `draft` (まだ表示しない)
   - **B 列 `title_ja`**: 日本語タイトル
   - **C 列 `date_start`**: `YYYY-MM-DD` 形式 (例: `2026-05-20`)
   - **D 列 `time_start`**: `HH:MM` 形式 (例: `19:00`)
   - **E 列 `time_end`**: `HH:MM` 形式 (例: `21:00`、不明なら開始 +2h)
3. (推奨) F 列以降の `title_en` / `venue` / `description_ja` を埋める
4. **M 列 `last_updated` と N 列 `event_id` は Apps Script が自動入力** — staff は触らない
5. **保存は不要** (Google Sheets は自動保存)
6. 翌日 09:00 JST の Cloud Scheduler 実行で Backend に反映 (Knowledge Base 更新)

### 5.2 イベント中止 / 取り消し

- **キャンセル**: A 列 `status` を `scheduled` → `cancelled` に変更
  - Backend は 「中止」イベントとして除外 (応答に出ない)
- **誤入力削除**: 行全体を削除 (Sheets の右クリック「行を削除」)

### 5.3 過去イベント整理 (月次)

- 月末に `date_start < 今日` のイベントを `_archive` シートに切り出す (optional)
- Backend は `date_start >= 今日` のみ参照するので、放置でも害はない (容量増加のみ)

### 5.4 よくあるミス

| ミス | 症状 | 対処 |
|-----|------|------|
| `2026/5/20` と入力 | Backend がパース失敗、応答に出ない | `2026-05-20` (ハイフン + 0埋め) |
| `7:00 PM` と入力 | 同上 | `19:00` (24h 表記) |
| `status` 空欄 | 同上 | 必ず `scheduled` 等を入力 |
| title_ja に改行 | 表示崩れ | 改行禁止 (descriptionに記載) |

---

## 6. マイグレーション手順 (terisuke)

### 6.1 既存 `alert_discord` シート保全

```
1. シートタブを右クリック →「コピーを作成」→「alert_discord_legacy」にリネーム
2. (オプション) 別ファイルとしてダウンロード保存 (`.xlsx` / `.csv`)
```

### 6.2 新 `events` シート作成

```
1. シート下部の「+」ボタンで新規シート追加 → 名前を「events」に変更
2. §2.2 のヘッダー行をコピペ
3. §2.3 のサンプルデータを参考に、現存予定のイベントを移行入力
4. (推奨) §3.3 の Apps Script を設置 + onEdit トリガー設定
```

### 6.3 SA 共有 (§4.1)

```
1. 右上「共有」
2. SA email を「閲覧者」追加
3. 通知を送信のチェック外し → 共有
```

### 6.4 Secret Manager 登録 (§1.2)

```
gcloud secrets create ENGINEER_CAFE_EVENT_SHEET_ID --data-file=- <<< "<id>"
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="ENGINEER_CAFE_EVENT_SHEET_ID=ENGINEER_CAFE_EVENT_SHEET_ID:latest"
```

### 6.5 動作確認 (Backend エンジニアと連携)

```bash
# Cloud Run rev デプロイ後、手動で Cloud Scheduler ジョブ実行
gcloud scheduler jobs run event-kb-sync-daily \
  --location=asia-northeast1 --project=aipartner-426616

# Supabase で確認
psql ... -c "SELECT title, source, created_at FROM knowledge_base WHERE category='events' ORDER BY created_at DESC LIMIT 10;"
# expect: source='event_bridge:spreadsheet' の record が複数件
```

---

## 7. 役割と完了条件

### 7.1 役割分担

| 担当 | タスク | 完了条件 |
|------|-------|---------|
| **terisuke** | スプレッドシート構造再設計 + SA 共有 + Secret 登録 + Apps Script 設置 + 既存予定移行 | §2 〜 §6 全項目 done |
| **Cafe staff** | 新規イベント記入運用 | 5/24 以降の新規イベントは `events` シートに記入 |
| **Backend engineer (Theme C)** | `SheetsEventSource` 実装 + `sync_event_kb.py` 拡張 + EventAgent merge 更新 + Cloud Scheduler ジョブ body 更新 | FU-07 Issue #851 / PR #852 close |

### 7.2 Wave 2 Theme C 完了条件 (再掲)

- [ ] `curl /api/chat "今日のイベントは?"` → spreadsheet 由来のイベントが上位に出る
- [ ] 「今週のイベント」→ spreadsheet に基づき過去日含まず正確
- [ ] キャンセル (`status=cancelled`) は応答に出ない
- [ ] `cancelled` を Backend が「中止」ラベルとして処理 (FU-19 と整合)
- [ ] RAGAS event ground truth 更新 + ja >= 0.85

---

## 8. Open Questions / Risks

| # | Question / Risk | Owner | 期限 |
|---|----------------|-------|------|
| Q1 | `events` シート 1 ファイルに何件まで現実的か? (現状年 ~60 件想定なら問題なし) | terisuke | 検討 |
| Q2 | 既存 `alert_discord` の現存予定 (もしあれば) を `events` に移行する優先度は? | terisuke | Day 1 |
| Q3 | 多言語タイトル: `title_en` が空の場合、Backend が DeepL/OpenRouter で翻訳するか? | Backend engineer | Day 2 |
| Q4 | Cloud Scheduler 頻度: 現状 daily 09:00 JST。staff 入力反映の遅延が問題なら 1h ごとに変更? | terisuke | 運用開始後 |
| R1 | SA 共有外しミス → Backend が空応答 | terisuke | 定期 audit (月次) |
| R2 | スプレッドシート ID 変更 / 削除 → Backend 致命的 | terisuke | Secret Manager rotation 手順を runbook 化 |
| R3 | Apps Script onEdit がパースエラーで停止 → `last_updated` 未更新 | terisuke | Apps Script の実行ログ監視 |
| R4 | staff がフォーマット違反入力 → Backend skip しても気付けない | Backend engineer | sync_event_kb.py で skip 件数を log + Datadog/Sentry alert |

---

## 9. Reference

- 設計 doc (FU-07): `docs/plans/event-source-spreadsheet-integration-2026-05-17.md`
- Wave 2 handoff: `docs/plans/wave2-date-audio-calendar-handoff-2026-05-17.md` §4
- FU-02 (Cloud Scheduler ✅ done): Issue #844 closed
- FU-07 (Spreadsheet 実装): Issue #851 / PR #852
- Wave 2 Theme C (Calendar): Issue #858
- Sheets API doc: https://developers.google.com/sheets/api/guides/values
- Existing Apps Script (legacy, 停止): `script.google.com/home/projects/1nh9-irHMyCQ8RvcASOD98CJDd5r_cttfdo-hJL_aWj8a26k5cLjnkjUN/edit`
