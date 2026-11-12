# Lista de compras

Lo que falta para terminar el prototipo. Marcar cada casilla al comprarlo y hacer commit para que el grupo lo vea. Detalles de cada prueba en [CHECKLIST_ARMADO.md](CHECKLIST_ARMADO.md).

## Urgente: actuadores

### Transistores NPN y resistencias: ya no hacen falta
1. **Buzzer:** suena bien directo a D27 (CHECKLIST, sección 5.2). El kit no traía transistor; el que parecía uno es un **LM35DZ** (sensor de temperatura).
2. **Relé:** se reemplazó el JQC3F-05VDC-C por un módulo de 2 canales, con VCC a 5 V e IN directo a D26 (CHECKLIST, sección 5.1).


### Algo que el relé encienda (frase 4: «Enciende la luz»)
- [x] **Foco de 220 V** con su cable y enchufe. Funciona con el relé de 2 canales (2026-11-08).

**Conexión:** el relé corta **un solo conductor** del cable del foco (de preferencia la fase): un extremo a **COM**, el otro a **NO**; el otro conductor queda sin cortar. Cablear siempre con el cable desenchufado y dejar los bornes cubiertos (CHECKLIST, sección 5.1).

## Para la vincha y el dedo

- [ ] **Cable largo de 4 hilos, 50–80 cm**, para el MPU6050 (vincha) y el MAX30102 (dedo). Ideal: un trozo de **cable UTP** (de red), que trae 4 pares trenzados: SDA trenzado con GND y SCL trenzado con 3V3.
- [ ] **Liga, velcro o pinza de dedo** para fijar el dedo sobre el MAX30102. Sin eso, el pulso se pierde al moverse.
- [ ] **Cables dupont hembra-macho** (un paquete) para conectar los módulos sin protoboard. En el protoboard, el MAX30102 se desconectó 3 veces al presionarlo.
- [ ] **Cinta aislante**, para la parte de atrás del MAX30102 (que no haga corto al apretarlo) y para fijar cables.

## Para el enclosure (semana 13)

- [ ] Caja o material reciclado, o impresión 3D, para el nodo (ESP32, relé, buzzer).
- [ ] Vincha o banda elástica para el MPU6050 y el electrodo del EMG.
