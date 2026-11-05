// pulso.h : MAX30102, pulso y SpO₂ (prueba 03b_max30102).
// - FIFO leída directo de los registros (25 muestras/s; con check()/available() de la librería
//   llegaban ~10). Brillo 30: con 60 el IR se saturaba al 96 %.
// - Pulso: algoritmo propio en flujo (quitar la componente lenta, pasa bajos, máximos de −IR con
//   umbral adaptable, mediana de los últimos 6 intervalos). Sobre la grabación del 2026-10-28 da
//   79 BPM (75–83), igual que el análisis offline; el de Maxim daba 125.
// - SpO₂: algoritmo de Maxim sobre la ventana de 4 s, solo su SpO₂.
#pragma once
#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

namespace pulso {

const uint8_t DIR = 0x57;
const float FS = 25.0f;
const uint32_t IR_MIN_DEDO = 50000;
const int VENTANA = 100;                // 4 s para la SpO₂

MAX30105 sensor;
volatile bool presente = false, dedo = false;
volatile int bpm = 0, spo2 = 0;         // 0 = sin dato válido
volatile uint32_t irActual = 0;

uint32_t irBuf[VENTANA], redBuf[VENTANA];
int iBuf = 0, nBuf = 0;
// estado del detector de latidos
float dc = 0, lp = 0, env = 0, prev1 = 0, prev2 = 0;
uint32_t n = 0, ultimo = 0;
bool hayUltimo = false;
float intervalos[6];
int nInt = 0;

uint8_t leerReg(uint8_t r) {
  Wire.beginTransmission(DIR); Wire.write(r);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(DIR, (uint8_t)1) != 1) return 0xFF;
  return Wire.read();
}

bool iniciar() {
  if (!sensor.begin(Wire, I2C_HZ)) return false;
  sensor.setup(30, 4, 2, 100, 411, 4096);   // brillo 30, promedio 4, rojo+IR, 100 Hz → 25 muestras/s
  return true;
}

void reiniciarLatidos() { hayUltimo = false; nInt = 0; env = 0; bpm = 0; }

void latido(uint32_t ir) {              // una muestra al detector de latidos
  if (n == 0) dc = ir;
  dc += (ir - dc) * 0.05f;
  lp += ((ir - dc) - lp) * 0.5f;
  float y = -lp;                        // el latido baja el IR: se buscan máximos de −IR
  env = max(fabsf(y), env * 0.97f);
  if (prev1 > prev2 && prev1 >= y && prev1 > 0.5f * env) {
    uint32_t m = n - 1;
    if (!hayUltimo || (m - ultimo) / FS >= 0.33f) {          // ≤ 180 BPM
      if (hayUltimo && (m - ultimo) / FS <= 1.5f) {           // ≥ 40 BPM
        if (nInt == 6) { memmove(intervalos, intervalos + 1, 5 * sizeof(float)); nInt = 5; }
        intervalos[nInt++] = (m - ultimo) / FS;
      }
      ultimo = m; hayUltimo = true;
    }
  }
  prev2 = prev1; prev1 = y; n++;
  if (nInt >= 3) {
    float o[6]; memcpy(o, intervalos, nInt * sizeof(float));
    std::sort(o, o + nInt);
    float med = nInt % 2 ? o[nInt / 2] : (o[nInt / 2 - 1] + o[nInt / 2]) / 2;
    bpm = (int)lroundf(60.0f / med);
  }
}

void calcularSpO2() {                   // una vez por segundo
  if (nBuf < VENTANA || !dedo) { spo2 = 0; return; }
  uint32_t ir[VENTANA], red[VENTANA];
  for (int i = 0; i < VENTANA; i++) { int k = (iBuf + i) % VENTANA; ir[i] = irBuf[k]; red[i] = redBuf[k]; }
  int32_t s, h; int8_t sOk, hOk;
  maxim_heart_rate_and_oxygen_saturation(ir, VENTANA, red, &s, &sOk, &h, &hOk);
  spo2 = (sOk && s > 0 && s <= 100) ? s : 0;
}

// Llamar cada 10 ms desde la tarea del bus I2C: lee lo que haya en la FIFO (registros 0x04, 0x06, 0x07)
void paso() {
  static uint32_t tSpO2 = 0;
  uint8_t w = leerReg(0x04), r = leerReg(0x06);
  if (w == 0xFF || r == 0xFF) { presente = false; return; }
  int pendientes = (w - r) & 0x1F;
  for (int k = 0; k < pendientes; k++) {
    Wire.beginTransmission(DIR); Wire.write(0x07);
    if (Wire.endTransmission(false) != 0 || Wire.requestFrom(DIR, (uint8_t)6) != 6) { presente = false; return; }
    uint8_t b[6];
    for (int i = 0; i < 6; i++) b[i] = Wire.read();
    uint32_t red = ((uint32_t)b[0] << 16 | b[1] << 8 | b[2]) & 0x3FFFF;
    uint32_t ir = ((uint32_t)b[3] << 16 | b[4] << 8 | b[5]) & 0x3FFFF;
    irActual = ir;
    bool hay = ir > IR_MIN_DEDO;
    if (hay != dedo) { dedo = hay; reiniciarLatidos(); n = 0; }
    irBuf[iBuf] = ir; redBuf[iBuf] = red;
    iBuf = (iBuf + 1) % VENTANA; nBuf = min(nBuf + 1, VENTANA);
    if (dedo) latido(ir);
  }
  if (millis() - tSpO2 >= 1000) { tSpO2 = millis(); calcularSpO2(); }
}

}  // namespace pulso
