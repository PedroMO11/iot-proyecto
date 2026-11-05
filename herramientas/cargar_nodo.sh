#!/usr/bin/env bash
# Carga firmware/nodo_asistivo en el ESP32 (Linux; en Windows/Mac usar el Arduino IDE).
# Antes de compilar pone en config.h la IP actual de la laptop (MQTT_HOST): la del hotspot cambia.
#   herramientas/cargar_nodo.sh                 → detecta el puerto (/dev/ttyUSB* o /dev/ttyACM*)
#   herramientas/cargar_nodo.sh /dev/ttyUSB1    → puerto a mano
#   herramientas/cargar_nodo.sh --solo-compilar → sin ESP32 conectado
# Necesita: arduino-cli (o el que trae el Arduino IDE), core esp32 y las librerías del README (sección 6).
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
SK="$RAIZ/firmware/nodo_asistivo"
CLI="$(command -v arduino-cli || echo /opt/arduino-ide/resources/app/lib/backend/resources/arduino-cli)"
FQBN="esp32:esp32:esp32:PartitionScheme=huge_app,UploadSpeed=460800"   # a 921600 el USB se caía

if [ ! -f "$SK/config.h" ]; then
  cp "$SK/config.example.h" "$SK/config.h"
  echo "Se creó $SK/config.h: completar WIFI_SSID, WIFI_PASS y PARLANTE, y volver a correr." >&2
  exit 1
fi
if grep -q '"TU_RED"' "$SK/config.h"; then
  echo "Falta completar WIFI_SSID y WIFI_PASS en $SK/config.h" >&2; exit 1
fi

IP="$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' || true)"
if [ -z "$IP" ]; then echo "La laptop no tiene red: conectarla al hotspot primero" >&2; exit 1; fi
sed -i "s|^#define MQTT_HOST .*|#define MQTT_HOST  \"$IP\"          // IP de la laptop (la pone cargar_nodo.sh)|" "$SK/config.h"
RED="$(grep -oP '^#define WIFI_SSID\s+"\K[^"]+' "$SK/config.h")"
echo "Broker: $IP · red del ESP32: $RED"
ACTUAL="$(nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep -oP '^(sí|yes):\K.*' || true)"
if [ -n "$ACTUAL" ] && [ "$ACTUAL" != "$RED" ]; then
  echo "AVISO: la laptop está en \"$ACTUAL\" y el ESP32 se conectará a \"$RED\": deben estar en la misma red" >&2
fi
if command -v firewall-cmd >/dev/null && ! firewall-cmd --query-port=1883/tcp >/dev/null 2>&1; then
  echo "AVISO: el firewall no deja pasar el 1883. Abrirlo: sudo firewall-cmd --permanent --add-port=1883/tcp && sudo firewall-cmd --reload" >&2
fi

if [ "${1:-}" = "--solo-compilar" ]; then
  "$CLI" compile --fqbn "$FQBN" "$SK"
  exit 0
fi
PUERTO="${1:-$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1 || true)}"
if [ -z "$PUERTO" ]; then echo "No se ve el ESP32: conectar el USB (o indicar el puerto)" >&2; exit 1; fi
echo "Cargando en $PUERTO…"
"$CLI" compile --fqbn "$FQBN" -u -p "$PUERTO" "$SK"
echo "Listo. Monitor serie: \"$CLI\" monitor -p $PUERTO -c baudrate=115200"
