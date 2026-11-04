// audio.h : frases por Bluetooth A2DP (pruebas 02a y 02b).
// - Busca el parlante por parte del nombre (PARLANTE) y guarda su dirección para reconectar sin
//   modo emparejamiento. Si PARLANTE cambia, olvida el anterior.
// - ESP32-A2DP 1.8.11 no reintenta sola tras una desconexión: cada 10 s se llama a reconnect().
#pragma once
#include <Preferences.h>
#include "BluetoothA2DPSource.h"
#include "frases.h"

namespace audio {

BluetoothA2DPSource a2dp;
volatile int fraseActual = -1;          // -1 = silencio
volatile float posicion = 0;
const float PASO = 16000.0f / 44100.0f; // frases a 16 kHz, A2DP pide 44,1 kHz estéreo
const uint32_t RECONEXION_MS = 10000;

int32_t datos(Frame* frame, int32_t n) {
  for (int i = 0; i < n; i++) {
    int16_t m = 0;
    int f = fraseActual;
    if (f >= 0) {
      uint32_t idx = (uint32_t)posicion;
      if (idx < FRASES_LEN[f]) {
        m = constrain(FRASES[f][idx] * GANANCIA_AUDIO, -32768.0f, 32767.0f);
        posicion += PASO;
      } else {
        fraseActual = -1;
      }
    }
    frame[i].channel1 = m;
    frame[i].channel2 = m;
  }
  delay(1);                             // evita el watchdog (recomendado por la librería)
  return n;
}

bool elegir(const char* nombre, esp_bd_addr_t, int rssi) {
  String n(nombre), b(PARLANTE);
  n.toLowerCase(); b.toLowerCase();
  bool ok = n.indexOf(b) >= 0;
  Serial.printf("[audio] encontrado \"%s\" (RSSI %d)%s\n", nombre, rssi, ok ? "  <-- este" : "");
  return ok;
}

void iniciar() {
  Preferences pref;
  pref.begin("nodo", false);
  if (pref.getString("parlante", "") != PARLANTE) {
    // clean_last_connection() no borra la NVS si la dirección en memoria ya es cero: primero una ficticia
    esp_bd_addr_t ficticia = {0x02, 0, 0, 0, 0, 0};
    a2dp.set_auto_reconnect(ficticia);
    a2dp.clean_last_connection();
    pref.putString("parlante", PARLANTE);
    Serial.printf("[audio] parlante nuevo (\"%s\"): buscando en modo emparejamiento\n", PARLANTE);
  }
  pref.end();
  a2dp.set_auto_reconnect(true);        // guarda la dirección en la NVS y la usa al arrancar
  a2dp.set_data_callback_in_frames(datos);
  a2dp.set_volume(VOLUMEN);
  a2dp.set_ssid_callback(elegir);
  a2dp.start();
}

void reproducir(int id) {               // id de 1 a NUM_FRASES
  if (id < 1 || id > NUM_FRASES) return;
  posicion = 0;
  fraseActual = id - 1;
}

bool conectado() { return a2dp.is_connected(); }

void atender() {                        // en loop(): avisos y reconexión
  static bool antes = false, huboConexion = false;
  static uint32_t ultimoIntento = 0;
  bool ahora = a2dp.is_connected();
  if (ahora != antes) {
    antes = ahora;
    if (ahora) huboConexion = true;
    ultimoIntento = millis();
    Serial.println(ahora ? "[audio] parlante CONECTADO" : "[audio] parlante desconectado");
  }
  if (!ahora && huboConexion && millis() - ultimoIntento >= RECONEXION_MS) {
    ultimoIntento = millis();
    a2dp.reconnect();
  }
}

}  // namespace audio
