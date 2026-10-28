// 03a_mpu6050.ino : inclinación de la cabeza con filtro complementario (100 Hz)
// Lee los registros directamente: el módulo GY-521 del grupo trae un chip compatible con
// WHO_AM_I = 0x74 (no 0x68) y la librería de Adafruit lo rechaza. Los registros usados
// son los mismos en toda la familia MPU6050/6500.
#include <Wire.h>

const uint8_t MPU = 0x68;
const float ALFA = 0.98, DT = 0.01;     // 10 ms
const float LSB_G = 16384.0;            // ±2 g
const float LSB_DPS = 131.0;            // ±250 °/s
float pitch = 0, roll = 0;

void escribir(uint8_t reg, uint8_t valor) {
  Wire.beginTransmission(MPU); Wire.write(reg); Wire.write(valor); Wire.endTransmission();
}

uint8_t leer(uint8_t reg) {
  Wire.beginTransmission(MPU); Wire.write(reg); Wire.endTransmission(false);
  Wire.requestFrom(MPU, (uint8_t)1);
  return Wire.read();
}

void leerEjes(uint8_t reg, float v[3]) {   // 3 enteros de 16 bits big-endian desde reg
  Wire.beginTransmission(MPU); Wire.write(reg); Wire.endTransmission(false);
  Wire.requestFrom(MPU, (uint8_t)6);
  for (int i = 0; i < 3; i++) v[i] = (int16_t)(Wire.read() << 8 | Wire.read());
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  Wire.beginTransmission(MPU);
  if (Wire.endTransmission() != 0) { Serial.println("No responde nada en 0x68"); while (true) delay(10); }
  Serial.printf("WHO_AM_I = 0x%02X\n", leer(0x75));
  escribir(0x6B, 0x00);                 // PWR_MGMT_1: despertar
  escribir(0x1A, 0x04);                 // CONFIG: filtro pasa bajos ~21 Hz
  escribir(0x1B, 0x00);                 // GYRO_CONFIG: ±250 °/s
  escribir(0x1C, 0x00);                 // ACCEL_CONFIG: ±2 g
  delay(100);
}

void loop() {
  static uint32_t t = millis();
  if (millis() - t < 10) return;
  t += 10;

  float a[3], g[3];
  leerEjes(0x3B, a);                    // ACCEL_XOUT_H..
  leerEjes(0x43, g);                    // GYRO_XOUT_H..
  float ax = a[0] / LSB_G, ay = a[1] / LSB_G, az = a[2] / LSB_G;
  float gx = g[0] / LSB_DPS, gy = g[1] / LSB_DPS;
  float pitchAcc = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG;
  float rollAcc  = atan2(ay, az) * RAD_TO_DEG;

  pitch = ALFA * (pitch + gy * DT) + (1 - ALFA) * pitchAcc;
  roll  = ALFA * (roll  + gx * DT) + (1 - ALFA) * rollAcc;

  Serial.printf("pitch:%.1f,roll:%.1f\n", pitch, roll);
}
