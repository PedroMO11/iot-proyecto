# Mide la latencia MQTT ida y vuelta (laptop -> ESP32 -> laptop)
# Uso:  uv run laptop/pruebas/latencia_mqtt.py [--broker localhost] [--puerto 1883] [-n 30]
import argparse
import time
import paho.mqtt.client as mqtt

p = argparse.ArgumentParser()
p.add_argument("--broker", default="localhost")
p.add_argument("--puerto", type=int, default=1883)
p.add_argument("-n", type=int, default=30, help="cantidad de pings, uno por segundo")
args = p.parse_args()
N = args.n
rtts = []


def al_recibir(cliente, datos, msg):
    rtt = (time.time() - float(msg.payload.decode())) * 1000
    rtts.append(rtt)
    print(f"ida y vuelta: {rtt:.0f} ms")


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_message = al_recibir
c.connect(args.broker, args.puerto)
c.subscribe("asistivo/nodo1/pong", qos=1)
c.loop_start()
for _ in range(N):
    c.publish("asistivo/nodo1/ping", str(time.time()), qos=1)
    time.sleep(1)
time.sleep(2)
c.loop_stop()

if rtts:
    print(f"\nRecibidos {len(rtts)}/{N} | promedio {sum(rtts)/len(rtts):.0f} ms | "
          f"máximo {max(rtts):.0f} ms | latencia de ida aprox. {sum(rtts)/len(rtts)/2:.0f} ms")
else:
    print("No llegó ninguna respuesta: revisar IP, red y firewall")
