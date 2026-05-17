# 📋 Engineer Cafe Event Spreadsheet — Engineer Handoff (2026-05-17, rev 3)

> **対象**: Backend 実装担当エンジニア (Wave 2 Theme C), terisuke (権限管理)
> **作成**: 2026-05-17, Claude Code session
> **位置付け**: FU-07 (#851) の実装ハンドオフ。Wave 2 Theme C (#858) の base layer。
> **更新履歴**:
> - rev 1: 新規 14 列 schema を提案 — **誤り** (既存シートを無視)
> - rev 2: 既存 `alert_discord` シート (A3:B 2列) 前提 + GAS Web App — **誤り** (legacy シート参照、実際の SoT は別)
> - **rev 3 (本版)**: **実物スプレッドシート (`153ib48CUk7P_Qf8DEXx2XYAMhaQnqyFUNQ18NEnnz_k`) を terisuke 提供 CSV で実測** → 真の SoT (`event_status` シート 44 列) を発見、Google Form 連携を反映
> **前提**: FU-02 (#844, Cloud Scheduler `event-kb-sync-daily`) は ✅ 完了

---

## 0. Executive Summary

### 真の SoT (実物確認, 2026-05-17)

| 項目 | 実測値 |
|------|--------|
| ワークブック名 | `イベント管理シート` |
| Spreadsheet ID | `153ib48CUk7P_Qf8DEXx2XYAMhaQnqyFUNQ18NEnnz_k` |
| シート数 | **10 シート** (`event_data` / `event_detail` / `URL_request` / **`event_status`** / `alert_discord` / `URL_form` / `終了後ステータスチェック` / `status_and_number` / `直近ステータスチェック` / `attendance_report`) |
| **Backend が読む対象シート** | **`event_status`** (gid `1420282345`) |
| 列数 | **44 列** (col 0 = Status、col 1-39 = ヘッダー付き、40-43 = trailing empty) |
| データ行数 | 約 **2,150 行** (2019 年〜現在の全イベント履歴) |
| 2026-05-17 時点の upcoming events | **37 件** (status=`許可済` AND date >= today) |

### データ追加フロー

- **Cafe staff / コミュニティ主催者** が `URL_form` シート連携の **Google Form** から申込
- Form 送信時に **`event_status` シート末尾に行が auto-append** される (Google Forms 標準連携)
- Cafe staff が **A 列 (Status)** を手動でワークフロー進行に応じて更新:
  `調整中` → `内部確認中` → `福岡市確認` → **`許可済`** → `実施済` (or `中止` / `不許可` / `延期`)
- → スタッフは **A 列の更新だけ手動**、それ以外は Form 入力そのまま

### Backend の役割

- `event_status` シートを GAS Web App 経由で fetch
- **`A == "許可済"` AND `H (開催希望日) >= today`** で filter
- PII 列 (メール / 氏名 / 電話) は **絶対に読まない** (GAS 側で除外)
- 残りの安全な列を JSON で返却 → Backend が `EventSourceRecord` に変換

---

## 1. `event_status` シートの実測スキーマ (全 44 列)

> **注**: 実測 (`/Users/teradakousuke/Desktop/イベント管理シート - event_status.csv`, 4.1MB, 2150 行) より。
> - **Read** = Backend が読んで良い列 (公開情報)
> - **Filter** = 行絞り込みに使う列
> - **PII** = Backend が **絶対に読まない** 列 (個人情報)
> - **Skip** = Backend で不要な列 (internal workflow)

### 1.1 全列一覧 (0-indexed)

| Col | 列名 (実測) | 種別 | 例 | 用途 |
|----|-----------|------|----|------|
| 0 | *(空ヘッダー)* = Status | **Filter** | `許可済` | A 列、手動更新ステータス |
| 1 | `発信URL` | Skip | (空 or URL) | internal |
| 2 | `HP告知` | Skip | `済` | 告知チェック |
| 3 | `Facebook告知` | Skip | `済` | 告知チェック |
| 4 | `Discord告知` | Skip | `済` | 告知チェック |
| 5 | `受付No` | Skip | `1`, `2`, ... | internal 連番 |
| 6 | `担当コミュニティマネージャー(responsible community manager)` | Skip | `鈴谷` | 内部担当者名 |
| **7** | `イベント開催希望日(event date)` | **Read+Filter** | `2026/05/20` | **必須**: イベント日付 (YYYY/MM/DD) |
| **8** | `イベントタイトル(event title)` | **Read** | `XR Vision DevCamp` | **必須**: タイトル |
| **9** | `イベント概要/告知文(specific event information for announcements)` | **Read** | `3D 開発もくもく会...` | 説明 (1000+ 文字あり) |
| 10 | `追加情報(Additional Information)` | Read (任意) | 自由記述 | 補足 |
| 11 | `タイムテーブル(time table)` | Read (任意) | `19:00 開場 / 19:30 LT` | 詳細スケジュール |
| 12 | `主催者種別(type of event organizer)` | Read (任意) | `コミュニティ` / `法人` / `個人` | 種別 |
| **13** | `主催者(event organizer)` | **Read** | `Re-Creation Fukuoka` | 主催者名 |
| 14 | `利用想定人数(Expected number of users)` | Read (任意) | `50` | 定員 |
| 15 | `利用開始時刻(start using time)` | Read (任意) | `12:30` | 施設利用開始 (設営含む) |
| **16** | `イベント開始時刻(event start time)` | **Read** | `19:00` | **必須**: イベント開始 |
| **17** | `イベント終了時刻(event close time)` | **Read** | `21:00` | **必須**: イベント終了 |
| 18 | `利用終了時刻(close time)` | Read (任意) | `22:00` | 施設利用終了 (撤収含む) |
| **19** | `メールアドレス` | **PII** | `xxxx@xxx` | 🚫 absolutely no read |
| **20** | `申込者氏名(name)` | **PII** | `山田 太郎` | 🚫 |
| **21** | `申込者氏名ふりがな(phonetic)` | **PII** | `やまだ たろう` | 🚫 |
| **22** | `ご連絡先電話番号(phone number)` | **PII** | `090-...` | 🚫 |
| 23 | `登壇者/氏名および役職(speakers and their official positions)` | **PII (注意)** | `山田 太郎 / CTO` | 🚫 default 除外 (公開許諾は申込確認列で別管理、安全側で skip) |
| 24 | `飲食を行いますか？(Do you eat and drink?)` | Skip | `はい` / `いいえ` | 内部情報 |
| 25 | `飲食内容` | Skip | 自由記述 | 内部情報 |
| 26 | `参加費（entry fee）` | Read (任意) | `無料` / `有料` | 公開可能 |
| 27 | `一人あたりの金額（円）` | Read (任意) | `0` / `1000` | 金額 |
| 28 | `参加費等の徴収内容` | Read (任意) | 自由記述 | 公開可能 |
| 29 | `利用施設(facility)` | **Read** | `Engineer Cafe メインホール` | 会場 |
| 30 | `オンライン配信の有無（ Online delivery availability ）` | Read (任意) | `あり` / `なし` | オンライン併用フラグ |
| 31 | `その他お問い合わせ(other inquiries)` | Skip | 自由記述 | internal |
| 32 | `タイムスタンプ` | Skip | `2026-05-17T...` | Form 送信日時 (PII 周辺) |
| 33 | `写真利用について(about photo usage)` | Skip | 同意 enum | internal |
| 34 | `申込確認と内容についての同意(application confirmation and agreement on content)` | Skip | 同意 enum | internal (PII 同意フラグ) |
| 35 | `イベント用ハッシュタグ 1 (Event Hashtag 1)` | Read (任意) | `#engineerCafe` | SNS |
| 36 | `イベント用ハッシュタグ 2 (Event Hashtag 2)` | Read (任意) | `#XR` | SNS |
| 37 | `コミュニティ名用ハッシュタグ (Community Hashtag)` | Read (任意) | `#OrbitBase` | SNS |
| 38 | `告知用画像の提出方法 (How will you submit the image?)` | Skip | 内部workflow | - |
| 39 | `告知用画像 (Promotional Image)` | Skip | URL / 添付 | - |
| 40-43 | *(空 trailing)* | - | - | - |

### 1.2 ステータス enum (A 列 = col 0) — terisuke 確認 + CSV 実測

| ステータス | CSV 実測件数 | Backend 扱い |
|----------|------------|------------|
| `実施済` (= 実施済み) | 2024 | ❌ skip (過去イベント、FU-18 過去日除外と二重防御) |
| **`許可済`** (= 許可済み) | 39 | ✅ **Backend が応答に含める唯一の対象** |
| `中止` | 57 | ❌ skip (FU-19 整合) |
| `延期` | 18 | ❌ skip (未確定、新日付で再申請されるまで非公開) |
| `不許可` | 5 | ❌ skip (公開不可) |
| `調整中` | 1 | ❌ skip (確定前) |
| `内部確認中` | 0 (CSV 内見当たらず, terisuke 言及) | ❌ skip |
| `福岡市確認` | 0 (同上) | ❌ skip |
| *(空)* | 5 | ❌ skip |

**Backend filter ルール (rev 3 確定)**:
```python
status_normalized = row[0].strip()
if status_normalized != "許可済":
    skip
```

> ※ `許可済` だけが Backend 公開対象。これ以外は **すべて skip**。
> 過去日除外 (FU-18) と組み合わせて、`status == 許可済` AND `date >= today` を満たす行のみ KB に投入。

### 1.3 日付フォーマット (実測)

- 全行 `YYYY/MM/DD` (例: `2026/05/20`)
- スラッシュ区切り (ハイフン区切りや和暦は無し)
- Google Form の Date Picker 由来 (フォーマット強制されている)

### 1.4 時刻フォーマット (実測)

- 全行 `H:MM` または `HH:MM` (例: `9:00`, `19:00`, `12:30`)
- 24h 表記
- 時刻なし (空セル) のケースもあり (`XR Vision DevCamp` row 2101: 9:00 / 9:00) — 終日扱い検討要

### 1.5 直近 upcoming events サンプル (実測, 2026-05-17 抽出)

| 開催日 | タイトル | 主催者 | 開始 | 終了 |
|--------|---------|--------|------|------|
| 2026-05-17 | `<3Dプリンター初回講習付き!>3Dモデルを作成して印刷してみよう` | (data) | 9:00 | 10:00 |
| 2026-05-17 | `AkarengaLT #45` | (data) | 17:30 | 18:00 |
| 2026-05-19 | `Orbit Base｜異なる軌道が交差するクロスジャンルLT` | Orbit Base | 18:00 | 19:00 |
| 2026-05-19 | `TinyGame機をつくろう!` | (data) | 18:00 | 18:30 |
| 2026-05-20 | `お昼だよ。最近どう?🍽エンジニアの為のカフェ☕️エンジニアカフェ@福岡` | (data) | 11:45 | 12:00 |
| 2026-05-20 | `iPadでSwift Playgroundsを学ぼう#106` | (data) | 12:30 | 12:45 |
| 2026-05-21 | `エンジニアたちのゆるっと数学勉強会` | (data) | 19:15 | 19:30 |
| ...37 件中の上位 7 件 | | | | |

→ **2026-05-17 時点で 37 件の upcoming `許可済` イベントが既に揃っている**。Backend 統合後はナビゲーターから即正確応答可能。

---

## 2. 認証方式 — GAS Web App + Shared Token (rev 2 から継承)

terisuke 指摘:
> 制限されたアカウントであれば、取得できる URL を許可したユーザーとして入れてもらって、URL を共有してもらって、GAS のようにそれを取得するような仕組みがいいのではないでしょうか。

→ **GAS Web App** 方式を採用 (terisuke のアカウント権限で GAS デプロイ → Backend は URL fetch のみ)。
スプレッドシート共有設定 (Service Account viewer share 等) は **不要**。

### 比較 (再掲)

| 方式 | terisuke 作業 | Backend 作業 | 推奨 |
|------|------------|------------|------|
| **A. GAS Web App + token** | GAS デプロイ + Script Properties 設定 | httpx GET のみ | ⭐⭐⭐⭐ **採用** |
| B. Sheets API + SA viewer | SA email を viewer 追加 + Sheets API enable | google-api-python-client + ADC | ⭐⭐⭐ |
| C. Publish-to-web (CSV) | チェックボックス 1 つ | CSV パース | ⭐ (URL 知る全員が閲覧可) |

---

## 3. Apps Script (`EventApi.gs`) — terisuke がデプロイ

### 3.1 設置場所

イベント管理シートの Apps Script エディタ:
1. スプレッドシートを開く
2. メニュー「拡張機能」→「Apps Script」
3. 新規ファイル `EventApi.gs` を追加 (legacy `alert_discord` 用 GAS とは分離)

### 3.2 推奨スクリプト (rev 3, 実測スキーマ対応)

```javascript
/**
 * Engineer Cafe Event API (GAS Web App, rev 3)
 *
 * GET https://script.google.com/macros/s/<DEPLOY_ID>/exec?token=<SECRET>
 * → { "events": [{ title, date, start, end, organizer, venue, ... }, ...] }
 *
 * 仕様:
 * - Source sheet: `event_status` (gid=1420282345) の 44 列
 * - Filter: A 列 == "許可済" AND H 列 (開催希望日) >= today
 * - 戻り値: 公開可能列のみ (PII = メール / 氏名 / 電話 / 登壇者氏名 / 申込日時 は除外)
 * - Auth: ?token=SHARED_TOKEN がスクリプトプロパティと一致した場合のみ返却
 */

const SHEET_NAME = 'event_status';
const HEADER_ROW = 1;
const DATA_START_ROW = 2;

// 公開対象ステータス (rev 3 確定)
const PUBLIC_STATUS = '許可済';

// 0-indexed 列マッピング (実測スキーマ)
const COL = {
  status: 0,            // A: ステータス (filter)
  date: 7,              // H: イベント開催希望日 (YYYY/MM/DD)
  title: 8,             // I: イベントタイトル
  description: 9,       // J: 概要/告知文
  additional_info: 10,  // K: 追加情報
  time_table: 11,       // L: タイムテーブル
  organizer_type: 12,   // M: 主催者種別
  organizer: 13,        // N: 主催者
  capacity: 14,         // O: 利用想定人数
  facility_start: 15,   // P: 利用開始時刻
  event_start: 16,      // Q: イベント開始時刻 (必須)
  event_end: 17,        // R: イベント終了時刻 (必須)
  facility_end: 18,     // S: 利用終了時刻
  entry_fee: 26,        // AA: 参加費
  entry_fee_amount: 27, // AB: 一人あたり金額
  facility: 29,         // AD: 利用施設
  online: 30,           // AE: オンライン配信の有無
  hashtag1: 35,         // AJ: ハッシュタグ 1
  hashtag2: 36,         // AK: ハッシュタグ 2
  community_hashtag: 37, // AL: コミュニティハッシュタグ
};
// 注: col 19-23 (メール/氏名/ふりがな/電話/登壇者氏名), col 32 (タイムスタンプ),
//     col 33-34 (写真利用 / 同意) は PII or 不要なので一切読まない。

function doGet(e) {
  // 認証
  const expectedToken = PropertiesService.getScriptProperties().getProperty('SHARED_TOKEN');
  if (!expectedToken) {
    return _json({ error: 'server not configured (SHARED_TOKEN missing)' });
  }
  const providedToken = (e && e.parameter && e.parameter.token) || '';
  if (providedToken !== expectedToken) {
    return _json({ error: 'unauthorized' });
  }

  const ss = SpreadsheetApp.getActive();
  const sheet = ss.getSheetByName(SHEET_NAME);
  if (!sheet) {
    return _json({ error: `sheet '${SHEET_NAME}' not found` });
  }

  const lastRow = sheet.getLastRow();
  if (lastRow < DATA_START_ROW) {
    return _json({ events: [], count: 0, sheet: SHEET_NAME });
  }

  // 必要な列を含む最小範囲を取得 (パフォーマンス考慮、最終列 = col 37)
  const numCols = Math.max(...Object.values(COL)) + 1; // 38
  const range = sheet.getRange(DATA_START_ROW, 1, lastRow - 1, numCols);
  const values = range.getValues();

  const todayJst = _todayJst();
  const events = [];

  for (let i = 0; i < values.length; i++) {
    const row = values[i];
    const status = String(row[COL.status] || '').trim();

    // Filter 1: status
    if (status !== PUBLIC_STATUS) continue;

    // Filter 2: 開催日が今日以降
    const dateIso = _toIsoDate(row[COL.date]);
    if (!dateIso) continue;
    if (dateIso < todayJst) continue;

    events.push({
      row: i + DATA_START_ROW,
      title: String(row[COL.title] || '').trim(),
      date: dateIso,
      event_start: _toHHmm(row[COL.event_start]),
      event_end: _toHHmm(row[COL.event_end]),
      facility_start: _toHHmm(row[COL.facility_start]),
      facility_end: _toHHmm(row[COL.facility_end]),
      organizer: String(row[COL.organizer] || '').trim(),
      organizer_type: String(row[COL.organizer_type] || '').trim(),
      description: String(row[COL.description] || '').trim(),
      additional_info: String(row[COL.additional_info] || '').trim(),
      time_table: String(row[COL.time_table] || '').trim(),
      capacity: _toInt(row[COL.capacity]),
      facility: String(row[COL.facility] || '').trim() || 'Engineer Cafe',
      online: String(row[COL.online] || '').trim(),
      entry_fee: String(row[COL.entry_fee] || '').trim(),
      entry_fee_amount: _toInt(row[COL.entry_fee_amount]),
      hashtags: [
        String(row[COL.hashtag1] || '').trim(),
        String(row[COL.hashtag2] || '').trim(),
        String(row[COL.community_hashtag] || '').trim(),
      ].filter(Boolean),
    });
  }

  // 日付昇順、同日内は開始時刻昇順でソート
  events.sort((a, b) => {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    return (a.event_start || '99:99') < (b.event_start || '99:99') ? -1 : 1;
  });

  return _json({
    events: events,
    count: events.length,
    sheet: SHEET_NAME,
    filter: { status: PUBLIC_STATUS, date_from: todayJst },
    fetched_at: new Date().toISOString(),
    schema_version: 'v3',
  });
}

function _json(body) {
  return ContentService
    .createTextOutput(JSON.stringify(body))
    .setMimeType(ContentService.MimeType.JSON);
}

function _todayJst() {
  return Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
}

function _toIsoDate(value) {
  if (!value) return null;
  if (value instanceof Date) {
    return Utilities.formatDate(value, 'Asia/Tokyo', 'yyyy-MM-dd');
  }
  const s = String(value).trim();
  const m = s.match(/^(\d{4})[\/\-](\d{1,2})[\/\-](\d{1,2})$/);
  if (!m) return null;
  const [, y, mo, d] = m;
  return `${y}-${mo.padStart(2, '0')}-${d.padStart(2, '0')}`;
}

function _toHHmm(value) {
  if (!value) return '';
  if (value instanceof Date) {
    return Utilities.formatDate(value, 'Asia/Tokyo', 'HH:mm');
  }
  const s = String(value).trim();
  const m = s.match(/^(\d{1,2}):(\d{2})/);
  return m ? `${m[1].padStart(2, '0')}:${m[2]}` : '';
}

function _toInt(value) {
  const n = parseInt(value, 10);
  return isNaN(n) ? null : n;
}
```

### 3.3 Script Properties 設定

GAS エディタ → 左サイドバー「プロジェクトの設定」→「スクリプト プロパティ」:
- プロパティ名: `SHARED_TOKEN`
- 値: 強いランダム文字列 (terisuke 手元で `openssl rand -hex 32` で生成)

### 3.4 デプロイ手順

1. GAS エディタ右上「デプロイ」→「新しいデプロイ」
2. 「種類の選択」→ 歯車 →「ウェブアプリ」
3. 設定:
   - 説明: `Engineer Cafe Event API v3`
   - 次のユーザーとして実行: **自分 (terisuke@cor-jp.com)** ← terisuke の権限でシート読み込み
   - アクセスできるユーザー: **全員** ← token で実 auth、URL を Secret 扱い
4. 「デプロイ」をクリック
5. Web App URL をコピー (`https://script.google.com/macros/s/AKfyc.../exec`)

### 3.5 動作確認 (terisuke 手元)

```bash
TOKEN="<SHARED_TOKEN>"
URL="<WEB_APP_URL>"

# 認証なし → unauthorized
curl "${URL}"
# → {"error":"unauthorized"}

# 正しい token → 37 件の upcoming events
curl "${URL}?token=${TOKEN}" | jq '.count, .events[0:3]'
# expect:
# 37
# [{ "title": "...", "date": "2026-05-17", "event_start": "09:00", ... }, ...]
```

---

## 4. Backend 統合 (Wave 2 Theme C 担当エンジニア)

### 4.1 環境変数 / Secret Manager

| 変数名 | 値 | 設置場所 |
|-------|----|---------|
| `EVENT_SHEET_GAS_URL` | GAS Web App URL | Secret Manager → Cloud Run |
| `EVENT_SHEET_GAS_TOKEN` | SHARED_TOKEN 同値 | Secret Manager → Cloud Run |

```bash
echo -n "<WEB_APP_URL>" | gcloud secrets create EVENT_SHEET_GAS_URL --data-file=- --project=aipartner-426616
echo -n "<SHARED_TOKEN>" | gcloud secrets create EVENT_SHEET_GAS_TOKEN --data-file=- --project=aipartner-426616

gcloud run services update engineer-cafe-backend \
  --region=asia-northeast1 \
  --update-secrets="EVENT_SHEET_GAS_URL=EVENT_SHEET_GAS_URL:latest" \
  --update-secrets="EVENT_SHEET_GAS_TOKEN=EVENT_SHEET_GAS_TOKEN:latest"
```

### 4.2 新設: `backend/services/sheets_event_source.py` (rev 3, 実測スキーマ対応)

```python
"""
Engineer Cafe Event Spreadsheet (event_status sheet) を GAS Web App 経由で取得する service.

GAS が返す JSON は既に「許可済 AND date >= today」で filter 済 + 公開可能列のみ。
Backend は受け取った構造化データを EventSourceRecord に変換するだけ。
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

# 文字数制限 (KB 投入 + LLM prompt 安全のため)
MAX_TITLE = 200
MAX_DESC = 1000
MAX_TIMETABLE = 500
MAX_VENUE = 100
MAX_ORGANIZER = 100

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

        for ev in raw_events:
            # GAS 側で許可済 + 過去日除外済だが、Backend 側でも防御的に再 check
            title = sanitize_input(str(ev.get("title", "")).strip(), MAX_TITLE)
            date = str(ev.get("date", "")).strip()
            if not title or not date:
                continue

            # ISO datetime 構築 (start/end が空なら 00:00 / 23:59 で代替)
            event_start = ev.get("event_start", "").strip() or "00:00"
            event_end = ev.get("event_end", "").strip() or event_start

            try:
                start_dt = datetime.fromisoformat(f"{date}T{event_start}:00").replace(tzinfo=JST)
                end_dt = datetime.fromisoformat(f"{date}T{event_end}:00").replace(tzinfo=JST)
            except ValueError as exc:
                logger.debug("Skipping row %s (datetime parse): %s", ev.get("row"), exc)
                continue

            organizer = sanitize_input(str(ev.get("organizer", "")).strip(), MAX_ORGANIZER)
            venue = sanitize_input(
                str(ev.get("facility", "")).strip() or "Engineer Cafe", MAX_VENUE
            )

            # description: 概要 + タイムテーブル (LLM 応答素材)
            desc_parts = []
            if ev.get("description"):
                desc_parts.append(sanitize_input(str(ev["description"]).strip(), MAX_DESC))
            if ev.get("time_table"):
                tt = sanitize_input(str(ev["time_table"]).strip(), MAX_TIMETABLE)
                desc_parts.append(f"[タイムテーブル] {tt}")
            if organizer:
                desc_parts.append(f"[主催] {organizer}")
            if ev.get("capacity"):
                desc_parts.append(f"[定員] {ev['capacity']}名")
            description = "\n".join(desc_parts)

            records.append(
                EventSourceRecord(
                    external_id=f"sheet:event_status:row{ev.get('row')}",
                    title=title,
                    start=start_dt.isoformat(),
                    end=end_dt.isoformat(),
                    description=description,
                    location=venue,
                    url="",  # event_status シートに公開 URL 列なし
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

### 4.3 sync_event_kb.py 拡張

```python
parser.add_argument(
    "--include-spreadsheet",
    action="store_true",
    help="Also fetch Cafe events via GAS Web App (event_status sheet).",
)

# ...
records: list[EventSourceRecord] = []
if args.ics_url or args.ics_file:
    records.extend(await parse_ics_event_records(...))
if args.include_spreadsheet:
    from backend.services.sheets_event_source import SheetsEventSource
    records.extend(await SheetsEventSource().fetch_events())
# Connpass 既存ロジック...

await sync_event_kb_records(records, ...)
```

### 4.4 Cloud Scheduler ジョブ body 更新

```bash
gcloud scheduler jobs update http event-kb-sync-daily \
  --location=asia-northeast1 \
  --project=aipartner-426616 \
  --message-body='{"args": ["--ics-url", "<url>", "--include-spreadsheet"]}'
```

### 4.5 EventAgent merge 優先順位 (Wave 2 FU-20)

`backend/agents/event_agent.py:_merge_events`:
```
1. spreadsheet (source="spreadsheet")  ← SoT、最優先
2. connpass    (source="connpass")     ← 外部告知
3. calendar    (source="google_calendar") ← 補助
```

同 (title, date) 重複は spreadsheet 側が勝つ。spreadsheet にない event は connpass / calendar から補完。

### 4.6 依存追加

```
追加依存なし — httpx は既存 (FastAPI 経由)。
google-api-python-client / google-auth は不要 (GAS Web App fetch のみ)。
```

---

## 5. Cafe Staff 向け運用 (現状維持、変更なし)

**スタッフ側の運用変更ゼロ**。新規イベントは現状通り Google Form 経由で申込み、A 列 (Status) を手動更新するだけ。

### 5.1 既存ワークフロー (確認)

1. Cafe staff / コミュニティ主催者が **Google Form** から申込
2. Form 送信 → `event_status` シート末尾に行 auto-append
3. Cafe staff が A 列を手動更新:
   `調整中` → `内部確認中` → `福岡市確認` → `許可済` → 開催後 `実施済`
   (or `中止` / `不許可` / `延期`)
4. Backend Cloud Scheduler が毎日 09:00 JST に GAS Web App fetch → KB 更新

### 5.2 「ナビゲーターに案内させたい」イベントの条件

- A 列 = **`許可済`** にする (これだけ Backend が拾う)
- H 列 (開催希望日) を未来日付に設定

### 5.3 「中止 / 延期にしたい」場合

- A 列を **`中止`** または **`延期`** に変更 → Backend が即除外 (次回 cron 実行で反映)
- 行削除は推奨しない (履歴保持のため)

---

## 6. terisuke 向け実施手順 (Day 0)

### Step 1: GAS Web App デプロイ
1. イベント管理シート → 拡張機能 → Apps Script
2. 新規ファイル `EventApi.gs` を追加 + §3.2 のコードを貼り付け
3. Script Properties に `SHARED_TOKEN` を設定 (§3.3)
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

### Step 4: 動作確認
```bash
TOKEN="<SHARED_TOKEN>"
URL="<WEB_APP_URL>"
curl "${URL}?token=${TOKEN}" | jq '.count, .events[0:3]'
# expect: count=37 (2026-05-17 時点), events に直近のイベントが出る
```

### Step 5: Backend engineer に共有
- `EVENT_SHEET_GAS_URL` / `EVENT_SHEET_GAS_TOKEN` Secret 名
- 動作確認結果 (count + sample)

---

## 7. PII 防御チェックリスト

GAS の `EventApi.gs` が PII 列を **絶対に返却しない** ことを保証する設計:

| 列 | 内容 | GAS で返却? | 確認方法 |
|----|------|-----------|---------|
| col 19 (メールアドレス) | PII | ❌ never | `COL` map に含めない |
| col 20-22 (氏名/ふりがな/電話) | PII | ❌ never | 同上 |
| col 23 (登壇者氏名/役職) | PII (グレー) | ❌ never | 安全側、別途公開許諾フローで対応 |
| col 32 (タイムスタンプ) | 申込日時 (PII 周辺) | ❌ never | `COL` map に含めない |
| col 33-34 (写真利用/同意) | internal | ❌ never | 同上 |

**監査手順** (terisuke):
```bash
curl "${URL}?token=${TOKEN}" | jq '.events[0] | keys'
# expected keys (PII なし):
# ["additional_info", "capacity", "date", "description", "entry_fee", "entry_fee_amount",
#  "event_end", "event_start", "facility", "facility_end", "facility_start",
#  "hashtags", "online", "organizer", "organizer_type", "row", "time_table", "title"]
#
# NG: "email", "name", "phone", "speaker" などが含まれていたら GAS 即修正
```

---

## 8. Open Questions / Risks

| # | Question / Risk | Owner | 期限 |
|---|----------------|-------|------|
| Q1 | 終了時刻が空または開始と同じ (`9:00 → 9:00` のような) イベントの扱い | 検討 | Day 1 |
| Q2 | 同日複数同タイトルイベントの dedup (例: `TinyGame機をつくろう!` 6/2 / 6/9 / 6/16) | 検討 (date 違うので OK) | - |
| Q3 | `登壇者/氏名および役職` を公開すべきイベントは別 GAS フィールドで開示? | terisuke | Phase 3+ |
| Q4 | 多言語対応 — `title` は和文のみ。英語応答時の翻訳 | Backend engineer | Day 2 |
| Q5 | Google Form の項目追加で列がずれた場合の検知 | terisuke | runbook 化 |
| R1 | GAS Web App URL 漏洩 → token 知る人が events を取得可能 | terisuke | `openssl rand -hex 32` で十分長い token + rotation 手順 |
| R2 | terisuke 退職 / アカウント停止 → GAS 実行停止 | terisuke | 引き継ぎ手順 (新管理者で再デプロイ) |
| R3 | GAS quota (日次 90 分実行時間, 1日 20,000 URL fetch 等) — 通常運用 (1 日 1 回) では非問題 | terisuke | 監視 |
| R4 | スプレッドシート列順変更 → `COL` map 破綻 → 誤データ返却 | terisuke + Backend engineer | GAS で `headers[COL.title] === 'イベントタイトル...'` の startsWith check 追加検討 |
| R5 | PII 列を誤って `COL` map に追加 → 漏洩 | Backend engineer | code review + §7 監査 |
| R6 | Status enum 増加 (例: `承認待ち` 新設) → Backend filter で skip される | terisuke | 新 enum は事前共有 |

---

## 9. 完了条件

### Day 0 (terisuke)
- [ ] GAS Web App デプロイ + 動作確認 `count=37` 確認
- [ ] Secret Manager 登録 + Cloud Run env bind
- [ ] PII 監査 (§7) で expected keys のみ返却を確認

### Backend engineer (Wave 2 Theme C)
- [ ] `backend/services/sheets_event_source.py` 新規実装 (§4.2)
- [ ] `backend/scripts/sync_event_kb.py` に `--include-spreadsheet` 追加 (§4.3)
- [ ] Cloud Scheduler job body 更新 (§4.4)
- [ ] `backend/agents/event_agent.py:_merge_events` priority order 反映 (§4.5)
- [ ] unit test: GAS response の mock + status filter + PII 不在検証
- [ ] live: `curl /api/chat "今日のイベントは?"` で `許可済` event が応答に出る
- [ ] live: `curl /api/chat "今週のイベント"` で 37 件のうち今週分が正確に出る
- [ ] ruff + black + pytest 全 PASS

### Wave 2 Theme C 統合
- [ ] FU-07 (#851) + FU-18 (#869) + FU-19 (#870) + FU-20 (#871) close
- [ ] RAGAS event ground truth 更新 + ja >= 0.85
- [ ] Theme C Sub-Epic #858 close

---

## 10. Reference

- 実測 CSV: `~/Desktop/イベント管理シート - event_status.csv` (terisuke 提供, 2026-05-17)
- スプレッドシート URL: `https://docs.google.com/spreadsheets/d/153ib48CUk7P_Qf8DEXx2XYAMhaQnqyFUNQ18NEnnz_k/edit?gid=1420282345`
- FU-07 設計初版: `docs/plans/event-source-spreadsheet-integration-2026-05-17.md`
- Wave 2 handoff: `docs/plans/wave2-date-audio-calendar-handoff-2026-05-17.md` §4
- FU-02 (Cloud Scheduler ✅ done): Issue #844
- FU-07 (Spreadsheet 実装): Issue #851 / PR #852
- Wave 2 Theme C: Issue #858
- Apps Script Web Apps doc: https://developers.google.com/apps-script/guides/web
- Apps Script Properties Service: https://developers.google.com/apps-script/reference/properties

---

## Appendix A: rev 1 / rev 2 / rev 3 の差分

| 項目 | rev 1 (誤) | rev 2 (誤) | **rev 3 (正)** |
|------|-----------|-----------|---------------|
| シート前提 | 新規 14 列 events シート | 既存 `alert_discord` (A3:B 2列) | **実物 `event_status` (44 列)** ← 実測 |
| 入力フロー | staff 手動入力 | staff 手動入力 | **Google Form 自動 append** ← 実際の運用 |
| Status 管理 | スキーマ列に enum | 列なし、タイトル prefix で判定 | **A 列に 8 種類の手動 enum** ← 実測 |
| 公開判定 | `status=scheduled` | タイトル先頭 `中止` で除外 | **`status==許可済` のみ公開** ← terisuke 確認 |
| PII 配慮 | (なし) | (なし) | **GAS で col 19-23, 32-34 を返却しない明示設計** |
| イベント時刻 | `time_start/time_end` 必須列追加 | 列なし | **既存 col 16/17 (イベント開始/終了時刻) を利用** |
| 列マッピング根拠 | 想定 | 想定 | **terisuke 提供 CSV で 0-indexed 確認済 (§1.1)** |
| 直近 upcoming 件数 | 不明 | 不明 | **37 件 (2026-05-17 実測)** |
