# Enciende y apaga el foco por MQTT y confirma que el nodo realmente respondió.
# Uso:  uv run laptop/pruebas/foco.py on|off|toggle|estado [--broker localhost] [--puerto 1883]
# Sale con código 1 si el nodo no responde a tiempo.
import argparse
import json
import sys
import threading

import paho.mqtt.client as mqtt

sys.stdout.reconfigure(encoding="utf-8")     # en Windows, con la salida redirigida, cp1252 no tiene todos los acentos

p = argparse.ArgumentParser(description="Controla el foco del nodo por MQTT")
p.add_argument("orden", choices=["on", "off", "toggle", "estado"])
p.add_argument("--broker", default="localhost")
p.add_argument("--puerto", type=int, default=1883)
p.add_argument("--nodo", default="asistivo/nodo1")
p.add_argument("--espera", type=float, default=3.0, help="segundos para esperar la respuesta del nodo")
args = p.parse_args()

T_CMD = f"{args.nodo}/cmd"
T_ESTADO = f"{args.nodo}/estado"
T_ACTUADORES = f"{args.nodo}/actuadores"

listo = threading.Event()


def al_conectar(c, datos, flags, rc, props=None):
    if rc.is_failure:
        print(f"El broker rechazó la conexión: {rc}")
        return
    c.subscribe([(T_ESTADO, 1), (T_ACTUADORES, 1)])


def al_suscribir(c, datos, mid, rc, props=None):
    if args.orden != "estado":
        c.publish(T_CMD, json.dumps({"accion": "luz", "estado": args.orden}), qos=1)


def al_recibir(c, datos, msg):
    if msg.topic == T_ESTADO:
        print(f"Nodo: {msg.payload.decode(errors='replace')}")
        return
    # Al suscribirse llega el último estado retenido: sirve para "estado", pero no es la respuesta a una orden.
    if args.orden == "estado" or not msg.retain:
        print(f"Luz: {'ENCENDIDA' if json.loads(msg.payload)['luz'] else 'apagada'}")
        listo.set()


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_connect = al_conectar
c.on_subscribe = al_suscribir
c.on_message = al_recibir
try:
    c.connect(args.broker, args.puerto, keepalive=10)
except OSError as e:
    sys.exit(f"No se pudo conectar al broker {args.broker}:{args.puerto}: {e}")

c.loop_start()
respondio = listo.wait(args.espera)
c.loop_stop()

if not respondio:
    sys.exit(f"Sin respuesta en {args.espera:g} s: revisar que el nodo esté encendido y conectado al broker")
