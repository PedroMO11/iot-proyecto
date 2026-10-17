# Mide la latencia MQTT ida y vuelta (laptop -> ESP32 -> laptop)
import time
import paho.mqtt.client as mqtt

BROKER = "localhost"
N = 30
rtts = []


def al_recibir(cliente, datos, msg):
    rtt = (time.time() - float(msg.payload.decode())) * 1000
    rtts.append(rtt)
    print(f"ida y vuelta: {rtt:.0f} ms")


c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.on_message = al_recibir
c.connect(BROKER, 1883)
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
