// 02b_coexistencia.ino : WiFi + MQTT + Bluetooth A2DP al mismo tiempo
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include "BluetoothA2DPSource.h"
#include "frases.h"

// ---- Configuración (NO subir contraseñas reales al repositorio) ----
const char* WIFI_SSID = "TU_RED";
const char* WIFI_PASS = "TU_CLAVE";
const char* MQTT_HOST = "192.168.1.100";               // IP de la laptop
const char* PARLANTE  = "ULT WEAR";                    // audífonos Sony ULT WEAR

const char* T_CMD    = "asistivo/nodo1/cmd";
const char* T_PING   = "asistivo/nodo1/ping";
const char* T_PONG   = "asistivo/nodo1/pong";
const char* T_ESTADO = "asistivo/nodo1/estado";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
BluetoothA2DPSource a2dp;

// ---- Audio (igual que en la prueba A) ----
volatile int fraseActual = -1;
volatile float posicion = 0;
const float PASO = 16000.0f / 44100.0f;

int32_t get_data_frames(Frame* frame, int32_t frame_count) {
  for (int i = 0; i < frame_count; i++) {
    int16_t muestra = 0;
    int f = fraseActual;
    if (f >= 0) {
      uint32_t idx = (uint32_t)posicion;
      if (idx < FRASES_LEN[f]) { muestra = FRASES[f][idx]; posicion += PASO; }
      else fraseActual = -1;
    }
    frame[i].channel1 = muestra;
    frame[i].channel2 = muestra;
  }
  delay(1);
  return frame_count;
}

void reproducir(int id) {
  if (id < 1 || id > NUM_FRASES) return;
  posicion = 0;
  fraseActual = id - 1;
  Serial.printf("Frase %d\n", id);
}

// ---- MQTT ----
void alRecibir(char* topic, byte* payload, unsigned int len) {
  char msg[128];                                       // copiar: el buffer de PubSubClient se reutiliza
  len = min(len, (unsigned int)sizeof(msg) - 1);
  memcpy(msg, payload, len);
  msg[len] = '\0';

  if (strcmp(topic, T_PING) == 0) {                    // eco para medir latencia
    mqtt.publish(T_PONG, msg);
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, msg)) { Serial.println("JSON inválido"); return; }
  if (doc["accion"] == "frase") reproducir(doc["id"] | 0);
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
    mqtt.subscribe(T_PING, 1);
  } else {
    Serial.printf("falló (rc=%d)\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.printf("\nWiFi OK, IP: %s\n", WiFi.localIP().toString().c_str());
  // IMPORTANTE: no usar WiFi.setSleep(false). Con Bluetooth activo, el WiFi
  // necesita su modo de ahorro para compartir la radio.

  mqtt.setServer(MQTT_HOST, 1883);
  mqtt.setCallback(alRecibir);

  a2dp.set_data_callback_in_frames(get_data_frames);
  a2dp.set_volume(80);
  a2dp.start(PARLANTE);
}

void loop() {
  conectarMqtt();
  mqtt.loop();

  static bool btAntes = false;
  if (a2dp.is_connected() != btAntes) {
    btAntes = a2dp.is_connected();
    Serial.println(btAntes ? "Parlante CONECTADO" : "Parlante desconectado");
  }
  if (Serial.available()) {
    char c = Serial.read();
    if (c >= '1' && c <= '9') reproducir(c - '0');
  }
  delay(5);
}
