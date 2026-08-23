#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <DHT.h>
#include <Adafruit_BMP280.h>
#include <ArduinoJson.h>

// --- Wi-Fi Credentials (Use any Wi-Fi or Mobile Hotspot) ---
const char* WIFI_SSID = "BHUIYANH";
const char* WIFI_PASS = "217092004";

// --- Live Render Cloud Endpoint ---
const char* SERVER_URL = "https://iot-weather-api.onrender.com/api/readings/";

#define DHTPIN 4
#define DHTTYPE DHT22

#define I2C_SDA 21
#define I2C_SCL 22

DHT dht(DHTPIN, DHTTYPE);
Adafruit_BMP280 bmp;

unsigned long lastSampleTime = 0;
const unsigned long sampleInterval = 10000; // Sample every 10 seconds

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("[WiFi] Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connected!");
    Serial.print("[WiFi] ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Connection timed out. Will retry on next cycle.");
  }
}

void sendSensorData(float temperature, float humidity, float pressure) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Cannot POST: Wi-Fi not connected.");
    return;
  }

  WiFiClientSecure client;
  client.setInsecure(); // Allows secure HTTPS connection to cloud without loading root CA certs

  HTTPClient http;
  if (!http.begin(client, SERVER_URL)) {
    Serial.println("[HTTP] Failed to initialize connection to cloud.");
    return;
  }

  http.addHeader("Content-Type", "application/json");

  JsonDocument doc;
  doc["temperature"] = serialized(String(temperature, 2));
  doc["humidity"]    = serialized(String(humidity, 2));
  doc["pressure"]    = serialized(String(pressure, 2));

  String requestBody;
  serializeJson(doc, requestBody);

  Serial.print("[HTTP] Sending to Cloud: ");
  Serial.println(requestBody);

  int httpResponseCode = http.POST(requestBody);

  if (httpResponseCode > 0) {
    Serial.printf("[HTTP] Success! Cloud Status Code: %d\n", httpResponseCode);
  } else {
    Serial.printf("[HTTP] Cloud Request failed. Error: %s\n", http.errorToString(httpResponseCode).c_str());
  }

  http.end();
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n=== Initializing ESP32 Environmental Station ===");

  Wire.begin(I2C_SDA, I2C_SCL);
  dht.begin();

  if (!bmp.begin(0x76) && !bmp.begin(0x77)) {
    Serial.println("[BMP280] Warning: Sensor not found at 0x76 or 0x77. Check wiring!");
  } else {
    Serial.println("[BMP280] Sensor initialized successfully.");
    bmp.setSampling(Adafruit_BMP280::MODE_NORMAL,
                    Adafruit_BMP280::SAMPLING_X2,
                    Adafruit_BMP280::SAMPLING_X16,
                    Adafruit_BMP280::FILTER_X16,
                    Adafruit_BMP280::STANDBY_MS_500);
  }

  connectWiFi();
}

void loop() {
  connectWiFi();

  unsigned long currentMillis = millis();
  if (currentMillis - lastSampleTime >= sampleInterval) {
    lastSampleTime = currentMillis;

    float humidity = dht.readHumidity();
    float dhtTemp = dht.readTemperature();
    float bmpTemp = bmp.readTemperature();
    float pressure = bmp.readPressure() / 100.0F;

    float temperature = !isnan(dhtTemp) ? dhtTemp : bmpTemp;

    if (isnan(temperature) || isnan(humidity) || isnan(pressure)) {
      Serial.println("[Sensors] Read error: One or more sensor values are NaN.");
      return;
    }

    Serial.printf("[Sensors] Temp: %.2f °C | Humidity: %.2f %% | Pressure: %.2f hPa\n",
                  temperature, humidity, pressure);

    sendSensorData(temperature, humidity, pressure);
  }
}