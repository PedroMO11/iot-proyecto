// 03b_max30102.ino : pulso y SpO₂ con el algoritmo de Maxim (adaptado de SparkFun Example8_SPO2)
// Cambios para el ESP32:
//  - el ejemplo usa los pines 11 y 13 como LEDs, y el GPIO11 es de la flash interna
//    (cuelga el chip y salta el watchdog); tampoco espera una tecla para empezar;
//  - la FIFO se lee directo de los registros: con check()/available() de la librería
//    (búfer de 4 muestras) solo llegaban ~10 de las 25 muestras/s que entrega el sensor;
//  - si el sensor deja de responder (contacto flojo), avisa y lo reinicia en vez de colgarse.
// 25 muestras/s: ventana de 4 s (100 muestras) que avanza de 1 s en 1 s.
#include <Wire.h>
#include "MAX30105.h"
#include "spo2_algorithm.h"

const uint8_t MAX = 0x57;
const int VENTANA = 100;                // 4 s a 25 muestras/s
const int PASO = 25;                    // recalcular cada 1 s
const uint32_t IR_MIN_DEDO = 50000;     // por debajo: no hay dedo
const uint32_t TIMEOUT_MS = 500;        // sin muestras en este tiempo = sensor sin respuesta

MAX30105 sensor;                        // solo para configurarlo
uint32_t irBuf[VENTANA], redBuf[VENTANA];

uint8_t leerReg(uint8_t reg) {
  Wire.beginTransmission(MAX); Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return 0xFF;
  if (Wire.requestFrom(MAX, (uint8_t)1) != 1) return 0xFF;
  return Wire.read();
}

void iniciarSensor() {
  while (!sensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("No se encontró el MAX30102 (0x57): revisar cables");
    delay(1000);
  }
  // brillo 30 (~6 mA), promedio de 4, rojo + IR, 100 Hz (25 muestras/s tras promediar), 411 µs, 4096 nA.
  // Con el brillo 60 del ejemplo, el IR con dedo quedaba al 96 % del tope (262143) y el pulso se aplanaba.
  sensor.setup(30, 4, 2, 100, 411, 4096);
}

// Una muestra (rojo + IR) de la FIFO del sensor: registros 0x04 (escritura), 0x06 (lectura), 0x07 (datos)
bool leerFIFO(uint32_t &red, uint32_t &ir) {
  uint32_t t0 = millis();
  while (((leerReg(0x04) - leerReg(0x06)) & 0x1F) == 0) {
    if (millis() - t0 > TIMEOUT_MS) return false;
    delay(2);
  }
  Wire.beginTransmission(MAX); Wire.write(0x07);
  if (Wire.endTransmission(false) != 0 || Wire.requestFrom(MAX, (uint8_t)6) != 6) return false;
  uint8_t b[6];
  for (int i = 0; i < 6; i++) b[i] = Wire.read();
  red = ((uint32_t)b[0] << 16 | b[1] << 8 | b[2]) & 0x3FFFF;   // 18 bits
  ir  = ((uint32_t)b[3] << 16 | b[4] << 8 | b[5]) & 0x3FFFF;
  return true;
}

void leerMuestra(int i) {
  while (!leerFIFO(redBuf[i], irBuf[i])) {
    Serial.println("MAX30102 sin respuesta: reiniciando");
    iniciarSensor();
  }
  Serial.printf("ir:%lu\n", (unsigned long)irBuf[i]);   // para graficar en el Serial Plotter
}

void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);
  iniciarSensor();
  for (int i = 0; i < VENTANA; i++) leerMuestra(i);
}

void loop() {
  int32_t spo2, hr;
  int8_t spo2Ok, hrOk;
  bool dedo = irBuf[VENTANA - 1] > IR_MIN_DEDO;
  if (dedo) {
    maxim_heart_rate_and_oxygen_saturation(irBuf, VENTANA, redBuf, &spo2, &spo2Ok, &hr, &hrOk);
    Serial.printf("HR=%ld HRvalid=%d SPO2=%ld SPO2valid=%d\n", (long)hr, hrOk, (long)spo2, spo2Ok);
  } else {
    Serial.println("sin dedo");
  }
  // desplazar la ventana y leer 1 s nuevo
  memmove(irBuf, irBuf + PASO, (VENTANA - PASO) * sizeof(uint32_t));
  memmove(redBuf, redBuf + PASO, (VENTANA - PASO) * sizeof(uint32_t));
  for (int i = VENTANA - PASO; i < VENTANA; i++) leerMuestra(i);
}
