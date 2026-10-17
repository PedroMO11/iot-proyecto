// Plantilla de configuración. Copiar este archivo como config.h y completarlo.
// config.h está en .gitignore: NUNCA subirlo (tiene la contraseña del WiFi).
#pragma once

// ---- Red ----
#define WIFI_SSID  "TU_RED"
#define WIFI_PASS  "TU_CLAVE"
#define MQTT_HOST  "192.168.1.100"          // IP de la laptop con Mosquitto
#define MQTT_PORT  1883

// ---- Audio ----
#define PARLANTE   "NOMBRE EXACTO DEL PARLANTE"
#define VOLUMEN    80                       // 0 a 127

// ---- Sensor EMG (README.md, sección 3.1) ----
#define EMG_MUSCLE_SENSOR  1                // Opción A: placa roja, envolvente, divisor 20k/10k, 500 Hz
#define EMG_DFROBOT        2                // Opción B: OYMotion SEN0240, señal cruda, 1 kHz
#define EMG_OPCION         EMG_DFROBOT

// ---- Relé (CHECKLIST_ARMADO.md, sección 5.1) ----
// Muchos módulos se activan con LOW. Ajustar según lo anotado en la prueba 04a_rele.
#define RELE_ENCENDIDO     LOW
