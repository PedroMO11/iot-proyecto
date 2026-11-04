// emg.h : tarea de 1 kHz del EMG (pruebas 03c_emg_senal y 03c_emg_eventos).
// Señal → filtro de 60/120/180 Hz (opción B) → rectificación → envolvente de 50 ms.
// Calibración: 1 s para asentarse + 5 s en reposo → umbral = max(μ + EMG_SIGMAS·σ, μ + EMG_MARGEN).
// Confirmar = sobre el umbral entre 100 ms y 1 s; cancelar = más de 1 s; refractario de 700 ms.
#pragma once

namespace emg {

const int PIN = 34;                     // ADC1 (el ADC2 no funciona con WiFi)
const int VENTANA = 50;                 // 50 ms a 1 kHz
const uint32_t ASENTAR_MS = 1000, CALIBRACION_MS = 5000;
const uint32_t MIN_MS = 100, CANCELAR_MS = 1000, REFRACTARIO_MS = 700;

volatile float envolvente = 0, mu = 0, sigma = 0, umbral = 1e9;
volatile bool calibrado = false, pedirCalibracion = true;

struct Notch {                          // biquad (RBJ Audio EQ Cookbook) a 1 kHz
  float b0, b1, b2, a1, a2, x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  Notch(float f0, float q) {
    float w = 2 * PI * f0 / 1000.0f, alfa = sin(w) / (2 * q), a0 = 1 + alfa;
    b0 = 1 / a0; b1 = -2 * cos(w) / a0; b2 = 1 / a0; a1 = -2 * cos(w) / a0; a2 = (1 - alfa) / a0;
  }
  float paso(float x) {
    float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x; y2 = y1; y1 = y;
    return y;
  }
};

void (*alEvento)(const char* tipo) = nullptr;   // lo asigna el sketch: publica en emg/evento

void tarea(void*) {
  analogReadResolution(12);
  analogSetPinAttenuation(PIN, ADC_11db);
  Notch red[] = {Notch(60, 8), Notch(120, 8), Notch(180, 8)};
  float buf[VENTANA] = {0}, suma = 0;
  int ib = 0;
  float base = analogRead(PIN);
  // calibración y detección
  uint32_t tCal = 0;
  double s = 0, s2 = 0;
  uint32_t n = 0;
  bool encima = false, cancelado = false;
  uint32_t tInicio = 0, tUltimo = 0;
  TickType_t t = xTaskGetTickCount();

  for (;;) {
    vTaskDelayUntil(&t, 1);             // 1 tick = 1 ms
    int x = analogRead(PIN);
#if EMG_OPCION == EMG_DFROBOT
    base = 0.999f * base + 0.001f * x;  // nivel de reposo (~1,5 V)
    float f = x - base;
    for (Notch& q : red) f = q.paso(f);
    float r = fabsf(f);
#else
    float r = x;                        // la placa roja ya entrega la envolvente
#endif
    suma += r - buf[ib];
    buf[ib] = r;
    ib = (ib + 1) % VENTANA;
    float env = suma / VENTANA;
    envolvente = env;
    uint32_t ahora = millis();

    if (pedirCalibracion) {             // empezar (o repetir) la calibración
      pedirCalibracion = false;
      calibrado = false;
      tCal = ahora; s = s2 = 0; n = 0; encima = false;
      Serial.println("[emg] calibrando: mandíbula RELAJADA 6 s");
    }
    if (!calibrado) {
      if (ahora - tCal > ASENTAR_MS) { s += env; s2 += (double)env * env; n++; }
      if (ahora - tCal > ASENTAR_MS + CALIBRACION_MS && n > 0) {
        mu = s / n;
        sigma = sqrt(max(0.0, s2 / n - (double)mu * mu));
        umbral = max(mu + EMG_SIGMAS * sigma, mu + EMG_MARGEN);
        calibrado = true;
        Serial.printf("[emg] listo: μ=%.1f σ=%.1f umbral=%.1f\n", (float)mu, (float)sigma, (float)umbral);
      }
      continue;
    }

    bool activo = env > umbral;
    if (activo && !encima && ahora - tUltimo >= REFRACTARIO_MS) {
      encima = true; tInicio = ahora; cancelado = false;
    }
    if (encima) {
      uint32_t dur = ahora - tInicio;
      if (activo && !cancelado && dur > CANCELAR_MS) {
        cancelado = true;
        if (alEvento) alEvento("cancelar");
      }
      if (!activo) {
        if (!cancelado && dur >= MIN_MS && alEvento) alEvento("confirmar");
        if (cancelado || dur >= MIN_MS) tUltimo = ahora;
        encima = false;
      }
    }
  }
}

}  // namespace emg
