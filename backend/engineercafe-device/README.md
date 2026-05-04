# Engineer Cafe — M5Stack Core2 センサーデバイス

PIR と VL53L0X（ToF）で来訪を検知し、バックエンドの reception Webhook に POST する Arduino スケッチです。

## ハードウェア

| 要素 | 接続・備考 |
|------|------------|
| M5Stack Core2 | 本体 |
| VL53L0X | Core2 PORT-A（I2C **SDA 32 / SCL 33**、`Wire.begin(32, 33)`） |
| PIR（例: HC-SR501） | **GPIO 35**（`INPUT`） |

## Arduino IDE での準備

1. ボードマネージャで **ESP32** 系パッケージをインストールし、ボードに **M5Stack-Core2**（または同等）を選択する。
2. ライブラリマネージャから以下をインストールする。
   - **M5Core2**
   - **Adafruit VL53L0X**

本リポジトリではスケッチを [`engineercafe-device.ino`](engineercafe-device.ino) と同じフォルダで開いてビルドする。

## シークレット（必須）

1. このディレクトリでテンプレをコピーする。

   ```bash
   cp secrets.example.h secrets.h
   ```

2. `secrets.h` を編集し、`SSID` / `PASSWORD` / `WEBHOOK_URL_BACKEND` / `API_SECRET_KEY` / `DEVICE_ID` を実環境の値に置き換える。
3. **`secrets.h` はコミットしない。** `.gitignore` で無視されていることを確認する。

   ```bash
   git check-ignore -v backend/engineercafe-device/secrets.h
   ```

4. `git ls-files backend/engineercafe-device | rg secrets` で **`secrets.h` が一覧に含まれない**ことをマージ前に確認する。

## API（バックエンド契約）

- **エンドポイント:** `POST {BASE_URL}/api/reception/sensor-trigger`
  - `BASE_URL` はデプロイ先（例: Cloud Run の HTTPS オリジン）。パスは **`sensor-trigger`**（`/api/reception/sensor` ではない）。
- **ヘッダ**
  - `Content-Type: application/json`
  - `Authorization: Bearer <API_SECRET_KEY>`（バックエンドの API キーと一致させる）
- **JSON ボディ**（[`SensorTriggerRequest`](../api/reception.py) と一致）

  | フィールド | 型・制約 |
  |-----------|-----------|
  | `sensor_type` | 文字列（最大 50）。スケッチでは `pir_tof` |
  | `distance_mm` | 整数 ≥ 0（ToF の mm） |
  | `device_id` | 文字列（最大 100） |

成功時は HTTP 200 と `success: true` / `action: trigger_received` が返る。

### レートリミットとデバイス側の扱い

サーバ側では **デバイス ID ごとに 5 秒間のクールダウン**があり、短時間に続けて送ると HTTP 200 で `success: false` / `action: rate_limited` が返ることがあります。

ファームウェアでは **`rate_limited` を成功扱い**にしています。理由は次のとおりです。

- 直前の POST がサーバで受理済みなのに、クライアント側だけタイムアウトや切断で失敗と判定した場合などにリトライすると、`rate_limited` が返りやすい。
- キオスク用途では「サーバが既にイベントを抑えている」状態とみなし、画面を歓迎状態へ進めてよいと判断できる。

ネットワークエラーや非 200 で **`rate_limited` でも `trigger_received` でもない**応答のときは Webhook 失敗とし、歓迎画面には進みません。

## フラッシュ・シリアル

- USB 経由で書き込み、シリアルモニタは **115200 baud**。
- 初回起動後、PIR の安定のため約 **30 秒**のウォームアップカウントダウンがある。

## セキュリティ（TLS）

現状スケッチでは **`WiFiClientSecure::setInsecure()`** を使用しており、サーバ証明書の検証を行っていません。半公開 Wi-Fi 環境では MITM のリスクがあります。**ルート CA をバンドルして `setCACert()` に渡す**対応は別 Issue / PR（HIGH-2 follow-up）として扱う想定です。

## トラブルシュート

| 現象 | 確認 |
|------|------|
| WiFi に繋がらない | `secrets.h` の SSID/パスワード、タイムアウト後は自動再起動 |
| ToF 初期化失敗 | 配線・PORT-A、再起動ループまたはメッセージ後に再起動 |
| Webhook NG と表示 | URL・Bearer・ネットワーク、バックエンドログ |
