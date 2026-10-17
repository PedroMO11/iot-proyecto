// nodo_asistivo.ino : firmware final integrado (README.md, paso 5)
// Esqueleto: se completa a medida que se aprueban las pruebas de firmware/pruebas/.
#if __has_include("config.h")
#include "config.h"
#else
#error "Falta config.h: copiar config.example.h como config.h y completarlo"
#endif

// ---- Pines (README.md, sección 3.2) ----
const int PIN_EMG    = 34;              // ADC1
const int PIN_SDA    = 21;              // MPU6050 (0x68) + MAX30102 (0x57)
const int PIN_SCL    = 22;
const int PIN_RELE   = 26;
const int PIN_BUZZER = 27;

// ---- Contrato MQTT (README.md, sección 4) ----
const char* T_EMG     = "asistivo/nodo1/emg/evento";
const char* T_IMU     = "asistivo/nodo1/imu/evento";
const char* T_VITALES = "asistivo/nodo1/vitales";
const char* T_CMD     = "asistivo/nodo1/cmd";
const char* T_ESTADO  = "asistivo/nodo1/estado";

// TODO (paso 5): FreeRTOS con dos núcleos.
//   - Núcleo 1: tarea de adquisición (EMG a 1 kHz, IMU a 100 Hz, MAX30102), sin delay().
//   - Núcleo 0: WiFi, MQTT y A2DP.
//   - Eventos entre tareas con colas (xQueueSend / xQueueReceive).

void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
  digitalWrite(PIN_RELE, !RELE_ENCENDIDO);    // relé apagado al arrancar
  pinMode(PIN_BUZZER, OUTPUT);
  digitalWrite(PIN_BUZZER, LOW);
}

void loop() {
}
