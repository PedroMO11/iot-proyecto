// 01_mqtt_basico.ino : WiFi + MQTT con LWT, publicación de prueba y reconexión
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// ---- Configuración: WiFi, IP del broker y parlante ----
// Copiar firmware/nodo_asistivo/config.example.h como config.h en esta carpeta y completarlo.
// config.h está en .gitignore: NUNCA subirlo (tiene la contraseña del WiFi).
#if __has_include("config.h")
#include "config.h"
#else
#error "Falta config.h: copiar firmware/nodo_asistivo/config.example.h como config.h en esta carpeta"
#endif

const char* T_CMD     = "asistivo/nodo1/cmd";
const char* T_ESTADO  = "asistivo/nodo1/estado";
const char* T_VITALES = "asistivo/nodo1/vitales";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

void alRecibir(char* topic, byte* payload, unsigned int len) {
  char msg[128];                                       // copiar: el buffer de PubSubClient se reutiliza
  len = min(len, (unsigned int)sizeof(msg) - 1);
  memcpy(msg, payload, len);
  msg[len] = '\0';
  Serial.printf("[%s] %s\n", topic, msg);
}

void conectarMqtt() {
  static uint32_t ultimoIntento = 0;
  if (mqtt.connected() || millis() - ultimoIntento < 2000) return;
  ultimoIntento = millis();
  Serial.print("Conectando a MQTT... ");
  // LWT: si el ESP32 se cae, el broker publica "offline"
  if (mqtt.connect("esp32-nodo1", T_ESTADO, 1, true, "offline")) {
    Serial.println("OK");
    mqtt.publish(T_ESTADO, "online", true);
    mqtt.subscribe(T_CMD, 1);
  } else {
    Serial.printf("falló (rc=%d)\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);                         // el ESP32 reintenta solo si se cae el WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.printf("\nWiFi OK, IP: %s\n", WiFi.localIP().toString().c_str());

  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(alRecibir);
}

void loop() {
  static bool wifiAntes = true;
  bool wifiOk = WiFi.status() == WL_CONNECTED;
  if (wifiOk != wifiAntes) {
    wifiAntes = wifiOk;
    Serial.println(wifiOk ? "WiFi reconectado" : "WiFi perdido, reintentando...");
  }
  if (!wifiOk) { delay(100); return; }

  conectarMqtt();
  mqtt.loop();

  // JSON de prueba cada 1 s (valores fijos; los reales vienen del MAX30102)
  static uint32_t ultimo = 0;
  if (mqtt.connected() && millis() - ultimo >= 1000) {
    ultimo = millis();
    JsonDocument doc;
    doc["bpm"] = 72;
    doc["spo2"] = 98;
    doc["ts"] = millis();
    char buf[96];
    serializeJson(doc, buf);
    mqtt.publish(T_VITALES, buf);
  }
  delay(5);
}
