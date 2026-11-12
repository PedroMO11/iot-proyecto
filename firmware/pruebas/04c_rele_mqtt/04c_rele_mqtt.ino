// 04c_rele_mqtt.ino : enciende y apaga el foco por MQTT, sin sensores ni audio.
// Usa los mismos topics y comandos que nodo_asistivo (README.md, sección 4), así que todo lo que se
// pruebe aquí sigue funcionando con el firmware final.
//
// Topic asistivo/nodo1/cmd:
//   {"accion":"luz","estado":"on"}       enciende
//   {"accion":"luz","estado":"off"}      apaga
//   {"accion":"luz","estado":"toggle"}   conmuta (también si falta "estado")
// Publica el estado real en asistivo/nodo1/actuadores: {"luz":true} o {"luz":false}.
// Por el Monitor Serie (115200): 1 enciende · 0 apaga · l conmuta.

// ---- Configuración: WiFi, IP del broker y lógica del relé ----
// Copiar firmware/nodo_asistivo/config.example.h como config.h en esta carpeta y completarlo.
// config.h está en .gitignore: NUNCA subirlo (tiene la contraseña del WiFi).
// RELE_ENCENDIDO: LOW con D26 directo a IN; HIGH con el transistor 2N2222.
#if __has_include("config.h")
#include "config.h"
#else
#error "Falta config.h: copiar firmware/nodo_asistivo/config.example.h como config.h en esta carpeta"
#endif

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

const int PIN_RELE = 26;

const char* T_CMD = NODO "/cmd";
const char* T_ESTADO = NODO "/estado";
const char* T_ACTUADORES = NODO "/actuadores";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

bool luz = false;

void publicarActuadores() {
  if (mqtt.connected()) mqtt.publish(T_ACTUADORES, luz ? "{\"luz\":true}" : "{\"luz\":false}", true);
}

void ponerLuz(bool encendida) {
  luz = encendida;
  digitalWrite(PIN_RELE, luz ? RELE_ENCENDIDO : !RELE_ENCENDIDO);
  Serial.printf("[relé] luz %s\n", luz ? "ENCENDIDA" : "apagada");
  publicarActuadores();
}

void alRecibir(char* topic, byte* payload, unsigned int len) {
  char msg[128];                        // copiar: el buffer de PubSubClient se reutiliza
  len = min(len, (unsigned int)sizeof(msg) - 1);
  memcpy(msg, payload, len);
  msg[len] = '\0';
  Serial.printf("[mqtt] %s\n", msg);

  JsonDocument doc;
  if (deserializeJson(doc, msg)) { Serial.println("[mqtt] JSON inválido"); return; }
  if (strcmp(doc["accion"] | "", "luz") != 0) return;

  const char* estado = doc["estado"] | "toggle";
  if (!strcmp(estado, "on")) ponerLuz(true);
  else if (!strcmp(estado, "off")) ponerLuz(false);
  else if (!strcmp(estado, "toggle")) ponerLuz(!luz);
  else Serial.printf("[mqtt] estado desconocido: %s\n", estado);   // no mover el relé si no se entiende
}

void conectarMqtt() {
  static uint32_t ultimoIntento = 0;
  if (WiFi.status() != WL_CONNECTED || mqtt.connected() || millis() - ultimoIntento < 2000) return;
  ultimoIntento = millis();
  // LWT: si el ESP32 se cae, el broker publica "offline"
  if (mqtt.connect("esp32-nodo1", T_ESTADO, 1, true, "offline")) {
    Serial.println("[mqtt] conectado");
    mqtt.publish(T_ESTADO, "online", true);
    mqtt.subscribe(T_CMD, 1);
    publicarActuadores();
  } else {
    Serial.printf("[mqtt] falló (rc=%d)\n", mqtt.state());
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
  digitalWrite(PIN_RELE, !RELE_ENCENDIDO);   // relé apagado al arrancar
  Serial.println("\n[nodo] arrancando");

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);          // no se espera: el Monitor Serie sigue atendiendo
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alRecibir);
  mqtt.setKeepAlive(5);                      // el LWT llega en ~7,5 s
}

void loop() {
  static bool wifiAntes = false;
  bool wifiOk = WiFi.status() == WL_CONNECTED;
  if (wifiOk != wifiAntes) {
    wifiAntes = wifiOk;
    if (wifiOk) Serial.printf("[wifi] conectado, IP %s\n", WiFi.localIP().toString().c_str());
    else Serial.println("[wifi] sin conexión, reintentando");
  }
  conectarMqtt();
  mqtt.loop();

  if (Serial.available()) {                  // pruebas sin MQTT
    char c = Serial.read();
    if (c == '1') ponerLuz(true);
    else if (c == '0') ponerLuz(false);
    else if (c == 'l') ponerLuz(!luz);
  }
  delay(5);
}
