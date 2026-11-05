#!/usr/bin/env bash
# Arranca el lado de la laptop para probar el sistema (Linux): broker, interfaz y dashboard.
#   laptop/iniciar.sh               → broker + interfaz + dashboard
#   laptop/iniciar.sh --vision      → además la mirada (MediaPipe)
#   laptop/iniciar.sh --simulador   → además el ESP32 simulado (teclas en esta terminal), sin hardware
# Ctrl+C detiene todo lo que arrancó este script.
set -uo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
if command -v uv >/dev/null; then PY=(uv run --project "$RAIZ"); else PY=("$RAIZ/.venv/bin/python"); fi
VISION=0; SIMULADOR=0
for a in "$@"; do
  case "$a" in
    --vision) VISION=1 ;;
    --simulador) SIMULADOR=1 ;;
    *) echo "Opción desconocida: $a" >&2; exit 1 ;;
  esac
done

PIDS=()
terminar() { for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done; echo; echo "Detenido."; }
trap terminar EXIT

IP="$(ip -4 route get 1.1.1.1 2>/dev/null | grep -oP 'src \K[0-9.]+' || echo "sin red")"
RED="$(nmcli -t -f ACTIVE,SSID dev wifi 2>/dev/null | grep -oP '^(sí|yes):\K.*' || echo "?")"
echo "Laptop: $IP en \"$RED\" (MQTT_HOST del ESP32: herramientas/cargar_nodo.sh la pone sola)"
if command -v firewall-cmd >/dev/null && ! firewall-cmd --query-port=1883/tcp >/dev/null 2>&1; then
  echo "AVISO: el firewall no deja pasar el 1883 y el ESP32 no podrá conectarse."
  echo "       sudo firewall-cmd --permanent --add-port=1883/tcp && sudo firewall-cmd --reload"
fi

if ss -ltn | grep -q ':9001 '; then
  echo "Broker: ya estaba corriendo"
else
  mosquitto -c "$RAIZ/laptop/mosquitto.conf" > /tmp/mosquitto_asistivo.log 2>&1 &
  PIDS+=($!); sleep 0.5
  echo "Broker: iniciado (registro en /tmp/mosquitto_asistivo.log)"
fi

xdg-open "file://$RAIZ/laptop/interfaz/index.html" >/dev/null 2>&1
xdg-open "file://$RAIZ/laptop/dashboard/index.html" >/dev/null 2>&1
echo "Abiertas la interfaz (paciente) y el dashboard (cuidador)"

if [ "$VISION" = 1 ]; then
  (cd "$RAIZ/laptop/vision" && exec "${PY[@]}" mirada.py) &
  PIDS+=($!)
  echo "Visión: iniciada (en la interfaz: C calibra, K comprueba, O recentra)"
fi

echo "Para ver todo el tráfico: mosquitto_sub -t 'asistivo/#' -v"
if [ "$SIMULADOR" = 1 ]; then
  echo "Simulador: a/d/w/s cabeza · c confirmar · x cancelar · n dedo · q salir (Enter tras cada tecla)"
  "${PY[@]}" "$RAIZ/laptop/pruebas/simulador_nodo.py"
else
  echo "Corriendo. Ctrl+C para detener."
  while true; do sleep 60; done
fi
