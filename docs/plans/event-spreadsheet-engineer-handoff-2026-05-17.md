# 📋 Engineer Cafe Event Spreadsheet — Engineer Handoff (2026-05-17, rev 2)

> **対象**: Backend 実装担当エンジニア (Wave 2 Theme C)、terisuke (権限管理)
> **作成**: 2026-05-17, Claude Code session
> **位置付け**: FU-07 (#851) の **実装ハンドオフ**。Wave 2 Theme C (#858) の base layer。
> **前提**:
> - terisuke が **既存の `alert_discord` スプレッドシート** の管理権限を取得済
> - シート構造・staff の運用フロー・既存データは **一切変更しない**
> - FU-02 (#844, Cloud Scheduler `event-kb-sync-daily`) は ✅ 完了
>
> **設計方針**:
> - 既存スプレッドシート (`alert_discord` シート, range `A3:B`, A=イベント名, B=日付) を **そのまま読み取る**
> - terisuke が GAS Web App をデプロイ → Backend は **URL を fetch するだけ** で取得
> - シートに新しい列を追加するなどの schema 変更は要求しない (将来拡張は §7 参照)

---

## 0. Executive Summary

terisuke 指摘:
> 既に既存のスプレッドシートがあるという認識で進めてください。新規でスプレッドシートを作るのではなく、まず制限されたアカウントであれば、取得できるURLを許可したユーザーとして入れてもらって、URLを共有してもらって、GAS のようにそれを取得するような仕組みがいいのではないでしょうか。

→ 本 doc は **既存シート + GAS Web App fetch** の最小侵襲アプローチを採用。

### 全体像

```
┌────────────────────────────┐
│ alert_discord (既存シート)  │
│   A3:B 形式               │
│   A = イベント名          │
│   B = 日付                │
│   ↑ Cafe staff が現状通り編集 │
└──────────┬─────────────────┘
           │ 読み取り (Google Workspace 内)
           ▼
┌────────────────────────────┐
│ Apps Script Web App        │
│   doGet(e) で JSON 返却    │
│   ?token=SECRET で認証     │
│   terisuke がデプロイ管理   │
└──────────┬─────────────────┘
           │ HTTPS GET + token
           ▼
┌────────────────────────────┐
│ Backend (Cloud Run)        │
│   sync_event_kb.py         │
│   --include-spreadsheet    │
│   Cloud Scheduler で毎日09:00│
└──────────┬─────────────────┘
           ▼
┌────────────────────────────┐
│ knowledge_base table       │
│   category=events          │
│   source=spreadsheet       │
└────────────────────────────┘
```

---

## 1. 既存スプレッドシートの構造 (変更しない)

### 1.1 シート構造 (既存仕様、Apps Script 解析より)

| 項目 | 値 |
|------|----|
| シート名 | `alert_discord` |
| データ範囲 | `A3:B` (3 行目以降) |
| A 列 | イベント名 (文字列) |
| B 列 | イベント日付 (Date オブジェクトまたは `YYYY/MM/DD` などの文字列) |
| ヘッダー | A1〜A2 はヘッダーまたは空 |
| 無効値 | `#N/A` / 空セルは skip |

**Backend 側の要求**: 上記 2 列を読み取るだけ。**列追加・列順変更は不要**。

### 1.2 既存運用フロー (変更しない)

- Cafe staff が新規イベントを `alert_discord` シートに追加
- (legacy) `onEdit` トリガー → Discord 通知 (現在は停止運用中、シート編集自体は継続)
- Staff の入力習慣・列定義は **そのまま** 維持

### 1.3 Backend が解釈するルール

| 状況 | 動作 |
|------|------|
| A 列 (title) が空 or `#N/A` | skip |
| B 列 (date) が空 or `#N/A` | skip |
| B 列がパース不能 (例: `未定`) | skip + warning log |
| B 列が過去日 | skip (Wave 2 Theme C FU-18 の過去日除外と整合) |
| 同一 (title, date) が複数行 | 最初の 1 件を採用 + duplicate warning log |
| タイトル先頭が `中止` `キャンセル` `[CANCELLED]` | skip (Wave 2 FU-19 整合) |

→ シートに status 列がなくても、**タイトル先頭文字列でキャンセルを判定** することで既存 staff の習慣に合わせる。

---

## 2. 認証方式の選定

### 2.1 比較

| 方式 | 認証 | terisuke 側作業 | Backend 側作業 | 推奨 |
|------|------|---------------|--------------|------|
| **A. GAS Web App + shared token** | Apps Script の `doGet(e)` で `?token=SECRET` 検証 | GAS デプロイ (1 回) + Secret 共有 | 単純 HTTPS GET | ⭐⭐⭐⭐ **推奨** |
| B. Sheets API + SA viewer share | Service Account を viewer に追加 | SA email 共有設定 | ADC + Sheets API client | ⭐⭐⭐ |
| C. Publish-to-web (CSV) | シート全体を公開 (URL 知ってる全員が閲覧) | チェックボックス 1 つ | CSV パース | ⭐ (公開リスク) |

### 2.2 推奨: 方式 A (GAS Web App + shared token)

**理由** (terisuke 指摘に沿った設計):
- 「制限されたアカウントであれば、取得できる URL を許可したユーザーとして入れてもらって」 → terisuke のアカウントで GAS を deploy = terisuke の権限でスプレッドシートを読む
- 「URL を共有してもらって」 → GAS Web App URL を terisuke から Backend に共有
- 「GAS のようにそれを取得する仕組み」 → まさに GAS Web App パターン
- Sheets API + SA 共有よりも **terisuke 側の操作が少ない** (SA email 確認・共有設定・API enable 不要)
- スプレッドシート自体の共有設定を変えない (情報漏洩経路を増やさない)
- 将来 schema 変更 (列追加) があっても、GAS 側で吸収すれば Backend は変更不要

**セキュリティ**:
- `?token=XXX` をクエリパラメータで送る場合、HTTPS で暗号化されるが、GAS 実行ログにクエリが残る点に注意 (Apps Script 実行履歴は terisuke のみ閲覧可)
- token は Secret Manager に保管、Cloud Run env 経由で Backend に渡す
- token rotation は Secret Manager の new version + GAS Script Property 更新で実現

---

## 3. Apps Script Web App (terisuke デプロイ)

### 3.1 設置場所

既存スプレッドシートの **Apps Script エディタ**に新規スクリプトとして追加。
（legacy `alert_discord` の Discord 通知 GAS とは別ファイル推奨、混同防止のため）

1. スプレッドシートを開く
2. メニュー「拡張機能」→「Apps Script」
3. 既存 `Code.gs` は触らず、新しいファイル `EventApi.gs` を追加

### 3.2 推奨スクリプト (`EventApi.gs`)

```javascript
/**
 * Engineer Cafe Event API (GAS Web App)
 *
 * GET https://script.google.com/macros/s/<DEPLOY_ID>/exec?token=<SECRET>
 * → { "events": [{ "title": "...", "date": "YYYY-MM-DD" }, ...] }
 *
 * 認証: Script Properties に SHARED_TOKEN を設定し、クエリ token と一致する場合のみ返却。
 */

const SHEET_NAME = 'alert_discord';
const DATA_RANGE = 'A3:B';

function doGet(e) {
  // 認証
  const expectedToken = PropertiesService.getScriptProperties().getProperty('SHARED_TOKEN');
  if (!expectedToken) {
    return _json({ error: 'server not configured (SHARED_TOKEN missing)' }, 500);
  }
  const providedToken = (e && e.parameter && e.parameter.token) || '';
  if (providedToken !== expectedToken) {
    return _json({ error: 'unauthorized' }, 401);
  }

  // データ取得
  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    return _json({ error: `sheet '${SHEET_NAME}' not found` }, 404);
  }

  const values = sheet.getRange(DATA_RANGE).getValues();
  const events = [];
  for (let i = 0; i < values.length; i++) {
    const [titleRaw, dateRaw] = values[i];
    if (!titleRaw || titleRaw === '#N/A') continue;
    if (!dateRaw || dateRaw === '#N/A') continue;

    const title = String(titleRaw).trim();
    if (!title) continue;

    const date = _toIsoDate(dateRaw);
    if (!date) continue;

    events.push({
      title: title,
      date: date,                    // ISO 8601 YYYY-MM-DD
      row: i + 3,                    // データ範囲が A3 開始なので +3 (デバッグ用)
    });
  }

  return _json({
    events: events,
    sheet: SHEET_NAME,
    fetched_at: new Date().toISOString(),
    count: events.length,
  }, 200);
}

/**
 * Date オブジェクト or 文字列を ISO YYYY-MM-DD に変換。
 * 失敗時 null。
 */
function _toIsoDate(value) {
  if (value instanceof Date) {
    return Utilities.formatDate(value, 'Asia/Tokyo', 'yyyy-MM-dd');
  }
  const s = String(value).trim();
  // YYYY-MM-DD / YYYY/MM/DD / M/D/YYYY などを許容
  const patterns = [
    /^(\d{4})[-\/](\d{1,2})[-\/](\d{1,2})$/,
    /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/,
  ];
  for (const re of patterns) {
    const m = s.match(re);
    if (!m) continue;
    let yyyy, mm, dd;
    if (m[1].length === 4) { [, yyyy, mm, dd] = m; } else { [, mm, dd, yyyy] = m; }
    const d = new Date(Number(yyyy), Number(mm) - 1, Number(dd));
    if (!isNaN(d.getTime())) {
      return Utilities.formatDate(d, 'Asia/Tokyo', 'yyyy-MM-dd');
    }
  }
  return null;
}

function _json(body, status) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
  // 注: GAS Web App は HTTP status code を直接返せないため、
  //     body 内の error field で Backend 側に判定させる。
}
```

### 3.3 Script Properties 設定

GAS エディタ:
1. 左サイドバー「プロジェクトの設定」→「スクリプト プロパティ」
2. 「スクリプト プロパティを追加」
3. プロパティ名: `SHARED_TOKEN`
4. 値: 強いランダム文字列 (例: `openssl rand -hex 32` で生成)
5. 保存

### 3.4 デプロイ手順

1. GAS エディタ右上「デプロイ」→「新しいデプロイ」
2. 「種類の選択」→ 歯車アイコン →「ウェブアプリ」
3. 設定:
   - **説明**: `Engineer Cafe Event API v1`
   - **次のユーザーとして実行**: `自分 (terisuke@...)` ← terisuke の Google アカウントで実行
   - **アクセスできるユーザー**: `全員` ← token で実 auth するので URL を知ってる人だけアクセス可
4. 「デプロイ」をクリック
5. 表示された **Web App URL** をコピー (`https://script.google.com/macros/s/AKfyc.../exec`)

**重要**: 「全員」公開でも token 必須なので実質的に token 保持者のみアクセス可。public discovery されないよう URL は Secret 扱い。

### 3.5 動作確認 (terisuke 手元)

```bash
# 認証なし → 401
curl "https://script.google.com/macros/s/<DEPLOY_ID>/exec"
# → {"error":"unauthorized"}

# 正しい token → events JSON
curl "https://script.google.com/macros/s/<DEPLOY_ID>/exec?token=<SHARED_TOKEN>"
# → {"events":[{"title":"...","date":"2026-05-20","row":3}, ...], "count": N}
```

---

## 4. Backend 統合 (Wave 2 Theme C 担当エンジニア)

### 4.1 環境変数 / Secret Manager

| 変数名 | 値 | 設置場所 |
|-------|----|---------|
| `EVENT_SHEET_GAS_URL` | GAS Web App URL (terisuke から共有) | Secret Manager → Cloud Run |
| `EVENT_SHEET_GAS_TOKEN` | SHARED_TOKEN 同値 | Secret Manager → Cloud Run |

**登録手順** (terisuke + Backend engineer):
```bash
# URL を Secret として登録
echo -n "https://script.google.com/macros/s/<DEPLOY_ID>/exec" | \
  gcloud secrets create EVENT_SHEET_GAS_URL --data-file=- --project=aipartner-426616

# token を Secret として登録
echo -n "<SHARED_TOKEN_VALUE>" | \
  gcloud secrets create EVENT_SHEET_GAS_TOKEN --data-file=- --project=aipartner-426616

# Cloud Run service に bind
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest" \
  --update-secrets="EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest"
```

### 4.2 新設: `backend/services/sheets_event_source.py`

```python
"""
Engineer Cafe Event Spreadsheet を GAS Web App 経由で取得する service.

terisuke がデプロイした Apps Script Web App から JSON で events を取得し、
EventSourceRecord に変換する。Sheets API / Service Account は使わない
(terisuke 指摘: GAS Web App + shared token 方式)。
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo

import httpx

from backend.services.event_kb_sync import EventSourceRecord, EVENT_KB_SOURCE_PREFIX
from backend.utils.input_sanitizer import sanitize_input

logger = logging.getLogger(__name__)

GAS_URL_ENV = "EVENT_SHEET_GAS_URL"
GAS_TOKEN_ENV = "EVENT_SHEET_GAS_TOKEN"
EVENT_SOURCE_NAME = "spreadsheet"
JST = ZoneInfo("Asia/Tokyo")
HTTP_TIMEOUT_SEC = 15.0
MAX_TITLE_LENGTH = 200

# Wave 2 FU-19 と整合: タイトル先頭にこれらが付いていたら skip
CANCELLED_PREFIXES = ("中止", "キャンセル", "[CANCELLED]", "[CANCELED]")

_SOURCE_LABEL = f"{EVENT_KB_SOURCE_PREFIX}:{EVENT_SOURCE_NAME}"


class SheetsEventSource:
    def __init__(self) -> None:
        self.url = os.getenv(GAS_URL_ENV, "").strip()
        self.token = os.getenv(GAS_TOKEN_ENV, "").strip()
        if not self.url or not self.token:
            logger.warning(
                "%s / %s not configured; SheetsEventSource disabled",
                GAS_URL_ENV, GAS_TOKEN_ENV,
            )

    async def fetch_events(self) -> List[EventSourceRecord]:
        if not self.url or not self.token:
            return []

        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SEC) as client:
                resp = await client.get(self.url, params={"token": self.token})
                resp.raise_for_status()
                payload = resp.json()
        except Exception as exc:
            logger.warning("GAS event API fetch failed: %s", exc)
            return []

        if "error" in payload:
            logger.warning("GAS event API returned error: %s", payload.get("error"))
            return []

        raw_events = payload.get("events", [])
        records: List[EventSourceRecord] = []
        seen: set[tuple[str, str]] = set()  # dedup (title, date)

        today_jst = datetime.now(JST).date()

        for ev in raw_events:
            title_raw = ev.get("title", "")
            date_raw = ev.get("date", "")
            row_num = ev.get("row", -1)

            title = sanitize_input(str(title_raw).strip(), MAX_TITLE_LENGTH)
            if not title:
                continue

            # キャンセル判定 (Wave 2 FU-19 整合)
            if any(title.startswith(p) for p in CANCELLED_PREFIXES):
                logger.debug("Skipping cancelled event row %s: %s", row_num, title)
                continue

            # 日付パース
            try:
                event_date = datetime.strptime(date_raw, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                logger.debug("Skipping invalid date row %s: %s", row_num, date_raw)
                continue

            # 過去日除外 (Wave 2 FU-18 整合)
            if event_date < today_jst:
                continue

            # 重複除外
            key = (title, date_raw)
            if key in seen:
                logger.debug("Skipping duplicate row %s: %s", row_num, title)
                continue
            seen.add(key)

            # ISO datetime (時刻は 00:00 JST 固定、existing schema に時刻列なし)
            start_iso = datetime.combine(
                event_date, datetime.min.time(), tzinfo=JST
            ).isoformat()

            records.append(
                EventSourceRecord(
                    external_id=f"sheet:{row_num}:{title}:{date_raw}",
                    title=title,
                    start=start_iso,
                    end="",  # 終了時刻不明 (schema に列なし)
                    description="",
                    location="Engineer Cafe",
                    url="",
                    source=EVENT_SOURCE_NAME,
                )
            )

        logger.info(
            "SheetsEventSource fetched %d events (raw=%d, sheet=%s, fetched_at=%s)",
            len(records),
            len(raw_events),
            payload.get("sheet"),
            payload.get("fetched_at"),
        )
        return records
```

### 4.3 `sync_event_kb.py` 拡張

既存 `backend/scripts/sync_event_kb.py` に flag 追加:

```python
parser.add_argument(
    "--include-spreadsheet",
    action="store_true",
    help="Also fetch from Engineer Cafe events via GAS Web App.",
)

# ...
records: list[EventSourceRecord] = []

if args.ics_url or args.ics_file:
    records.extend(await parse_ics_event_records(...))

if args.include_spreadsheet:
    from backend.services.sheets_event_source import SheetsEventSource
    records.extend(await SheetsEventSource().fetch_events())

# connpass は既存ロジック...

await sync_event_kb_records(records, ...)
```

### 4.4 Cloud Scheduler ジョブ body 更新

```bash
gcloud scheduler jobs update http event-kb-sync-daily \
  --location=asia-northeast1 \
  --project=aipartner-426616 \
  --message-body='{"args": ["--ics-url", "<url>", "--include-spreadsheet"]}'
```

### 4.5 EventAgent merge 優先順位 (Wave 2 Theme C / FU-20)

`backend/agents/event_agent.py:_merge_events` の優先順位:

```
1. spreadsheet (source="spreadsheet")  ← SoT、最優先
2. connpass    (source="connpass")     ← 外部告知
3. calendar    (source="google_calendar") ← 補助
```

同 (title, date) 重複は spreadsheet 側が勝つ。spreadsheet にない event は connpass / calendar からそのまま採用 (Cafe 主催以外の外部イベント補完)。

### 4.6 依存追加

```toml
# backend/pyproject.toml
# httpx は既存 (FastAPI 経由で既に依存)
# 追加依存なし — Sheets API client や google-auth は不要 (シンプル!)
```

---

## 5. Cafe Staff 向け運用 (変更なし)

**Staff の運用は現状通り維持**。新規イベントは従来通り `alert_discord` シートに 2 列 (イベント名 + 日付) で追加するだけ。

### 5.1 既存ワークフロー (確認のみ)

1. Cafe staff が `alert_discord` シートに新規行追加 (A=イベント名, B=日付)
2. 翌日 09:00 JST の Cloud Scheduler 実行で Backend に反映
3. ナビゲーターが「今週のイベント」などのクエリで応答に含む

### 5.2 中止イベントの記入規約 (Wave 2 FU-19 整合)

中止イベントを応答から除外したい場合、staff は以下のいずれかで対応:
- **行削除**: その行を Sheets の右クリック「行を削除」で消す
- **タイトル prefix**: タイトル先頭に `中止` `キャンセル` `[CANCELLED]` を付ける (例: `中止: 朝活もくもく 5/18`)
  → Backend 側 (§4.2 `CANCELLED_PREFIXES`) で skip

### 5.3 日付形式

Backend は以下を許容:
- `2026-05-20` (推奨, ISO 8601)
- `2026/05/20` (許容)
- `5/20/2026` (許容, US 形式)
- Date オブジェクトとして Sheets が認識した値 (Apps Script が ISO 化)

不可:
- `2026年5月20日` (パース失敗、skip)
- `5/20` (年が無いのでパース失敗)

---

## 6. terisuke 向け実施手順 (Day 0)

### Step 1: GAS Web App デプロイ
1. スプレッドシート → 拡張機能 → Apps Script
2. 新規ファイル `EventApi.gs` を追加し §3.2 のコードを貼り付け
3. Script Properties に `SHARED_TOKEN` を設定 (§3.3, openssl rand -hex 32 で生成)
4. デプロイ (§3.4) → Web App URL を取得

### Step 2: Secret Manager 登録
```bash
echo -n "<WEB_APP_URL>" | gcloud secrets create EVENT_SHEET_GAS_URL \
  --data-file=- --project=aipartner-426616

echo -n "<SHARED_TOKEN>" | gcloud secrets create EVENT_SHEET_GAS_TOKEN \
  --data-file=- --project=aipartner-426616
```

### Step 3: Cloud Run env bind
```bash
gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest" \
  --update-secrets="EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest"
```

### Step 4: 動作確認 (terisuke 手元)
```bash
TOKEN="<SHARED_TOKEN>"
URL="<WEB_APP_URL>"
curl "${URL}?token=${TOKEN}" | jq '.count, .events[0:3]'
# expect: count >= 1, events に最初 3 件が出る
```

### Step 5: Backend engineer に共有
- `EVENT_SHEET_GAS_URL` Secret 名
- `EVENT_SHEET_GAS_TOKEN` Secret 名
- Web App URL の動作確認結果

---

## 7. 将来拡張 (optional, 本 PR スコープ外)

シートに列を増やしたくなった場合、変更は **GAS 側 (`EventApi.gs`) のみ**。Backend (`SheetsEventSource`) は JSON のフィールドが増えたら使う、無ければ default 値で動く設計。

### 想定追加列 (例)

| 追加列 | GAS 側変更 | Backend 側変更 |
|--------|-----------|--------------|
| C: 時間 | `getRange('A3:C')` + 時刻 ISO 化 | `start_iso` 構築に追加情報を使う |
| D: 場所 | `getRange('A3:D')` + 場所返却 | `EventSourceRecord.location` 差し替え |
| E: URL | `getRange('A3:E')` + URL 返却 | `EventSourceRecord.url` 差し替え |
| F: 英語タイトル | 同上 | EventAgent multi-lingual response で使用 |

Wave 2 完了後の Phase 3+ で必要になった段階で別途設計。今は **既存 2 列のみ** で運用開始。

---

## 8. Open Questions / Risks

| # | Question / Risk | Owner | 期限 |
|---|----------------|-------|------|
| Q1 | 既存 `alert_discord` シートに現在何件記入されているか? | terisuke | Day 0 |
| Q2 | Cafe staff の入力ペース (週何件追加?) | terisuke | 観測 |
| Q3 | キャンセル時に「行削除」と「prefix `中止`」のどちらを staff に推奨するか? | terisuke | Day 0 |
| Q4 | 同日複数イベントの順序 (シート行順 vs 時刻順) は? | 検討 | 観測後 |
| R1 | GAS Web App URL 漏洩 → 第三者が events 一覧を取得可能 | terisuke | token rotation 手順を runbook 化 (§6.1 の再実行) |
| R2 | terisuke の Google アカウント停止/退職 → GAS 実行が止まる | terisuke | 引き継ぎ手順 (新管理者で再デプロイ) |
| R3 | スプレッドシート URL 変更 → GAS は同 ID なので影響なし | - | - |
| R4 | Apps Script の実行 quota (日次 90 分) 超過リスク | terisuke | 通常運用 (1日1回 cron) では非問題 |
| R5 | staff のフォーマット違反 (`5/20` など年なし) → skip | Backend engineer | sync_event_kb.py で skip 件数を log + alert |

---

## 9. 完了条件

### Day 0 (terisuke)
- [ ] GAS Web App デプロイ (§6 Step 1〜4)
- [ ] Secret Manager 登録 (§6 Step 2)
- [ ] Cloud Run env bind (§6 Step 3)
- [ ] 動作確認 (`curl ${URL}?token=${TOKEN}` で events 返却) (§6 Step 4)
- [ ] Backend engineer に共有 (§6 Step 5)

### Backend engineer (Wave 2 Theme C)
- [ ] `backend/services/sheets_event_source.py` 新規実装 (§4.2)
- [ ] `backend/scripts/sync_event_kb.py` に `--include-spreadsheet` 追加 (§4.3)
- [ ] Cloud Scheduler job body 更新 (§4.4)
- [ ] `backend/agents/event_agent.py:_merge_events` priority order 反映 (§4.5)
- [ ] unit test: GAS response の mock + パース・skip ロジック検証
- [ ] live: `curl /api/chat "今日のイベントは?"` で spreadsheet 由来 event が応答に出る
- [ ] ruff + black + pytest 全 PASS

### Wave 2 Theme C 統合
- [ ] FU-07 (#851) close + FU-18 (#869) + FU-19 (#870) + FU-20 (#871) all close
- [ ] RAGAS event ground truth 更新 + ja >= 0.85
- [ ] Theme C Sub-Epic #858 close

---

## 10. Reference

- FU-07 設計 doc: `docs/plans/event-source-spreadsheet-integration-2026-05-17.md`
- Wave 2 handoff: `docs/plans/wave2-date-audio-calendar-handoff-2026-05-17.md` §4
- FU-02 (Cloud Scheduler ✅ done): Issue #844
- FU-07 (Spreadsheet 実装): Issue #851 / PR #852
- Wave 2 Theme C: Issue #858
- Apps Script Web Apps doc: https://developers.google.com/apps-script/guides/web
- Apps Script Properties Service: https://developers.google.com/apps-script/reference/properties
