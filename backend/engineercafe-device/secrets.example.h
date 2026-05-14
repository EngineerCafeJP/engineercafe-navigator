#pragma once

#define SSID "YOUR_WIFI_SSID"
#define PASSWORD "YOUR_WIFI_PASSWORD"
#define WEBHOOK_URL_BACKEND "https://YOUR_SERVICE.run.app/api/reception/sensor-trigger"
#define API_SECRET_KEY "YOUR_API_SECRET_KEY"
#define DEVICE_ID "m5stack-001"

// Replace this with the PEM-encoded root CA that signs WEBHOOK_URL_BACKEND's
// server certificate chain. Keep the BEGIN/END lines and trailing newlines.
#define BACKEND_ROOT_CA \
"-----BEGIN CERTIFICATE-----\n" \
"REPLACE_WITH_ROOT_CA_PEM_BODY\n" \
"-----END CERTIFICATE-----\n"
