# Simula el ESP32 (nodo1) para desarrollar la interfaz y el dashboard sin hardware.
# Respeta el contrato MQTT del README: LWT/estado, vitales cada 1 s, ping→pong, cmd,
# y eventos de EMG e IMU que se escriben por teclado:
#   a / d / w / s  → imu/evento izq / der / arriba / abajo
#   c              → emg/evento confirmar        x → cancelar
#   n              → sin dedo / con dedo         q → salir
# Uso:  uv run laptop/pruebas/simulador_nodo.py [--broker localhost] [--puerto 1883]
import argparse
import json
import math
import random
import sys
import threading
import time

import paho.mqtt.client as mqtt

FRASES = {1: "Tengo hambre", 2: "Hola", 3: "Tengo sed", 4: "Enciende la luz",
          5: "Llamar al cuidador", 6: "Siento dolor"}
TECLAS_IMU = {"a": "izq", "d": "der", "w": "arriba", "s": "abajo"}

sys.stdout.reconfigure(encoding="utf-8")     # en Windows, con la salida redirigida, cp1252 no tiene ♪ ni «»

p = argparse.ArgumentParser()
p.add_argument("--broker", default="localhost")
p.add_argument("--puerto", type=int, default=1883)
p.add_argument("--nodo", default="asistivo/nodo1")
args = p.parse_args()
N = args.nodo

estado = {"dedo": True, "luz": False, "inicio": time.time()}


def millis():
    return int((time.time() - estado["inicio"]) * 1000)


def publicar_actuadores(c):
    c.publish(f"{N}/actuadores", json.dumps({"luz": estado["luz"]}), qos=1, retain=True)


def al_conectar(c, datos, flags, rc, props=None):
    print(f"[sim] conectado al broker {args.broker} (rc={rc})")
    c.publish(f"{N}/estado", "online", qos=1, retain=True)
    c.subscribe([(f"{N}/cmd", 1), (f"{N}/ping", 0)])
    publicar_actuadores(c)


def al_recibir(c, datos, msg):
    texto = msg.payload.decode(errors="replace")
    if msg.topic.endswith("/ping"):              # eco con un retardo parecido al de la prueba B
        retardo = random.uniform(0.03, 0.15)
        threading.Timer(retardo, lambda: c.publish(f"{N}/pong", texto)).start()
        return
    try:
        cmd = json.loads(texto)
    except json.JSONDecodeError:
        print(f"[sim] cmd inválido: {texto}")
        return
    accion = cmd.get("accion")
    if accion == "frase":
        n = cmd.get("id")
        print(f"[sim] ♪ suena la frase {n}: «{FRASES.get(n, '?')}»")
        if n == 4:
            accion = "luz"
        elif n == 5:
            accion = "alerta"
    if accion == "luz":
        estado["luz"] = not estado["luz"]
        print(f"[sim] relé → luz {'ENCENDIDA' if estado['luz'] else 'apagada'}")
        publicar_actuadores(c)
    elif accion == "alerta":
        print("[sim] buzzer 2 s (llamar al cuidador)")


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="esp32-nodo1-sim")
c.will_set(f"{N}/estado", "offline", qos=1, retain=True)
c.on_connect = al_conectar
c.on_message = al_recibir
c.connect(args.broker, args.puerto, keepalive=5)
c.loop_start()


def vitales():
    while True:
        t = time.time()
        if estado["dedo"]:
            bpm = round(76 + 5 * math.sin(t / 25) + random.gauss(0, 1.5))
            spo2 = min(100, round(98 + random.gauss(0, 0.6)))
        else:
            bpm = spo2 = None
        c.publish(f"{N}/vitales", json.dumps({"bpm": bpm, "spo2": spo2, "ts": millis()}))
        time.sleep(1)


threading.Thread(target=vitales, daemon=True).start()
print("[sim] a/d/w/s = cabeza · c = confirmar · x = cancelar · n = dedo · q = salir (Enter tras cada tecla)")
try:
    while True:
        for tecla in input().strip().lower():
            if tecla in TECLAS_IMU:
                c.publish(f"{N}/imu/evento", json.dumps({"dir": TECLAS_IMU[tecla]}), qos=1)
            elif tecla in "cx":
                tipo = "confirmar" if tecla == "c" else "cancelar"
                c.publish(f"{N}/emg/evento", json.dumps({"tipo": tipo, "ts": millis()}), qos=1)
            elif tecla == "n":
                estado["dedo"] = not estado["dedo"]
                print(f"[sim] dedo {'puesto' if estado['dedo'] else 'retirado'}")
            elif tecla == "q":
                raise KeyboardInterrupt
except (KeyboardInterrupt, EOFError):
    c.publish(f"{N}/estado", "offline", qos=1, retain=True).wait_for_publish(2)
    c.loop_stop()
    c.disconnect()
