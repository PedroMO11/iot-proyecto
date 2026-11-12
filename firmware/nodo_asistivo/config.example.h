// Plantilla de configuración. Copiar este archivo como config.h y completarlo.
// config.h está en .gitignore: NUNCA subirlo (tiene la contraseña del WiFi).
#pragma once

// ---- Red ----
#define WIFI_SSID  "TU_RED"
#define WIFI_PASS  "TU_CLAVE"
#define MQTT_HOST  "192.168.1.100"          // IP de la laptop con Mosquitto
#define MQTT_PORT  1883
#define NODO       "asistivo/nodo1"         // prefijo de los topics (README, sección 4)

// ---- Módulos: 1 = activo, 0 = desactivado (para probar el sistema por partes) ----
#define USAR_AUDIO  1
#define USAR_EMG    1
#define USAR_IMU    1
#define USAR_PULSO  1

// ---- Audio ----
// Parte del nombre Bluetooth del parlante, sin importar mayúsculas: "xiaomi", "ult wear"...
// Si se cambia, el ESP32 olvida el parlante anterior y busca el nuevo (en modo emparejamiento).
#define PARLANTE        "xiaomi"
#define VOLUMEN         127                 // 0 a 127
#define GANANCIA_AUDIO  2.5f                // los WAV TTS llegan con pico ~12 000 de 32 767

// ---- Sensor EMG (README.md, sección 3.1) ----
#define EMG_MUSCLE_SENSOR  1                // Opción A: placa roja, envolvente, divisor 20k/10k
#define EMG_DFROBOT        2                // Opción B: OYMotion SEN0240, señal cruda (filtro de 60 Hz)
#define EMG_OPCION         EMG_DFROBOT
#define EMG_SIGMAS         3.0f             // umbral = μ + EMG_SIGMAS·σ de la calibración en reposo
#define EMG_MARGEN         50.0f            // …y como mínimo μ + EMG_MARGEN (cuentas del ADC)

// ---- IMU (MPU6050 en la vincha) ----
#define IMU_UMBRAL         15.0f            // grados de inclinación para un gesto
#define IMU_SALIDA         7.0f             // volver a menos de esto para el siguiente gesto
// Orientación medida en la mano (CHECKLIST 4.1): adelante = pitch +, izquierda = roll −.
// Si en la vincha queda al revés o girado, cambiar aquí sin tocar el código.
#define IMU_SIGNO_PITCH    1                // -1 si "adelante" da pitch negativo
#define IMU_SIGNO_ROLL     1                // -1 si "izquierda" da roll positivo
#define IMU_INTERCAMBIAR   0                // 1 si el sensor quedó girado 90° (pitch ↔ roll)
#define IMU_FRENTE         1                // 1 = vertical en la frente con los pines hacia abajo; 0 = plano

// ---- Bus I2C (MPU6050 + MAX30102) ----
#define I2C_HZ             100000           // 100 kHz: más tolerante con los cables largos de la vincha

// ---- Actuadores (CHECKLIST_ARMADO.md, sección 5) ----
// Módulo de 2 canales con IN directo a D26: se enciende con LOW. HIGH solo si IN se maneja con un transistor.
#define RELE_ENCENDIDO     LOW
#define BUZZER_ENCENDIDO   HIGH             // buzzer activo directo a D27, sin transistor (suena bien a 3,3 V)
