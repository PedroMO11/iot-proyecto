# Sistema IoT de comunicación asistiva mediante gestos y mirada

Proyecto del curso **CS5055 Internet of Things** (UTEC, 2026-2), grupo de 4 integrantes.

Este documento resume el proyecto y los pasos para avanzar con el código. Si es tu primera vez en el repositorio, léelo completo antes de empezar.

---

## 1. Qué estamos construyendo

Un prototipo de bajo costo para que una persona con movilidad reducida severa y sin habla (por ejemplo, con ELA o secuelas de ACV) pueda:

1. **Elegir una de 6 frases** en pantalla moviendo la **mirada** o **inclinando la cabeza**.
2. **Confirmar** la frase **apretando la mandíbula**. Si la mantiene apretada más de 1 s, **cancela**.
3. Escuchar la frase por un **parlante Bluetooth**, encender una **luz** o activar un **buzzer** para llamar al cuidador.
4. Mostrarle al cuidador su **pulso y SpO₂** en un dashboard, con alerta si salen de rango.

**Menú de frases (cuadrícula de 2 × 3):**

| ID | Frase | Acción adicional |
|---|---|---|
| 1 | Tengo hambre | — |
| 2 | Hola | — |
| 3 | Tengo sed | — |
| 4 | Enciende la luz | Conmuta el relé (foco LED 12 V) |
| 5 | Llamar al cuidador | Activa el buzzer |
| 6 | Siento dolor | — |

**Prioridad indicada por el profesor:** primero el núcleo IoT, es decir, el ESP32 leyendo los sensores, MQTT funcionando y los actuadores respondiendo. La visión y el dashboard van después.

---

## 2. Arquitectura

```
 USUARIO                      NODO ESP32-WROOM-32                 ACTUADORES
 ───────                      ───────────────────                 ──────────
 Sensor EMG (masetero) ──ADC1 GPIO34──┐                    ┌──Bluetooth A2DP──> Parlante BT
 MPU6050 (vincha)      ──I2C 0x68─────┤  Adquisición y     ├──GPIO26──> Relé ──> Foco LED 12 V
 MAX30102 (dedo)       ──I2C 0x57─────┘  procesamiento     └──GPIO27──> 2N2222 ──> Buzzer
                                               │
                                        WiFi 2,4 GHz (MQTT)
                                               │
 LAPTOP ───────────────────────────────────────┴──────────────────────────────
   Broker Mosquitto  <──>  Interfaz de menú (Python)  <──  Módulo de visión (MediaPipe + webcam)
                     <──>  Dashboard (métricas y pulso)
```

- **Capa de percepción:** EMG, MPU6050, MAX30102 y la webcam de la laptop. Ojo: la webcam **no** cuenta como sensor IoT; los 3 sensores físicos están en el ESP32.
- **Capa de red:** WiFi con MQTT entre el ESP32 y el broker Mosquitto en la laptop, más Bluetooth A2DP entre el ESP32 y el parlante.
- **Capa de aplicación:** módulo de visión, interfaz de menú y dashboard, todos en la laptop.

---

## 3. Hardware

| Componente | Función | Notas |
|---|---|---|
| ESP32 DevKit V1 (ESP32-WROOM-32) | Nodo central | Tiene WiFi y Bluetooth **Classic**. **No** sirven el S2, S3 ni C3 porque solo tienen BLE, que no transmite audio A2DP. |
| Sensor EMG + cable de 3 electrodos | Confirmar y cancelar | Ver la sección 3.1 |
| MPU6050 (GY-521) | Navegación con la cabeza | I2C 0x68 |
| MAX30102 | Pulso y SpO₂ | I2C 0x57. Lecturas referenciales; no es un dispositivo médico. |
| Parlante Bluetooth | Voz | Cualquiera que acepte A2DP |
| Relé 1 canal optoacoplado (bobina 5 V) | Foco LED 12 V | Se activa con 3,3 V |
| Buzzer activo 5 V + transistor 2N2222 | Alerta al cuidador | |
| Laptop | Broker, visión, menú, dashboard | |

### 3.1 Sensor EMG: dos opciones posibles

La versión final depende de cuál se compre. El firmware debe tener un `#define` para elegir entre las dos.

| | **Opción A: Muscle Sensor (AliExpress, placa roja)** | **Opción B: DFRobot Gravity OYMotion SEN0240** |
|---|---|---|
| Alimentación | ±9 V con 2 baterías de 9 V | 3,3–5 V desde el ESP32 |
| Salida | **Envolvente** ya rectificada y suavizada, de 0 a +Vs | Señal EMG **amplificada y filtrada, sin rectificar**, de 0 a 3 V (centrada en unos 1,5 V) |
| Conexión al ESP32 | Pasa por un **divisor 20 kΩ / 10 kΩ** (salida a 1/3) antes del GPIO34 | Directo al GPIO34 |
| Muestreo | 500 Hz | 1 kHz (lo recomienda el fabricante) |
| Procesamiento en el ESP32 | Media móvil y umbral | Restar el nivel medio, valor absoluto, media móvil y umbral |
| Electrodos | Desechables Ag/AgCl (cambiar en cada sesión) | Secos de metal, reutilizables |

**En las dos opciones, el GND del sensor va al GND del ESP32.**

Conexión de baterías en la opción A: el + de la batería 1 va a +Vs; el − de la batería 1 y el + de la batería 2 van juntos a GND; el − de la batería 2 va a −Vs.

### 3.2 Asignación de pines

| Pin ESP32 | Conexión |
|---|---|
| GPIO34 (ADC1) | Salida del EMG (por el divisor en la opción A) |
| GPIO21 (SDA) / GPIO22 (SCL) | Bus I2C compartido por el MPU6050 y el MAX30102 |
| GPIO26 | Entrada IN del relé |
| GPIO27 | Base del 2N2222 del buzzer (con resistencia de unos 1 kΩ) |
| VIN (5 V del USB) | VCC del relé y del buzzer |
| 3V3 | VCC del MPU6050 y del MAX30102 (y del EMG en la opción B) |
| GND | Tierra común para **todo** |

> Usar solo pines **ADC1** (GPIO32–39) para lecturas analógicas. Los ADC2 dejan de funcionar cuando el WiFi está activo.
> Los GPIO trabajan a 3,3 V. **Nunca** conectar 5 V ni 9 V a un GPIO.

---

## 4. Contrato MQTT

Todo el equipo debe respetar estos topics y formatos, para que cada parte pueda desarrollarse por separado.

| Topic | Publica | Se suscribe | QoS | Payload (JSON) |
|---|---|---|---|---|
| `asistivo/nodo1/emg/evento` | ESP32 | Interfaz | 1 | `{"tipo":"confirmar","ts":123456}` o `{"tipo":"cancelar","ts":...}` |
| `asistivo/nodo1/imu/evento` | ESP32 | Interfaz | 1 | `{"dir":"izq"}`, con `dir` = `izq`, `der`, `arriba` o `abajo` |
| `asistivo/nodo1/vitales` | ESP32 | Dashboard | 0 | `{"bpm":72,"spo2":98,"ts":...}`, cada 1 s |
| `asistivo/nodo1/cmd` | Interfaz | ESP32 | 1 | `{"accion":"frase","id":3}`, `{"accion":"luz","estado":"toggle"}` o `{"accion":"alerta"}` |
| `asistivo/nodo1/estado` | ESP32 (LWT) | Interfaz, dashboard | 1, retenido | `"online"` / `"offline"` |
| `asistivo/nodo1/ping` → `pong` | Dashboard → ESP32 | Dashboard | 0 | El ESP32 devuelve en `pong` el mismo texto que recibe en `ping` (ya lo hace `02b`). El dashboard mide así la latencia cada 2 s |
| `asistivo/nodo1/actuadores` | ESP32 | Dashboard | 1, retenido | `{"luz":true}` *(opcional: estado del relé)* |
| `asistivo/vision/mirada` | Visión | Interfaz | 0 | `{"region":4}` (1–6), o `{"region":null}` si no hay cara |
| `asistivo/vision/punto` | Visión | Interfaz | 0 | `{"x":0.42,"y":0.71}` (0–1, relativos a la zona del menú), ~20 por segundo; `{"x":null}` sin cara |
| `asistivo/vision/estado` | Visión | Dashboard | 0 | `{"fps":30,"cara":true,"calibrado":true,"region":4}`, cada 2 s |
| `asistivo/vision/cmd` | Interfaz | Visión | 1 | `{"accion":"calibrar"}` o `{"accion":"centrar"}` |
| `asistivo/vision/calibracion` | Visión | Interfaz, dashboard | 1 | `{"estado":"mirar","region":3}`, `"listo"`, `"centrar"`, `"centrado"` o `{"estado":"error","faltan":[2]}` |
| `asistivo/interfaz/estado` | Interfaz | Dashboard | 1, retenido | `{"modo":"uso"}`, con `modo` = `uso`, `prueba` o `reposo` |
| `asistivo/interfaz/seleccion` | Interfaz | Dashboard | 1 | `{"modo":"prueba","id":3,"frase":"Tengo sed","via":"emg","enviado":true,"objetivo":3,"acierto":true,"t_seleccion_ms":2300,"ts":...}` |

- `ts` = `millis()` del ESP32. Sirve para medir la latencia.
- El ESP32 registra el Last Will (LWT) `"offline"` al conectarse y publica `"online"` apenas conecta.
- Para revisar todo el tráfico desde la laptop: `mosquitto_sub -h localhost -t "asistivo/#" -v`
- **Pendiente en `nodo_asistivo`:** responder `ping` → `pong` y publicar `actuadores` (sin `pong`, el dashboard muestra *"el nodo no responde al ping"*).
- `ts` de la interfaz es la hora de la laptop (`Date.now()`), no `millis()`.

---

## 5. Estructura del repositorio

```
/
├── README.md                  ← este documento
├── CHECKLIST_ARMADO.md        ← pruebas paso a paso con casillas y registro de resultados
├── COMPRAS.md                 ← lo que falta comprar (transistores, carga del relé, cables)
├── .gitignore                 ← excluye config.h, .venv, __pycache__ y .pio
├── firmware/                  ← código del ESP32 (Arduino IDE o PlatformIO)
│   ├── pruebas/               ← sketches pequeños, uno por paso (ver sección 7 y CHECKLIST_ARMADO.md)
│   │   ├── 01_mqtt_basico/
│   │   ├── 02a_a2dp_solo/
│   │   ├── 02b_coexistencia/
│   │   ├── 03_escaner_i2c/
│   │   ├── 03a_mpu6050/
│   │   ├── 03b_max30102/      ← pulso y SpO₂ (algoritmo de Maxim adaptado al ESP32)
│   │   ├── 03c_emg_senal/
│   │   ├── 03c_emg_eventos/
│   │   ├── 04a_rele/
│   │   └── 04b_buzzer/
│   └── nodo_asistivo/         ← firmware final integrado
│       ├── nodo_asistivo.ino
│       ├── config.example.h   ← plantilla (sí se sube)
│       └── config.h           ← WiFi, IP del broker (NO se sube, está en .gitignore)
├── audios/                    ← las 6 frases (.m4a, .wav y frases.h generado)
├── herramientas/
│   └── wav_a_header.py        ← convierte los .wav en frases.h
├── laptop/
│   ├── mosquitto.conf
│   ├── requirements.txt
│   ├── pruebas/               ← latencia_mqtt.py, simulador_nodo.py (ESP32 simulado)
│   ├── web/                   ← cliente MQTT por WebSocket y configuración (compartidos)
│   ├── vision/                ← MediaPipe: mirada → región 1..6
│   └── interfaz/              ← menú 2×3 del paciente (página web)
├── dashboard/                 ← panel del cuidador: signos vitales y métricas (página web)
└── docs/                      ← informe, diagramas, fotos de pruebas
```

---

## 6. Preparar el entorno

### ESP32
1. Instalar **Arduino IDE 2**.
2. En *Preferencias → URLs adicionales del gestor de placas* agregar:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`
3. *Gestor de placas* → instalar **esp32** (de Espressif Systems).
4. Placa: **ESP32 Dev Module**. **Partition Scheme: "Huge APP (3MB No OTA)"**, porque A2DP y los audios ocupan mucha flash.
5. Librerías (*Gestor de librerías* o GitHub):
   - `PubSubClient` (Nick O'Leary): MQTT
   - `ArduinoJson` (Benoit Blanchon, versión 7): JSON
   - `ESP32-A2DP` (Phil Schatzmann): audio Bluetooth. No está en el gestor: descargar el ZIP de https://github.com/pschatzmann/ESP32-A2DP y añadirlo con *Sketch → Include Library → Add .ZIP Library*.
   - ~~`Adafruit MPU6050`~~: ya no hace falta. Nuestro GY-521 es un clon (`WHO_AM_I = 0x74`) que la librería rechaza; `03a_mpu6050` lee los registros directamente
   - `SparkFun MAX3010x Pulse and Proximity Sensor Library`

### Laptop
1. Instalar **Mosquitto** (https://mosquitto.org/download/) y arrancarlo con la configuración del repositorio. Abre el **1883** (MQTT por TCP, para el ESP32) y el **9001** (MQTT por WebSocket, para la interfaz y el dashboard):
   ```
   mosquitto -c laptop/mosquitto.conf -v
   ```
   En Windows, permitir Mosquitto en el firewall (red privada) si el ESP32 no logra conectarse. En Linux con firewalld: `sudo firewall-cmd --zone=public --add-port=1883/tcp`.
2. Python 3.10 o superior (en Linux, activar el entorno con `source .venv/bin/activate` o usar `.venv/bin/python`):
   ```
   python -m venv .venv
   pip install -r laptop/requirements.txt
   ```
3. **ffmpeg**, para convertir los audios: `winget install ffmpeg` (Windows) o `brew install ffmpeg` (Mac).

### Red
Usar un **hotspot del celular o un router propio**: el WiFi de la universidad suele bloquear el tráfico entre dispositivos. La laptop y el ESP32 deben estar en la misma red. La IP de la laptop va en `config.h`.

---

## 7. Pasos a seguir

Cada paso tiene un **criterio de "listo"**. No pasar al siguiente hasta cumplirlo. Subir cada prueba a `firmware/pruebas/` con un commit que diga qué funcionó.

Los pasos 1 a 4 se ejecutan con el [CHECKLIST_ARMADO.md](CHECKLIST_ARMADO.md), que tiene el cableado, las casillas y la tabla de resultados de cada prueba.

### Paso 1: ESP32 + WiFi + MQTT
Sketch: [firmware/pruebas/01_mqtt_basico/](firmware/pruebas/01_mqtt_basico/01_mqtt_basico.ino).
- El ESP32 se conecta al WiFi y al broker, registra el LWT y publica `"online"` en `asistivo/nodo1/estado`.
- Publica un JSON de prueba cada segundo en `asistivo/nodo1/vitales`.
- Se suscribe a `asistivo/nodo1/cmd` e imprime en el Monitor Serie lo que recibe.
- Se reconecta solo si se cae el WiFi o el broker.

✅ **Listo cuando:** `mosquitto_sub` muestra los mensajes del ESP32; al hacer `mosquitto_pub -t asistivo/nodo1/cmd -m '{"accion":"alerta"}'` el ESP32 lo imprime; al desconectar el ESP32 aparece `"offline"`.

### Paso 2: Bluetooth A2DP y prueba de coexistencia ⚠️ (el riesgo más alto)
Checklist: [grabar los audios](CHECKLIST_ARMADO.md#1-grabar-y-preparar-los-audios), [prueba A](CHECKLIST_ARMADO.md#2-prueba-a-bluetooth-a2dp-solo) y [prueba B](CHECKLIST_ARMADO.md#3-prueba-b-wifi--mqtt--bluetooth-a-la-vez-coexistencia).
- Convertir las frases a PCM de 16 kHz, mono y 16 bits, y guardarlas como arrays en `frases.h` con [herramientas/wav_a_header.py](herramientas/wav_a_header.py).
- Con `ESP32-A2DP` (modo *source*), emparejar con el parlante y reproducir la frase. A2DP trabaja a 44,1 kHz estéreo, así que hay que remuestrear al enviar (repetir muestras y duplicar el canal).
- **Prueba clave:** WiFi + MQTT activos **al mismo tiempo** que Bluetooth. Mandar comandos `cmd` mientras suena el audio y anotar:
  - si el audio se corta,
  - si se cae el WiFi o el MQTT,
  - la latencia de MQTT con y sin audio (con el `ts`).

✅ **Listo cuando:** suena la frase al recibir `{"accion":"frase","id":1}` y MQTT sigue funcionando durante y después del audio. Anotar los resultados en `docs/`.

❌ **Plan B si falla la coexistencia:** la laptop reproduce el audio por su propio Bluetooth y el ESP32 queda solo con MQTT, relé y buzzer. **Avisar al grupo antes de seguir**, porque cambia la arquitectura.

### Paso 3: Sensores, uno por uno
Checklist: [sección 4](CHECKLIST_ARMADO.md#4-sensores).

Antes de nada, correr el **escáner I2C** ([03_escaner_i2c](firmware/pruebas/03_escaner_i2c/03_escaner_i2c.ino)): deben aparecer **0x68** (MPU6050) y **0x57** (MAX30102).

**3a. MPU6050**
- Leer el acelerómetro y el giroscopio a 100 Hz.
- Filtro complementario: `θ = 0.98·(θ + ω·Δt) + 0.02·θ_acc`, con Δt = 10 ms.
- Detectar inclinaciones a izquierda, derecha, arriba y abajo con umbrales configurables (empezar con unos 15°, **no** 45°). Agregar histéresis y un tiempo mínimo para no generar eventos repetidos.
- ✅ Inclinar la cabeza genera **un** evento `imu/evento` por movimiento.

**3b. MAX30102**
- Usar los ejemplos de la librería SparkFun para BPM y SpO₂.
- Publicar en `vitales` cada 1 s. Si no hay dedo, no publicar o mandar `null`.
- ✅ Con el dedo puesto, el BPM es estable y razonable (se puede comparar con un oxímetro o un reloj).

**3c. EMG**
- Leer el GPIO34 y graficar en el **Serial Plotter**, comparando la mandíbula relajada con la mandíbula apretada.
- Algoritmo:
  1. *(Solo opción B)* restar el nivel medio y tomar el valor absoluto.
  2. Media móvil de 50 ms.
  3. **Calibración al inicio:** 5 s en reposo → calcular la media μ y la desviación σ. Umbral = **μ + 3σ**.
  4. **Confirmar** = la señal supera el umbral entre **100 ms y 1 s**.
  5. **Cancelar** = la señal supera el umbral **más de 1 s**.
  6. **Periodo refractario de 700 ms** después de cada evento.
- ✅ Apretar la mandíbula da un `confirmar`; mantenerla da un `cancelar`; hablar o tragar no dispara eventos, o casi nunca.

### Paso 4: Actuadores
Checklist: [sección 5](CHECKLIST_ARMADO.md#5-actuadores).
- Al recibir `{"accion":"luz","estado":"toggle"}` → conmutar el relé en GPIO26. **Probar primero con un LED** y dejar el foco de 12 V para el final.
- Al recibir `{"accion":"alerta"}` → buzzer en GPIO27 por 2 s.
- Al recibir `{"accion":"frase","id":N}` → reproducir la frase N. Si N = 4, además conmutar la luz; si N = 5, además activar el buzzer.
- ✅ Los tres comandos funcionan desde `mosquitto_pub`.

> **Con los pasos 1 a 4 terminados, el núcleo IoT está completo.**

### Paso 5: Integración del firmware
- Unir todo en `firmware/nodo_asistivo/`.
- Usar **FreeRTOS** con dos núcleos: **núcleo 1** para la adquisición de sensores (EMG, IMU, MAX30102) y **núcleo 0** para WiFi, MQTT y A2DP. Pasar los eventos entre tareas con colas (`xQueueSend` / `xQueueReceive`).
- Evitar `delay()` en el loop de sensores; usar temporización con `millis()` o `vTaskDelayUntil`.

### Paso 6: Laptop (en paralelo, no necesita hardware)
- **`laptop/vision/`** ✅: `mirada.py` (cámara, MQTT y ventana de diagnóstico) + `modelo.py` (rasgos y modelo) + `evaluar_calibracion.py` (análisis para el informe). Webcam a **1280×720 y 30 fps** + **MediaPipe Face Landmarker** (`mp.solutions`/Face Mesh ya no existe en mediapipe 1.x).
  - **Rasgos (20):** iris de cada ojo respecto de sus comisuras, en píxeles reales y corregido por el alabeo de la cabeza; apertura de los párpados; 8 *blendshapes* de mirada; **pose 3D de la cabeza** (giro, cabeceo, alabeo y posición en cm, de la matriz de transformación de MediaPipe).
  - **Calibración** (tecla **C**): 10 puntos (rejilla de 3 × 3 con el **centro y los bordes**, y el centro repetido al final para medir la deriva). El programa prueba 48 variantes (conjuntos de rasgos, 1.er/2.º orden y regularización) y elige la de menor error con **validación cruzada dejando fuera un punto entero**, es decir, acertando en lugares no calibrados.
  - **Comprobación** (automática tras calibrar, o tecla **K**): 6 puntos en los centros de casilla; informa el **% de casillas acertadas** y el error (en la interfaz, el dashboard y `calibracion.json`). Primera prueba con buena luz (2026-10-30): **100 % de casillas, error de 3,5 % (x) y 4,0 % (y)**.
  - **Recentrado** (tecla **O**): mirar 1 s el centro corrige el desvío si la persona se movió.
  - **En uso:** filtro **One Euro** (poco temblor en reposo, poca demora al moverse) e **histéresis** en los bordes (para cambiar de casilla hay que entrar un 4 % en ella y quedarse 0,25 s). Se descartan parpadeos y caras de lado (> 35°).
  - **Cámara (Linux):** al arrancar pone el antiparpadeo en **60 Hz** (venía en 50 Hz, y con la red de Perú salen bandas) y fija los 30 fps (con poca luz caía a 10). Con poca luz la ventana muestra "POCA LUZ" y no se detecta la cara: iluminar la cara de frente.
  - `calibracion.json` (personal) y el modelo `face_landmarker.task` (3,7 MB, se descarga solo) no se suben.
- **`laptop/interfaz/`** ✅: menú 2 × 3 a pantalla completa (página web). El cursor se mueve con `imu/evento` (una casilla), con `vision/mirada` (región directa) o con el teclado; `emg/evento` confirma o cancela; al confirmar publica en `cmd` y en `interfaz/seleccion`. Tras confirmar ignora confirmaciones durante 1,5 s. Tres modos (tecla **M**):
  - **uso:** normal;
  - **prueba:** marca un objetivo al azar y registra acierto o error y el tiempo de selección;
  - **reposo:** no envía frases; cada confirmación del EMG cuenta como activación accidental.
- **`dashboard/`** ✅: suscrito a `asistivo/#`. No solo muestra: calcula las métricas con meta, en verde o rojo:
  - pulso y SpO₂ (promedio de 10 s) con alerta fuera de rango (50–120 BPM, SpO₂ < 92 %; referencial),
  - tasa de aciertos en modo prueba (meta ≥ 90 %),
  - tiempo de selección, mediana (meta ≤ 5 s),
  - activaciones accidentales por cada 5 min en reposo (meta ≤ 1),
  - latencia MQTT de ida por ping/pong, mediana y p90 (meta < 300 ms),
  - disponibilidad del nodo (% en línea y desconexiones).

  Gráficos de signos vitales y latencia de los últimos 5 min, registro de eventos y botón **Exportar CSV** para las figuras del informe.

**Cómo correrlo:**
1. `mosquitto -c laptop/mosquitto.conf -v`
2. Abrir en el navegador `laptop/interfaz/index.html` (tecla **F**: pantalla completa) y `dashboard/index.html`. Funcionan sin internet: no usan librerías externas.
3. **Mirada:** `.venv/bin/python laptop/vision/mirada.py` (abre una ventana de diagnóstico con la cámara, los ojos ampliados y un minimapa; `--sin-ventana` para ocultarla). En la interfaz: **C** calibra, **K** comprueba la precisión, **O** recentra, **V** activa o desactiva la mirada. Para el informe: `.venv/bin/python laptop/vision/evaluar_calibracion.py figura.png`.
4. **Sin el ESP32:** `.venv/bin/python laptop/pruebas/simulador_nodo.py` publica vitales, responde ping y ejecuta los comandos. Por teclado: `a/d/w/s` = cabeza, `c` = confirmar, `x` = cancelar, `n` = sin dedo (Enter tras cada tecla).
5. **Dashboard desde otro equipo o un celular** en la misma red: en la laptop, `python -m http.server 8000` desde la raíz del repo, y abrir `http://<IP-de-la-laptop>:8000/dashboard/?broker=ws://<IP-de-la-laptop>:9001` (abrir también los puertos 8000 y 9001 en el firewall).

### Paso 7: Enclosure y montaje
Carcasa del nodo (impresa en 3D o reciclada), vincha para el MPU6050 y el electrodo EMG, y soporte para el MAX30102 en el dedo.

---

## 8. Reglas de trabajo en el repositorio

- **Nunca subir `config.h`** (tiene la contraseña del WiFi). Subir solo `config.example.h`.
- Una rama por tarea (`paso1-mqtt`, `vision-mediapipe`, …) y *pull request* a `main`.
- Mensajes de commit claros: `firmware: MQTT con reconexión y LWT funcionando`.
- Cada prueba guarda una nota corta en `docs/` (qué se probó, resultado, foto o captura). Sirve para el informe final.
- Ante cualquier cambio de pines, topics o formato JSON, **actualizar este README** y avisar al grupo.

---

## 9. Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| WiFi y Bluetooth comparten la misma radio de 2,4 GHz | Probarlo en el paso 2, medir la latencia y tener listo el plan B |
| Activaciones accidentales del EMG | Calibración por sesión, duración mínima, periodo refractario y medición en el dashboard |
| La salida del EMG supera los 3,3 V (opción A) | Divisor 20k/10k **siempre** conectado antes del GPIO34 |
| La visión falla con poca luz | Iluminación frontal, distancia de 50–70 cm; la cabeza sirve como entrada alternativa |
| El WiFi de la universidad bloquea MQTT | Hotspot o router propio |
