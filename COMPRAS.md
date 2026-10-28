# Lista de compras

Lo que falta para terminar el prototipo. Marcar cada casilla al comprarlo y hacer commit para que el grupo lo vea. Detalles de cada prueba en [CHECKLIST_ARMADO.md](CHECKLIST_ARMADO.md).

## Urgente: actuadores

### Transistores NPN y resistencias
- [ ] **3 transistores NPN pequeños** (TO-92): **2N2222A**, PN2222A, S8050, BC547 o 2N3904. Cualquiera sirve; comprar 3 para tener repuesto.
- [ ] **3 resistencias de 1 kΩ** (bandas marrón – negro – rojo).

**Para qué:**
1. **Buzzer:** el ESP32 (D27) no puede encenderlo solo. El transistor conmuta el − del buzzer a GND (CHECKLIST, sección 5.2). El kit no traía transistor; el que parecía uno es un **LM35DZ** (sensor de temperatura).
2. **Relé:** el módulo JQC3F-05VDC-C es activo en LOW y no se apaga con 3,3 V. Ahora funciona provisionalmente con su VCC en 3V3, pero la bobina es de 5 V y queda justa. Con un transistor que lleve IN a GND, el módulo vuelve a 5 V (CHECKLIST, sección 5.1).

> **Ojo con el orden de las patas** (cara plana hacia uno, patas abajo): 2N2222A, PN2222A, S8050 y 2N3904 = **E – B – C**; BC547 = **C – B – E**; C1815 = **E – C – B**. Leer el texto impreso antes de montarlo.

- [ ] *(Opcional)* 1 diodo **1N4148**, en paralelo con el buzzer (raya hacia el +).

### Algo que el relé encienda (frase 4: «Enciende la luz»)
Un relé que solo hace clic no actúa sobre el mundo físico; en la demo tiene que encender algo. **Elegir una opción:**

- [ ] **Opción 1 (recomendada): lámpara o tira LED USB de 5 V** + un **cable de extensión USB** para cortarle solo el cable rojo (+5 V) + un **power bank** o cargador de celular. Barata, segura y se ve bien.
- [ ] **Opción 2: ventilador USB de 5 V** (misma conexión que la opción 1). Encaja como «confort» para el paciente.
- [ ] **Opción 3 (plan original): foco LED de 12 V + adaptador de 12 V** (1 A basta) con su conector o bornera.

**Conexión (cualquier opción):** el relé corta solo el cable **+** de la carga: un extremo a **COM**, el otro a **NO**; el cable − (GND) queda sin cortar. **Nunca usar 220 V.**

## Para la vincha y el dedo

- [ ] **Cable largo de 4 hilos, 50–80 cm**, para el MPU6050 (vincha) y el MAX30102 (dedo). Ideal: un trozo de **cable UTP** (de red), que trae 4 pares trenzados: SDA trenzado con GND y SCL trenzado con 3V3.
- [ ] **Liga, velcro o pinza de dedo** para fijar el dedo sobre el MAX30102. Sin eso, el pulso se pierde al moverse.
- [ ] **Cables dupont hembra-macho** (un paquete) para conectar los módulos sin protoboard. En el protoboard, el MAX30102 se desconectó 3 veces al presionarlo.
- [ ] **Cinta aislante**, para la parte de atrás del MAX30102 (que no haga corto al apretarlo) y para fijar cables.

## Para el enclosure (semana 13)

- [ ] Caja o material reciclado, o impresión 3D, para el nodo (ESP32, relé, buzzer).
- [ ] Vincha o banda elástica para el MPU6050 y el electrodo del EMG.
