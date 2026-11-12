// imu.h : MPU6050 (clon con WHO_AM_I = 0x74) por registros, filtro complementario a 100 Hz y
// detector de gestos de cabeza (prueba 03a_mpu6050; README, paso 3a).
// - Posición neutra: promedio de 2 s al arrancar o al pedirla (corrige el desvío del clon y la vincha).
// - Gesto: |Δ| > IMU_UMBRAL durante 150 ms en el eje dominante → un evento; para el siguiente hay que
//   volver a |Δ| < IMU_SALIDA durante 200 ms (histéresis). Refractario de 500 ms.
// - adelante (pitch +) = "abajo", atrás = "arriba", izquierda (roll −) = "izq", derecha = "der".
#pragma once
#include <Wire.h>

namespace imu {

const uint8_t DIR = 0x68;
const float ALFA = 0.98f, DT = 0.01f, LSB_G = 16384.0f, LSB_DPS = 131.0f;
const uint32_t ASENTAR_MS = 1000, NEUTRO_MS = 2000, MANTENER_MS = 150, SOLTAR_MS = 200, REFRACTARIO_MS = 500;

volatile bool presente = false, calibrado = false, pedirNeutro = true;
volatile float pitch = 0, roll = 0, p0 = 0, r0 = 0;
void (*alEvento)(const char* dir) = nullptr;

void escribir(uint8_t reg, uint8_t v) {
  Wire.beginTransmission(DIR); Wire.write(reg); Wire.write(v); Wire.endTransmission();
}

bool iniciar() {
  Wire.beginTransmission(DIR);
  if (Wire.endTransmission() != 0) return false;
  escribir(0x6B, 0x00);                 // despertar
  escribir(0x1A, 0x04);                 // filtro pasa bajos ~21 Hz
  escribir(0x1B, 0x00);                 // ±250 °/s
  escribir(0x1C, 0x00);                 // ±2 g
  return true;
}

bool leer(float a[3], float g[3]) {
  Wire.beginTransmission(DIR); Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(DIR, (uint8_t)14) != 14) return false;
  int16_t v[7];
  for (int i = 0; i < 7; i++) v[i] = (int16_t)(Wire.read() << 8 | Wire.read());
  for (int i = 0; i < 3; i++) { a[i] = v[i] / LSB_G; g[i] = v[i + 4] / LSB_DPS; }   // v[3] = temperatura
#if IMU_FRENTE
  // Vertical con X hacia arriba: pitch y roll serían inestables. Se giran 90° los ejes (x, y, z) → (z, −y, x)
  // en acelerómetro y giroscopio, para que el resto del cálculo vea un sensor plano.
  float t_ = a[0]; a[0] = a[2]; a[2] = t_; a[1] = -a[1];
  t_ = g[0]; g[0] = g[2]; g[2] = t_; g[1] = -g[1];
#endif
  return true;
}

// Llamar cada 10 ms desde la tarea del bus I2C
void paso() {
  static uint32_t tNeutro = 0, tFuera = 0, tDentro = 0, tUltimo = 0;
  static double sp = 0, sr = 0;
  static uint32_t n = 0;
  static bool inclinado = false, contando = false;
  float a[3], g[3];
  if (!leer(a, g)) { presente = false; return; }
  float pitchAcc = atan2(-a[0], sqrt(a[1] * a[1] + a[2] * a[2])) * RAD_TO_DEG;
  float rollAcc = atan2(a[1], a[2]) * RAD_TO_DEG;
  pitch = ALFA * (pitch + g[1] * DT) + (1 - ALFA) * pitchAcc;
  roll = ALFA * (roll + g[0] * DT) + (1 - ALFA) * rollAcc;
  uint32_t ahora = millis();

  if (pedirNeutro) {
    pedirNeutro = false; calibrado = false;
    tNeutro = ahora; sp = sr = 0; n = 0;
    Serial.println("[imu] posición neutra: cabeza quieta 3 s");
  }
  if (!calibrado) {
    if (ahora - tNeutro > ASENTAR_MS) { sp += pitch; sr += roll; n++; }
    if (ahora - tNeutro > ASENTAR_MS + NEUTRO_MS && n > 0) {
      p0 = sp / n; r0 = sr / n; calibrado = true; inclinado = false; contando = false;
      Serial.printf("[imu] neutro: pitch %.1f°, roll %.1f°\n", (float)p0, (float)r0);
    }
    return;
  }

  float dp = IMU_SIGNO_PITCH * (pitch - p0), dr = IMU_SIGNO_ROLL * (roll - r0);
#if IMU_INTERCAMBIAR
  float t_ = dp; dp = dr; dr = t_;
#endif
  float mayor = max(fabsf(dp), fabsf(dr));
  if (!inclinado) {
    if (mayor > IMU_UMBRAL && ahora - tUltimo >= REFRACTARIO_MS) {
      if (!contando) { contando = true; tFuera = ahora; }
      else if (ahora - tFuera >= MANTENER_MS) {
        const char* dir = fabsf(dp) >= fabsf(dr) ? (dp > 0 ? "abajo" : "arriba") : (dr < 0 ? "izq" : "der");
        if (alEvento) alEvento(dir);
        inclinado = true; contando = false; tUltimo = ahora;
      }
    } else contando = false;
  } else {
    if (fabsf(dp) < IMU_SALIDA && fabsf(dr) < IMU_SALIDA) {
      if (!contando) { contando = true; tDentro = ahora; }
      else if (ahora - tDentro >= SOLTAR_MS) { inclinado = false; contando = false; }
    } else contando = false;
  }
}

}  // namespace imu
