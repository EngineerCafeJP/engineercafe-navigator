# ADR 012: LTM Store connection pool migration

## ステータス

採用

## 日付

2026-04-23

## 背景

ADR 011 と PR #519 で LTM の cross-session recall 経路は修正したが、Cloud Run
deploy 後の smoke で、時間経過後に全 LTM load/store が `connection is closed` で
失敗する回帰が確認された。

本番設定では `SUPABASE_DB_URI` が Supabase の direct PostgreSQL endpoint
`db.smdmvpnsfmdspzzaisia.supabase.co:5432` を指しており、pooler endpoint ではない。
Cloud Run は `minScale=1` のためインスタンスが長時間残り、プロセス内に保持した DB
connection はリクエスト間 idle 状態になり得る。

## 問題

旧実装は `AsyncPostgresStore.from_conn_string()` を async context manager として
1 回だけ enter し、その single connection を singleton として保持していた。

この設計では以下が同時に起きる。

1. Supabase direct port 5432 側で idle connection が切断される。
2. TCP keepalive パラメータがないため、アプリ側は死活を早期検知しづらい。
3. `runtime.store` に注入された Store が dead connection を保持し続ける。
4. `close_store()` + `get_store()` retry は singleton 経路には効いても、注入済み
   `runtime.store` には効かない。

## 決定

LTM Store は single connection singleton ではなく、`psycopg_pool.AsyncConnectionPool`
を持つ `AsyncPostgresStore` として初期化する。

採用する pool 設定:

- `min_size=1`
- `max_size=5`
- `max_idle=120`
- `timeout=30`
- `check=AsyncConnectionPool.check_connection`
- `open=False` で作成し、`await pool.open()` で明示的に起動する。

接続文字列には以下の TCP keepalive query parameter を接続時に merge する。

- `keepalives=1`
- `keepalives_idle=30`
- `keepalives_interval=10`
- `keepalives_count=3`

`store_with_retry` は connection error を検知したら Store を作り直すことを第一選択にせず、
pool に health check を実行させる。`AsyncPostgresStore` は pool から connection を
checkout して操作するため、壊れた connection は pool の connection context と
`pool.check()` によって破棄され、retry は別 connection を取得できる。

## 採用理由

Cloud Run Fluid Compute / Cloud Run instance は request lifetime より長く残るため、
プロセス内 singleton に direct DB connection を保持すると、DB 側 idle timeout と
instance lifetime の差分がそのまま障害になる。

Pool 化すると request ごとの Store 操作が pool checkout/release の単位になり、dead
connection が全リクエストに波及しにくい。`max_idle=120` は Supabase 側の長い idle
kill を待たずにアプリ側で idle connection を短く循環させるための設定である。

TCP keepalive は idle 中の socket 状態検知を補助する。これだけでは retry 設計の代替には
ならないが、dead socket を長時間保持する確率を下げる。

## 互換性

- LangGraph の `runtime.store` 注入経路は維持する。
- LTM の namespace、record shape、ADR 011 の fast-path 書き込み設計は変更しない。
- `store_with_retry(store=None)` は引き続き process singleton Store を使うが、その中身は
  single connection ではなく pool である。

## ロールバック

問題が出た場合はこの ADR の実装 commit を revert する。ただし旧 single connection 実装へ
戻すと、Supabase direct connection idle kill 後に LTM が再び全滅するリスクが高い。
緊急時は `ENABLE_MEMORY_CANDIDATES=false` や `ENABLE_MEMORY_PROMOTION=false` ではなく、
LTM Store 初期化そのものを無効化して degraded mode にする。

## 検証方針

- Unit: keepalive parameter merge と pool 初期化設定。
- Unit: connection error 後に pool check を実行して retry が成功すること。
- Unit: pool size 上限で concurrent operation が block/release されること。
- Unit: 10 parallel store operations が全成功すること。
- Local: `ruff`, `black`, `pytest -m "not ragas and not slow"`。
- Live: Cloud Run deploy 後、Claude が 5 分 idle 後の cross-session recall と 30 秒間隔の
  連続 10 request を検証する。Codex は live verify を行わない。
