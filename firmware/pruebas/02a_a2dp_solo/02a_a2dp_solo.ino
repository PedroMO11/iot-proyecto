// 02a_a2dp_solo.ino : reproduce las frases por Bluetooth y prueba el buzzer (sin WiFi)
#include "BluetoothA2DPSource.h"
#include "frases.h"

const char* PARLANTE = "Xiaomi Sound Pocket";   // nombre Bluetooth del parlante

const int PIN_BUZZER = 27;              // buzzer activo directo al GPIO
const uint32_t ALERTA_MS = 2000;

BluetoothA2DPSource a2dp;

// La librería solo acepta nombres que empiecen exactamente igual. Con el Xiaomi
// funcionó mejor buscar PARLANTE dentro del nombre, sin distinguir mayúsculas.
bool esParlante(const char* nombre, esp_bd_addr_t direccion, int rssi) {
  String visto = nombre, buscado = PARLANTE;
  visto.toLowerCase();
  buscado.toLowerCase();
  bool coincide = visto.indexOf(buscado) >= 0;
  Serial.printf("Visto: \"%s\" (RSSI %d)%s\n", nombre, rssi, coincide ? " <- parlante" : "");
  return coincide;
}

// Reproducción: las frases están a 16 kHz y A2DP pide 44,1 kHz estéreo,
// así que avanzamos 16000/44100 muestras por cada cuadro enviado.
volatile int fraseActual = -1;          // -1 = silencio
volatile float posicion = 0;
const float PASO = 16000.0f / 44100.0f;
const float GANANCIA = 2.5f;            // los WAV llegan con pico ~12000/32767; x2,5 no satura

// ESP32-A2DP 1.8.11 no reintenta sola tras una desconexión: se queda quieta.
// Cada RECONEXION_MS sin parlante se vuelve a llamar a la última dirección conocida.
const uint32_t RECONEXION_MS = 10000;

int32_t get_data_frames(Frame* frame, int32_t frame_count) {
  for (int i = 0; i < frame_count; i++) {
    int16_t muestra = 0;
    int f = fraseActual;
    if (f >= 0) {
      uint32_t idx = (uint32_t)posicion;
      if (idx < FRASES_LEN[f]) {
        muestra = constrain(FRASES[f][idx] * GANANCIA, -32768.0f, 32767.0f);
        posicion += PASO;
      } else {
        fraseActual = -1;               // terminó la frase
      }
    }
    frame[i].channel1 = muestra;        // izquierdo
    frame[i].channel2 = muestra;        // derecho
  }
  delay(1);                             // evita el watchdog (recomendado por la librería)
  return frame_count;
}

void reproducir(int id) {               // id de 1 a NUM_FRASES
  if (id < 1 || id > NUM_FRASES) return;
  posicion = 0;
  fraseActual = id - 1;
  Serial.printf("Reproduciendo frase %d\n", id);
}

bool alertaActiva = false;
uint32_t inicioAlerta = 0;

void alerta() {                         // el loop apaga el buzzer tras ALERTA_MS, sin bloquear
  digitalWrite(PIN_BUZZER, HIGH);
  alertaActiva = true;
  inicioAlerta = millis();
  Serial.println("Alerta: buzzer ON");
}

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
  a2dp.set_data_callback_in_frames(get_data_frames);
  a2dp.set_ssid_callback(esParlante);
  a2dp.set_volume(127);                 // 0 a 127 (máximo)
  a2dp.set_auto_reconnect(true);        // guarda la dirección en la NVS y la usa al arrancar
  a2dp.start();                         // sin nombre: decide esParlante
  Serial.printf("Buscando \"%s\"... escribe 1-6 (frase) o 'a' (buzzer) en el Monitor Serie\n", PARLANTE);
}

void loop() {
  static bool conectadoAntes = false, huboConexion = false;
  static uint32_t ultimoIntento = 0;
  bool conectado = a2dp.is_connected();
  if (conectado != conectadoAntes) {
    conectadoAntes = conectado;
    if (conectado) huboConexion = true;
    ultimoIntento = millis();
    Serial.println(conectado ? "Parlante CONECTADO" : "Parlante desconectado");
  }
  if (!conectado && huboConexion && millis() - ultimoIntento >= RECONEXION_MS) {
    ultimoIntento = millis();
    Serial.println("Reintentando conexión con el parlante...");
    a2dp.reconnect();
  }
  if (alertaActiva && millis() - inicioAlerta >= ALERTA_MS) {
    digitalWrite(PIN_BUZZER, LOW);
    alertaActiva = false;
    Serial.println("Alerta: buzzer OFF");
  }
  if (Serial.available()) {
    char c = Serial.read();
    if (c >= '1' && c <= '9') reproducir(c - '0');
    if (c == 'a') alerta();
  }
  delay(10);
}
