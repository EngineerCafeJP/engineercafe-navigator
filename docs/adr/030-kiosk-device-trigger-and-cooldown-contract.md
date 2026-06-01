# ADR-030: Kiosk Device Trigger and Cooldown Contract

## Status

Proposed (2026-05-24) — Issue #913 の kiosk device trigger / cooldown 契約を明文化する。

> **2026-06-01 追記 (VNav)**: 本契約は `sensor_triggered` / `button_pressed` の 2 種のみを定義する。NFC 発火（`nfc` event 種別）は [ADR-031 (VNav Phase 2)](./031-vnav-phase2-program-and-scope.md) スコープ④で本契約を拡張して追加する。

## Context

Kiosk 端末では、人感センサーによる自動 Welcome と、物理ボタンによる OCR 起動が同じ frontend event 経路に流れる。両者の意味が曖昧なままだと、cooldown 中のイベントを後から実行する、OCR ボタンで Welcome が始まる、または自動録音が意図せず OCR 側で動くといった UX 事故が起きる。

本 ADR は Issue #913 の設計決定として、frontend event 契約と cooldown 境界を固定する。backend `/api/reception/*` の wire shape は変更しない。

## Decision

### D1: Frontend event contract を固定する

Kiosk device event は frontend 内で以下の意味に正規化する。

- `sensor_triggered` は Welcome 専用 event とする。
- `button_pressed` は OCR 専用 event とし、`data.mode` で OCR mode を明示する。
- `sensor_triggered` を OCR 起動に使わない。
- `button_pressed` を Welcome 起動に使わない。

### D2: Sensor cooldown / TTL / lookback / idle は 60 秒に統一する

人感センサー系の cooldown、event TTL、lookback window、idle 判定はすべて 60 秒を基準にする。これにより、端末側と UI 側の「直近検知」の解釈を揃える。

### D3: Cooldown 中の sensor event は予約しない

Cooldown 中に届いた `sensor_triggered` は、必要なら UI 上に「検知したが cooldown 中」の状態を表示し、その場で破棄する。Cooldown 終了後に遅延実行する予約 event として保持しない。

### D4: 自動録音は自動検知 Welcome のみに限定する

自動録音は `sensor_triggered` から始まる自動検知 Welcome flow のみに許可する。`button_pressed` + `data.mode` の OCR flow では自動録音を開始しない。

### D5: Backend reception API の wire shape は変更しない

`/api/reception/*` の request / response shape は維持する。今回の契約は frontend event の解釈と device UX の境界であり、backend API 互換性を壊さない。

## Consequences

### Positive

- Welcome と OCR の起動条件が event 名で分離され、誤起動を防ぎやすい。
- Cooldown 中 event を予約しないため、利用者が離れた後に Welcome が遅延発火しない。
- 60 秒基準に統一することで、sensor TTL / lookback / idle のズレを減らせる。
- Backend reception API の互換性を維持できる。

### Negative

- Cooldown 中の検知は後続処理に残らないため、検知回数の分析が必要な場合は別途 telemetry で見る必要がある。
- OCR flow で録音が必要になった場合は、`button_pressed` contract とは別に明示的な user action を設計する必要がある。

## Testing

- `sensor_triggered` が Welcome flow のみを起動し、OCR flow を起動しないこと。
- `button_pressed` + `data.mode` が OCR flow のみを起動し、Welcome flow を起動しないこと。
- 60 秒 cooldown 中の `sensor_triggered` が遅延予約されず、cooldown 終了後に再発火しないこと。
- 自動録音が `sensor_triggered` の自動検知 Welcome でのみ開始されること。
- `/api/reception/*` の既存 contract test / smoke が request / response shape 変更なしで通ること。

## Rollback

Frontend の event mapping と 60 秒 cooldown 設定を ADR-030 導入前の挙動へ戻す。Backend `/api/reception/*` wire shape は変更しないため、rollback は frontend/device contract の差し戻しに限定される。

## References

- [Issue #913](https://github.com/EngineerCafeJP/engineercafe-navigator/issues/913)
- [ADR-026 Wave 2 Kiosk UX Reliability Baseline](./026-wave2-kiosk-ux-reliability-baseline.md)
