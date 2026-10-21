// 02a_a2dp_solo.ino : reproduce las frases por Bluetooth (sin WiFi)
#include "BluetoothA2DPSource.h"
#include "frases.h"

const char* PARLANTE = "ULT WEAR";   // audífonos Sony ULT WEAR (nombre Bluetooth exacto)

BluetoothA2DPSource a2dp;

// Reproducción: las frases están a 16 kHz y A2DP pide 44,1 kHz estéreo,
// así que avanzamos 16000/44100 muestras por cada cuadro enviado.
volatile int fraseActual = -1;          // -1 = silencio
volatile float posicion = 0;
const float PASO = 16000.0f / 44100.0f;

int32_t get_data_frames(Frame* frame, int32_t frame_count) {
  for (int i = 0; i < frame_count; i++) {
    int16_t muestra = 0;
    int f = fraseActual;
    if (f >= 0) {
      uint32_t idx = (uint32_t)posicion;
      if (idx < FRASES_LEN[f]) {
        muestra = FRASES[f][idx];
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

void setup() {
  Serial.begin(115200);
  a2dp.set_data_callback_in_frames(get_data_frames);
  a2dp.set_volume(80);                  // 0 a 127
  a2dp.start(PARLANTE);
  Serial.println("Buscando parlante... escribe 1-6 en el Monitor Serie");
}

void loop() {
  static bool conectadoAntes = false;
  if (a2dp.is_connected() != conectadoAntes) {
    conectadoAntes = a2dp.is_connected();
    Serial.println(conectadoAntes ? "Parlante CONECTADO" : "Parlante desconectado");
  }
  if (Serial.available()) {
    char c = Serial.read();
    if (c >= '1' && c <= '9') reproducir(c - '0');
  }
  delay(10);
}
