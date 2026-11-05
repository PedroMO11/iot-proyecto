// nodo_asistivo.ino : firmware final integrado (README.md, paso 5).
// Une lo aprobado en firmware/pruebas/: MQTT con LWT (01), audio Bluetooth (02a/02b), MPU6050 (03a),
// MAX30102 (03b), EMG con filtro de 60 Hz (03c), relé (04a) y buzzer (04b).
//
// Tareas (FreeRTOS, núcleo 1): EMG a 1 kHz (prioridad 5) y bus I2C a 100 Hz con MPU6050 + MAX30102
// (prioridad 4). loop() (prioridad 1) atiende WiFi, MQTT, actuadores y el parlante; los eventos de los
// sensores le llegan por una cola. WiFi y Bluetooth corren en el núcleo 0 (pila de Espressif).
//
// Módulos activables en config.h (USAR_AUDIO, USAR_EMG, USAR_IMU, USAR_PULSO) para probar por partes.
// Por el Monitor Serie (115200): 1–6 frase · l luz · b buzzer · e recalibrar EMG · i neutro de la cabeza.
#if __has_include("config.h")
#include "config.h"
#else
#error "Falta config.h: copiar config.example.h como config.h y completarlo"
#endif

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#if USAR_AUDIO
#include "audio.h"
#endif
#include "emg.h"
#include "imu.h"
#include "pulso.h"

// ---- Pines (README.md, sección 3.2) ----
const int PIN_SDA = 21, PIN_SCL = 22;   // MPU6050 (0x68) + MAX30102 (0x57)
const int PIN_RELE = 26, PIN_BUZZER = 27;

// ---- Contrato MQTT (README.md, sección 4) ----
const char* T_EMG = NODO "/emg/evento";
const char* T_IMU = NODO "/imu/evento";
const char* T_VITALES = NODO "/vitales";
const char* T_CMD = NODO "/cmd";
const char* T_ESTADO = NODO "/estado";
const char* T_PING = NODO "/ping";
const char* T_PONG = NODO "/pong";
const char* T_ACTUADORES = NODO "/actuadores";
const char* T_DIAG = NODO "/diag";

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);

// ---- eventos de los sensores → loop() ----
struct Evento { char origen; char valor[12]; };     // origen: 'E' (EMG) o 'I' (IMU)
QueueHandle_t cola;

void encolar(char origen, const char* valor) {
  Evento e{origen, {0}};
  strncpy(e.valor, valor, sizeof(e.valor) - 1);
  xQueueSend(cola, &e, 0);
}
void eventoEMG(const char* tipo) { encolar('E', tipo); }
void eventoIMU(const char* dir) { encolar('I', dir); }

// ---- actuadores ----
bool luz = false;
uint32_t alertaHasta = 0;

void publicarActuadores() {
  if (mqtt.connected()) mqtt.publish(T_ACTUADORES, luz ? "{\"luz\":true}" : "{\"luz\":false}", true);
}

void ponerLuz(bool encendida) {
  luz = encendida;
  digitalWrite(PIN_RELE, luz ? RELE_ENCENDIDO : !RELE_ENCENDIDO);
  Serial.printf("[relé] luz %s\n", luz ? "ENCENDIDA" : "apagada");
  publicarActuadores();
}

void alerta() {                         // buzzer 2 s (5 pitidos), sin bloquear
  alertaHasta = millis() + 2000;
  Serial.println("[buzzer] alerta");
}

void atenderBuzzer() {
  bool sonar = millis() < alertaHasta && (alertaHasta - millis()) % 400 >= 200;
  digitalWrite(PIN_BUZZER, sonar ? BUZZER_ENCENDIDO : !BUZZER_ENCENDIDO);
}

void frase(int id) {
#if USAR_AUDIO
  audio::reproducir(id);
#endif
  Serial.printf("[audio] frase %d%s\n", id, USAR_AUDIO ? "" : " (audio desactivado)");
  if (id == 4) ponerLuz(!luz);          // «Enciende la luz»
  if (id == 5) alerta();                // «Llamar al cuidador»
}

// ---- MQTT ----
void alRecibir(char* topic, byte* payload, unsigned int len) {
  char msg[160];                        // copiar: el buffer de PubSubClient se reutiliza
  len = min(len, (unsigned int)sizeof(msg) - 1);
  memcpy(msg, payload, len);
  msg[len] = '\0';
  if (strcmp(topic, T_PING) == 0) { mqtt.publish(T_PONG, msg); return; }   // latencia (dashboard)

  JsonDocument doc;
  if (deserializeJson(doc, msg)) { Serial.println("[mqtt] JSON inválido"); return; }
  const char* accion = doc["accion"] | "";
  if (!strcmp(accion, "frase")) frase(doc["id"] | 0);
  else if (!strcmp(accion, "luz")) {
    const char* e = doc["estado"] | "toggle";
    ponerLuz(!strcmp(e, "on") ? true : !strcmp(e, "off") ? false : !luz);
  } else if (!strcmp(accion, "alerta")) alerta();
  else if (!strcmp(accion, "calibrar_emg")) emg::pedirCalibracion = true;
  else if (!strcmp(accion, "calibrar_imu")) imu::pedirNeutro = true;
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
    mqtt.subscribe(T_PING, 0);
    publicarActuadores();
  } else {
    Serial.printf("[mqtt] falló (rc=%d)\n", mqtt.state());
  }
}

void publicarVitales() {
  JsonDocument doc;
  if (USAR_PULSO && pulso::dedo && pulso::bpm > 0) doc["bpm"] = (int)pulso::bpm; else doc["bpm"] = nullptr;
  if (USAR_PULSO && pulso::dedo && pulso::spo2 > 0) doc["spo2"] = (int)pulso::spo2; else doc["spo2"] = nullptr;
  doc["ts"] = millis();
  char buf[96];
  serializeJson(doc, buf);
  mqtt.publish(T_VITALES, buf);
}

void publicarDiagnostico() {            // estado interno cada 5 s (pruebas de conjunto)
  JsonDocument doc;
  doc["emg"]["calibrado"] = (bool)emg::calibrado;
  doc["emg"]["envolvente"] = (int)emg::envolvente;
  doc["emg"]["umbral"] = emg::calibrado ? (int)emg::umbral : -1;
  doc["imu"]["presente"] = (bool)imu::presente;
  doc["imu"]["pitch"] = roundf((imu::pitch - imu::p0) * 10) / 10;
  doc["imu"]["roll"] = roundf((imu::roll - imu::r0) * 10) / 10;
  doc["pulso"]["presente"] = (bool)pulso::presente;
  doc["pulso"]["ir"] = (uint32_t)pulso::irActual;
#if USAR_AUDIO
  doc["parlante"] = audio::conectado();
#endif
  doc["rssi"] = WiFi.RSSI();
  doc["heap"] = ESP.getFreeHeap();
  char buf[320];
  serializeJson(doc, buf);
  mqtt.publish(T_DIAG, buf);
}

// ---- tarea del bus I2C: MPU6050 + MAX30102 a 100 Hz; si uno falta, reintenta cada 3 s ----
void tareaI2C(void*) {
  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(I2C_HZ);
  uint32_t reintentoImu = 0, reintentoPulso = 0;
  TickType_t t = xTaskGetTickCount();
  for (;;) {
    vTaskDelayUntil(&t, 10);
#if USAR_IMU
    if (imu::presente) imu::paso();
    else if (millis() - reintentoImu > 3000) {
      reintentoImu = millis();
      imu::presente = imu::iniciar();
      Serial.println(imu::presente ? "[imu] MPU6050 encontrado" : "[imu] no responde 0x68: revisar cables");
      if (imu::presente) imu::pedirNeutro = true;
    }
#endif
#if USAR_PULSO
    if (pulso::presente) pulso::paso();
    else if (millis() - reintentoPulso > 3000) {
      reintentoPulso = millis();
      pulso::presente = pulso::iniciar();
      Serial.println(pulso::presente ? "[pulso] MAX30102 encontrado" : "[pulso] no responde 0x57: revisar cables");
    }
#endif
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
  digitalWrite(PIN_RELE, !RELE_ENCENDIDO);     // relé apagado al arrancar
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, !BUZZER_ENCENDIDO);
  Serial.println("\n[nodo] arrancando");

  cola = xQueueCreate(16, sizeof(Evento));
  emg::alEvento = eventoEMG;
  imu::alEvento = eventoIMU;

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);       // no se espera: los sensores y el audio arrancan igual
  // No usar WiFi.setSleep(false): con Bluetooth activo, el WiFi necesita su ahorro para compartir la radio.
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alRecibir);
  mqtt.setKeepAlive(5);                   // el LWT llega en ~7,5 s
  mqtt.setBufferSize(512);

#if USAR_AUDIO
  audio::iniciar();
#endif
#if USAR_EMG
  xTaskCreatePinnedToCore(emg::tarea, "emg", 4096, nullptr, 5, nullptr, 1);
#endif
#if USAR_IMU || USAR_PULSO
  xTaskCreatePinnedToCore(tareaI2C, "i2c", 8192, nullptr, 4, nullptr, 1);
#endif
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

  Evento e;
  while (xQueueReceive(cola, &e, 0) == pdTRUE) {
    char buf[64];
    if (e.origen == 'E') snprintf(buf, sizeof(buf), "{\"tipo\":\"%s\",\"ts\":%lu}", e.valor, millis());
    else snprintf(buf, sizeof(buf), "{\"dir\":\"%s\",\"ts\":%lu}", e.valor, millis());
    Serial.printf("[%s] %s\n", e.origen == 'E' ? "emg" : "imu", e.valor);
    if (mqtt.connected()) mqtt.publish(e.origen == 'E' ? T_EMG : T_IMU, buf);
  }

  static uint32_t tVitales = 0, tDiag = 0;
  if (mqtt.connected() && millis() - tVitales >= 1000) { tVitales = millis(); publicarVitales(); }
  if (mqtt.connected() && millis() - tDiag >= 5000) { tDiag = millis(); publicarDiagnostico(); }

  atenderBuzzer();
#if USAR_AUDIO
  audio::atender();
#endif

  if (Serial.available()) {             // pruebas sin MQTT
    char c = Serial.read();
    if (c >= '1' && c <= '6') frase(c - '0');
    else if (c == 'l') ponerLuz(!luz);
    else if (c == 'b') alerta();
    else if (c == 'e') emg::pedirCalibracion = true;
    else if (c == 'i') imu::pedirNeutro = true;
  }
  delay(5);
}
