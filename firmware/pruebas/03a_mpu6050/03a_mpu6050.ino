// 03a_mpu6050.ino : inclinación de la cabeza con filtro complementario (100 Hz)
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

Adafruit_MPU6050 mpu;
const float ALFA = 0.98, DT = 0.01;     // 10 ms
float pitch = 0, roll = 0;

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  if (!mpu.begin()) { Serial.println("No se encontró el MPU6050"); while (true) delay(10); }
  mpu.setAccelerometerRange(MPU6050_RANGE_2_G);
  mpu.setGyroRange(MPU6050_RANGE_250_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
}

void loop() {
  static uint32_t t = millis();
  if (millis() - t < 10) return;
  t += 10;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);
  float ax = a.acceleration.x, ay = a.acceleration.y, az = a.acceleration.z;
  float pitchAcc = atan2(-ax, sqrt(ay * ay + az * az)) * RAD_TO_DEG;
  float rollAcc  = atan2(ay, az) * RAD_TO_DEG;

  pitch = ALFA * (pitch + g.gyro.y * RAD_TO_DEG * DT) + (1 - ALFA) * pitchAcc;
  roll  = ALFA * (roll  + g.gyro.x * RAD_TO_DEG * DT) + (1 - ALFA) * rollAcc;

  Serial.printf("pitch:%.1f,roll:%.1f\n", pitch, roll);
}
