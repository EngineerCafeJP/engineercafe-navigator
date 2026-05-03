#include <M5Core2.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_VL53L0X.h>

// ─── WiFi / API設定 ─────────────────────────────────────────
const char* SSID        = "";
const char* PASSWORD    = "";

// ─── Webhook URL設定 ────────────────────────────────────────
const char* WEBHOOK_URL_BACKEND   = "";

const char* API_SECRET_KEY = "";
const char* DEVICE_ID      = "";
const char* SENSOR_TYPE    = "pir_tof";  // ← 変更

// ─── ピン設定 ───────────────────────────────────────────────
#define PIR_PIN   35

// ─── ToF設定 ────────────────────────────────────────────────
#define TOF_TRIGGER_MM       300   // 確定閾値: 30cm
#define CONFIRM_COUNT          3   // 連続N回でWebhook発火
#define LEAVE_THRESHOLD_MM   400   // 離脱判定: 40cm以上
#define LEAVE_CONFIRM_COUNT    3   // 離脱連続N回で確定

// ─── PIR保持設定 ────────────────────────────────────────────
#define PIR_HOLD_MS          10000

// ─── 画面更新間隔 ────────────────────────────────────────────
#define DISPLAY_INTERVAL_MS   1000

// ─── ToFインスタンス ────────────────────────────────────────
Adafruit_VL53L0X tof;

// ─── 状態管理 ───────────────────────────────────────────────
enum State { WAITING, GREETING };
State currentState = WAITING;

int           confirmCount      = 0;
int           leaveCount        = 0;
unsigned long lastPirOnTime     = 0;
unsigned long lastDisplayUpdate = 0;

// ─── ToF距離測定 ─────────────────────────────────────────────
int measureToF_MM() {
  VL53L0X_RangingMeasurementData_t measure;
  tof.rangingTest(&measure, false);
  if (measure.RangeStatus == 4) return 9999;
  return measure.RangeMilliMeter;
}

// ─── バックエンドへ送信 ──────────────────────────────────────
void sendToBackend(int tofMM) {
  char payload[256];
  snprintf(
    payload, sizeof(payload),
    "{\"sensor_type\":\"%s\",\"distance_mm\":%d,\"device_id\":\"%s\"}",
    SENSOR_TYPE, tofMM, DEVICE_ID
  );

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.begin(client, WEBHOOK_URL_BACKEND);
  http.setTimeout(10000);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + API_SECRET_KEY);
  int code = http.POST((uint8_t*)payload, strlen(payload));
  String responseBody = http.getString();

  Serial.printf("[Backend] HTTP %d payload=%s\n", code, payload);
  if (responseBody.length() > 0) {
    Serial.printf("[Backend] response=%s\n", responseBody.c_str());
  }
  http.end();
}

// ─── 両方へ送信 ──────────────────────────────────────────────
void sendSensorTrigger(int tofMM) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[Webhook] WiFi未接続のためスキップ");
    return;
  }

  sendToBackend(tofMM);
}

// ─── 画面表示 ────────────────────────────────────────────────
void showWelcome() {
  M5.Lcd.fillScreen(TFT_YELLOW);
  M5.Lcd.setTextColor(TFT_BLACK);
  M5.Lcd.setTextSize(4);
  M5.Lcd.setCursor(60, 100);
  M5.Lcd.println("WELCOME!!");
}

void showStandby() {
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextColor(TFT_DARKGREY);
  M5.Lcd.setTextSize(3);
  M5.Lcd.setCursor(60, 80);
  M5.Lcd.println("Waiting...");
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(75, 135);
  M5.Lcd.println("Engineer Cafe");
}

void showDebug(bool pirOn, int tofMM, bool measuring) {
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextSize(2);

  // PIR
  M5.Lcd.setCursor(10, 10);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.print("PIR:    ");
  M5.Lcd.setTextColor(pirOn ? TFT_GREEN : TFT_RED);
  M5.Lcd.println(pirOn ? "ON " : "OFF");

  // ToF
  M5.Lcd.setCursor(10, 55);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.print("ToF:  ");
  if (measuring) {
    bool near = (tofMM != 9999 && tofMM < TOF_TRIGGER_MM);
    M5.Lcd.setTextColor(near ? TFT_YELLOW : TFT_WHITE);
    if (tofMM == 9999) {
      M5.Lcd.println("--- mm");
    } else {
      M5.Lcd.print(tofMM);
      M5.Lcd.println(" mm");
    }
  } else {
    M5.Lcd.setTextColor(TFT_DARKGREY);
    M5.Lcd.println("--- mm");
  }

  // 状態
  M5.Lcd.setCursor(10, 100);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.print("State: ");
  M5.Lcd.setTextColor(currentState == GREETING ? TFT_YELLOW : TFT_GREEN);
  M5.Lcd.println(currentState == GREETING ? "GREETING" : "WAITING ");

  // 確定カウント
  M5.Lcd.setCursor(10, 145);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.print("Count: ");
  M5.Lcd.print(currentState == WAITING ? confirmCount : leaveCount);
  M5.Lcd.print(" / ");
  M5.Lcd.println(currentState == WAITING ? CONFIRM_COUNT : LEAVE_CONFIRM_COUNT);

  // プログレスバー
  int total    = (currentState == WAITING) ? CONFIRM_COUNT     : LEAVE_CONFIRM_COUNT;
  int count    = (currentState == WAITING) ? confirmCount      : leaveCount;
  int barWidth = map(count, 0, total, 0, 300);
  M5.Lcd.fillRect(10, 178, barWidth, 14,
    currentState == WAITING ? TFT_GREEN : TFT_CYAN);
  M5.Lcd.drawRect(10, 178, 300, 14, TFT_DARKGREY);

  // WiFi状態
  M5.Lcd.setTextSize(1);
  M5.Lcd.setCursor(230, 225);
  M5.Lcd.setTextColor(WiFi.status() == WL_CONNECTED ? TFT_GREEN : TFT_RED);
  M5.Lcd.println(WiFi.status() == WL_CONNECTED ? "WiFi:OK" : "WiFi:NG");
}

// ─── 初期化 ─────────────────────────────────────────────────
void setup() {
  M5.begin(true, true, true, false);
  M5.Lcd.setRotation(1);
  Serial.begin(115200);

  pinMode(PIR_PIN, INPUT);

  // I2C + ToF初期化
  // 変更後（Core2: PORT-A）
  Wire.begin(32, 33);
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 80);
  M5.Lcd.println("Init ToF...");

  if (!tof.begin(0x29, false, &Wire)) {
    Serial.println("[ToF] 初期化失敗！");
    M5.Lcd.setTextColor(TFT_RED);
    M5.Lcd.setCursor(10, 110);
    M5.Lcd.println("ToF INIT FAILED");
    while (1) delay(100);
  }
  Serial.println("[ToF] 初期化完了");

  // WiFi接続
  M5.Lcd.setCursor(10, 110);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.println("WiFi connecting...");
  WiFi.begin(SSID, PASSWORD);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] 接続完了: %s\n", WiFi.localIP().toString().c_str());

  // PIR安定待ち
  Serial.println("[PIR] 安定待ち中... 30秒");
  M5.Lcd.fillScreen(TFT_BLACK);
  M5.Lcd.setTextColor(TFT_WHITE);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(10, 80);
  M5.Lcd.println("PIR Warming up...");
  for (int i = 30; i > 0; i--) {
    M5.Lcd.fillRect(10, 110, 300, 30, TFT_BLACK);
    M5.Lcd.setCursor(10, 110);
    M5.Lcd.printf("Wait: %d sec", i);
    delay(1000);
  }

  lastPirOnTime = 0;
  showStandby();
  Serial.println("[PIR] 安定完了。検知開始。");
}

// ─── メインループ ────────────────────────────────────────────
void loop() {
  M5.update();
  unsigned long now = millis();

  bool pirRaw = digitalRead(PIR_PIN) == HIGH;
  if (pirRaw) lastPirOnTime = now;

  if (currentState == WAITING) {
    bool pirDetected = (lastPirOnTime > 0) &&
                       ((now - lastPirOnTime) < PIR_HOLD_MS);

    if (pirDetected) {
      int tofMM = measureToF_MM();
      Serial.printf("[Sensor] PIR=ON ToF=%dmm count=%d\n", tofMM, confirmCount);

      if (now - lastDisplayUpdate >= DISPLAY_INTERVAL_MS) {
        showDebug(true, tofMM, true);
        lastDisplayUpdate = now;
      }

      if (tofMM != 9999 && tofMM < TOF_TRIGGER_MM) {
        confirmCount++;
        if (confirmCount >= CONFIRM_COUNT) {
          Serial.println("[System] >>> 来訪者検知！Webhook送信 <<<");
          showWelcome();
          sendSensorTrigger(tofMM);
          currentState = GREETING;
          confirmCount = 0;
          leaveCount   = 0;
          Serial.println("[System] GREETING状態へ。人が離れるまでPIR無効。");
        }
      } else {
        confirmCount = 0;
      }
    } else {
      confirmCount = 0;
      if (now - lastDisplayUpdate >= DISPLAY_INTERVAL_MS) {
        showDebug(false, 0, false);
        lastDisplayUpdate = now;
      }
    }

  } else if (currentState == GREETING) {
    int  tofMM     = measureToF_MM();
    bool personGone = (tofMM != 9999 && tofMM > LEAVE_THRESHOLD_MM);

    if (personGone) {
      leaveCount++;
      Serial.printf("[System] 離脱確認中... %d / %d (ToF=%dmm)\n",
        leaveCount, LEAVE_CONFIRM_COUNT, tofMM);
    } else {
      leaveCount = 0;
    }

    if (leaveCount >= LEAVE_CONFIRM_COUNT) {
      currentState  = WAITING;
      leaveCount    = 0;
      lastPirOnTime = 0;
      showStandby();
      Serial.println("[System] 人が離れた。WAITING状態へ戻る。");
    }

    if (now - lastDisplayUpdate >= DISPLAY_INTERVAL_MS) {
      showDebug(false, tofMM, true);
      lastDisplayUpdate = now;
    }
  }

  delay(300);
}