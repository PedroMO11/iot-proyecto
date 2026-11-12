# Checklist de armado: audio Bluetooth, sensores y actuadores

Guía paso a paso para probar **cada pieza por separado** antes de integrarlas. Marca cada casilla (`- [x]`) al terminarla y haz commit del archivo para que el grupo vea el avance.

El código de cada prueba está en [firmware/pruebas/](firmware/pruebas/) y en [laptop/pruebas/](laptop/pruebas/); aquí solo se enlaza. Pines, contrato MQTT e instalación del entorno están en el [README](README.md).

**Regla de oro:** probar **una sola cosa a la vez**. Si algo falla con todo conectado, es casi imposible saber qué es.

---

## Índice

0. [Preparación](#0-preparación)
1. [Grabar y preparar los audios](#1-grabar-y-preparar-los-audios)
2. [Prueba A: Bluetooth A2DP solo](#2-prueba-a-bluetooth-a2dp-solo)
3. [Prueba B: WiFi + MQTT + Bluetooth a la vez (coexistencia)](#3-prueba-b-wifi--mqtt--bluetooth-a-la-vez-coexistencia)
4. [Sensores](#4-sensores)
5. [Actuadores](#5-actuadores)
6. [Registro de resultados](#6-registro-de-resultados)
7. [Prueba de conjunto: el sistema completo](#7-prueba-de-conjunto-el-sistema-completo)

---

## 0. Preparación

### Seguridad eléctrica (siempre)
- [ ] **Desconectar el USB del ESP32 antes de cablear o mover cables.**
- [ ] Todo comparte **GND común** con el ESP32.
- [ ] Nunca conectar 5 V ni 12 V a un GPIO. Los GPIO del ESP32 son de **3,3 V**.
- [ ] Para el EMG, usar la laptop **desenchufada del cargador** (a batería), porque el cargador mete ruido de 60 Hz.

### Software
Instrucciones en el [README, sección 6](README.md#6-preparar-el-entorno).
- [ ] Arduino IDE 2 con el paquete de placas **esp32** y la placa **ESP32 Dev Module**.
- [ ] **Partition Scheme: "Huge APP (3MB No OTA)"**.
- [ ] Librerías instaladas: `ESP32-A2DP` (ZIP), `PubSubClient`, `ArduinoJson` 7, `SparkFun MAX3010x` (`Adafruit MPU6050` ya no hace falta: ver 4.1).
- [ ] **uv** instalado y `uv sync` corrido en la raíz del repositorio.
- [ ] **ffmpeg** instalado.
- [ ] Mosquitto instalado (se necesita a partir de la prueba B).

### Prueba de vida del ESP32
- [ ] Cargar *File → Examples → 01.Basics → Blink* (en el DevKit V1 el LED azul es el GPIO2: cambiar `LED_BUILTIN` por `2` si no compila).
- [ ] ✅ El LED parpadea. Si no carga, mantener presionado el botón **BOOT** mientras dice "Connecting...".

---

## 1. Grabar y preparar los audios

**Formato final que necesita el ESP32:** WAV **mono, 16 bits, 16 000 Hz**. Cada frase de **máximo 2,5 s**. A 16 kHz y 16 bits cada segundo ocupa 32 KB, así que las 6 frases suman entre 300 y 480 KB de flash.

| # | Archivo | Frase |
|---|---|---|
| 1 | `frase1` | Tengo hambre |
| 2 | `frase2` | Hola |
| 3 | `frase3` | Tengo sed |
| 4 | `frase4` | Enciende la luz |
| 5 | `frase5` | Llamar al cuidador |
| 6 | `frase6` | Siento dolor |

### 1.1 Grabar en el iPhone 15 (app Notas de voz)
- [ ] *(Opcional, mejor calidad)* **Ajustes → Apps → Notas de voz → Calidad de audio → Sin pérdida**. En versiones anteriores de iOS: *Ajustes → Notas de voz*.
- [ ] Buscar un cuarto **silencioso** y sin eco (un cuarto con cortinas o ropa sirve).
- [ ] iPhone a unos **20 cm** de la boca, sin soplar al micrófono.
- [ ] Grabar **una frase por grabación**, voz clara y pausada, con el mismo tono en las 6.
- [ ] Recortar los silencios del inicio y del final: tocar la grabación → **⋯ → Editar grabación →** icono de recorte → ajustar → **Recortar → Guardar**. Menos silencio significa menos flash y una respuesta más rápida.
- [ ] Renombrar cada grabación como `frase1` … `frase6` (tocar el nombre para editarlo).

### 1.2 Pasar los audios a la laptop
Elegir una opción:
- [ ] **Mac:** ⋯ → Compartir → **AirDrop** a tu Mac.
- [ ] **Windows:** ⋯ → Compartir → **Guardar en Archivos** (iCloud Drive) y descargarlos desde icloud.com, o subirlos a **Google Drive**, o enviarlos por **correo**.
- [ ] Si usas WhatsApp, enviarlos como **Documento**, no como audio, porque como audio WhatsApp los comprime y cambia el formato.
- [ ] ✅ En una carpeta `audios/` del repositorio están `frase1.m4a` … `frase6.m4a`.

### 1.3 Convertir a WAV de 16 kHz mono
Abrir una terminal **dentro de la carpeta `audios/`**:

**Windows (PowerShell):**
```powershell
foreach ($i in 1..6) { ffmpeg -y -i "frase$i.m4a" -af loudnorm -ac 1 -ar 16000 -sample_fmt s16 "frase$i.wav" }
```
**Mac / Linux:**
```bash
for i in 1 2 3 4 5 6; do ffmpeg -y -i frase$i.m4a -af loudnorm -ac 1 -ar 16000 -sample_fmt s16 frase$i.wav; done
```
`loudnorm` iguala el volumen de las 6 frases.

- [ ] ✅ Están `frase1.wav` … `frase6.wav` y se escuchan bien al abrirlos en la laptop.

<details>
<summary>Alternativa sin terminal: Audacity</summary>

1. Abrir el `.m4a` en Audacity.
2. *Pistas → Mezclar → Mezclar estéreo a mono* (si es estéreo).
3. *Efecto → Volumen y compresión → Normalizar* (a −1 dB).
4. Abajo a la izquierda, o en *Audio Setup → Audio Settings*, poner la **frecuencia del proyecto en 16000 Hz**.
5. *Archivo → Exportar audio → WAV*, codificación **Signed 16-bit PCM**, canales **Mono**.
</details>

### 1.4 Convertir los WAV a un archivo `frases.h` para el ESP32
Las frases se guardan en la flash del ESP32 como **arreglos de C**, sin sistema de archivos ni pasos extra de carga. El script [herramientas/wav_a_header.py](herramientas/wav_a_header.py) hace la conversión.

- [ ] Desde la carpeta `audios/` ejecutar:
  ```bash
  uv run ../herramientas/wav_a_header.py frases.h frase1.wav frase2.wav frase3.wav frase4.wav frase5.wav frase6.wav
  ```
- [ ] ✅ Imprime algo como `frases.h: 6 frases, 380 KB en la flash`. Si dice que el formato está mal, repetir el paso 1.3.
- [ ] Copiar `frases.h` a `firmware/pruebas/02a_a2dp_solo/` y `firmware/pruebas/02b_coexistencia/`, reemplazando el provisional (que solo tiene silencio).
- [ ] Hacer commit de los `.m4a`, los `.wav` y los `frases.h`.

---

## 2. Prueba A: Bluetooth A2DP solo

**Objetivo:** el ESP32 se conecta al parlante y reproduce una frase cuando escribes su número (1–6) en el Monitor Serie. Todavía sin WiFi.

### Preparación
- [ ] Anotar el **nombre Bluetooth exacto** del parlante (como aparece en el iPhone; mayúsculas y espacios cuentan).
- [ ] **Desconectar el parlante del iPhone o de cualquier otro dispositivo** (en el iPhone: *Bluetooth → ⓘ → Olvidar este dispositivo*). Un parlante conectado a otro equipo no acepta al ESP32.
- [ ] Encender el parlante en **modo emparejamiento** (luz parpadeando).

### Código
Sketch: [firmware/pruebas/02a_a2dp_solo/](firmware/pruebas/02a_a2dp_solo/02a_a2dp_solo.ino)
- [ ] La carpeta tiene el `frases.h` real (paso 1.4), no el provisional.
- [ ] Cambiar `PARLANTE` por el nombre exacto del parlante.

### Checklist
- [x] Compila y sube sin error. Si dice *"Sketch too big"*, revisar el **Partition Scheme** del paso 0.
- [x] El Monitor Serie (115200 baudios) muestra **"Parlante CONECTADO"** en menos de 30 s.
- [x] Al escribir `1` (Enter) suena "Tengo hambre".
- [x] Las 6 frases suenan completas, sin cortes ni velocidad rara.
- [x] Ajustar `set_volume` si suena muy fuerte o saturado. *(Quedó en 127 + ganancia digital ×2,5: los WAV TTS llegan con pico ~12 000 de 32 767.)*
- [x] Al apagar y prender el parlante, el ESP32 se reconecta solo. *(ESP32-A2DP 1.8.11 no reintenta sola tras una desconexión: el sketch llama a `reconnect()` cada 10 s y activa `set_auto_reconnect(true)`, que guarda la dirección en la NVS. Tras el primer emparejamiento ya no hace falta el modo emparejamiento.)*
- [x] **Cambiar de parlante** (2026-10-28, Xiaomi Sound Pocket): el ESP32 sigue buscando el último guardado. `clean_last_connection()` **no borra la NVS si la dirección en memoria ya es cero**: primero `set_auto_reconnect(direccionFicticia)` y luego `clean_last_connection()`. Buscar por parte del nombre con `set_ssid_callback` ("xiaomi") funcionó mejor que el nombre exacto.

**Si no conecta:** revisar el nombre exacto, que el parlante no esté enlazado a otro equipo y que esté a menos de 2 m. Si la voz suena muy rápida o muy lenta, el WAV no está a 16 000 Hz: repetir el paso 1.3.

---

## 3. Prueba B: WiFi + MQTT + Bluetooth a la vez (coexistencia)

⚠️ **Es la prueba más importante del proyecto.** El WiFi y el Bluetooth comparten la misma radio de 2,4 GHz. Si esto no funciona, hay que cambiar a plan B: el audio se reproduce desde la laptop.

### Preparación
- [ ] Usar un **hotspot del celular o un router propio** (no el WiFi de la universidad).
- [ ] La laptop y el ESP32 conectados a la **misma red**. Anotar la **IP de la laptop** (Windows: `ipconfig`; Mac: *Ajustes → Red*).
- [ ] Mosquitto corriendo en la laptop con [laptop/mosquitto.conf](laptop/mosquitto.conf): `mosquitto -c laptop/mosquitto.conf -v`
- [ ] En Windows, permitir Mosquitto en el firewall (red privada) si el ESP32 no logra conectarse.

### Código
- ESP32: [firmware/pruebas/02b_coexistencia/](firmware/pruebas/02b_coexistencia/02b_coexistencia.ino). Además de las frases, responde en `asistivo/nodo1/pong` cada mensaje que le llega a `asistivo/nodo1/ping`.
- Laptop: [laptop/pruebas/latencia_mqtt.py](laptop/pruebas/latencia_mqtt.py) manda 30 pings (uno por segundo) y calcula la latencia.
- [ ] La carpeta del sketch tiene el `frases.h` real (paso 1.4).
- [ ] Copiar [firmware/nodo_asistivo/config.example.h](firmware/nodo_asistivo/config.example.h) como `config.h` dentro de la carpeta del sketch y completar `WIFI_SSID`, `WIFI_PASS`, `MQTT_HOST` (IP de la laptop) y `PARLANTE`. `config.h` está en `.gitignore`: **no se sube**.

### Checklist
- [x] El Monitor Serie muestra **WiFi OK**, **MQTT OK** y **Parlante CONECTADO**.
- [x] En otra terminal: `mosquitto_sub -t "asistivo/#" -v` muestra `asistivo/nodo1/estado online`.
- [x] Frase por MQTT: `mosquitto_pub -t asistivo/nodo1/cmd -q 1 -m "{\"accion\":\"frase\",\"id\":1}"` → suena "Tengo hambre". En Mac/Linux se pueden usar comillas simples: `-m '{"accion":"frase","id":1}'`.
- [x] **Latencia sin audio:** correr `uv run laptop/pruebas/latencia_mqtt.py` sin reproducir nada. Anotar el promedio y el máximo en la sección 6.
- [x] **Latencia con audio:** correr el script otra vez mientras se mandan frases seguidas (escribir 1, 2, 3… en el Monitor Serie). Anotar en la sección 6.
- [ ] Durante el audio: ¿se corta la voz? ¿se cae el MQTT? ¿se reinicia el ESP32? Anotarlo.
- [x] Desconectar el ESP32 → en `mosquitto_sub` aparece `offline` en pocos segundos. *(Con keepalive de 5 s: 3,6 s y 6 s en dos pruebas; el máximo teórico es ~7,5 s. Al reconectar el USB publica `online` en ~2 s y recupera los audífonos en ~20 s sin modo emparejamiento.)*
- [ ] Dejarlo funcionando **10 minutos** mandando frases cada tanto. ¿Sigue estable? *(Parcial: 3,6 min estable, sin reinicios ni caídas. Falta la prueba completa.)*
- [ ] ✅ **Aprobado si:** las frases suenan sin cortes, se reciben 30/30 pings y la latencia de ida es menor a 300 ms incluso con audio.
- [ ] ❌ **Si falla:** avisar al grupo y pasar al plan B (la laptop reproduce el audio). Si el ESP32 se reinicia al arrancar, probar invirtiendo el orden en `setup()` (primero `a2dp.start`, luego el WiFi).

---

## 4. Sensores

Probar cada sensor **solo**, con su sketch, mirando la señal en *Tools → Serial Plotter* (115200 baudios).

### 4.0 Escáner I2C (antes de los sensores I2C)

Sketch: [firmware/pruebas/03_escaner_i2c/](firmware/pruebas/03_escaner_i2c/03_escaner_i2c.ino). Imprime la dirección de cada dispositivo del bus (SDA = GPIO21, SCL = GPIO22).

### 4.1 MPU6050 (GY-521): navegación con la cabeza

**Conexión:**

| GY-521 | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| SCL | GPIO22 |
| SDA | GPIO21 |
| AD0 | sin conectar (o GND), dirección 0x68 |
| XDA, XCL, INT | sin conectar |

- [x] Cableado según la tabla (USB desconectado).
- [x] Escáner I2C → aparece **0x68**.
- [x] ~~Cargar *File → Examples → Adafruit MPU6050 → basic_readings*~~ **No sirve con nuestro módulo:** el GY-521 trae un chip compatible con `WHO_AM_I = 0x74` (no 0x68) y la librería de Adafruit lo rechaza (*"No se encontró el MPU6050"*). `03a` lee los registros directamente.
- [x] Cargar [firmware/pruebas/03a_mpu6050/](firmware/pruebas/03a_mpu6050/03a_mpu6050.ino): filtro complementario a 100 Hz que grafica `pitch` y `roll`.

- [x] En el Serial Plotter: con el sensor quieto, las curvas están planas (sin deriva). *(Ruido ±0,05°; en reposo marca ~10° / −14° por el desvío del clon → el firmware debe calibrar la posición neutra al arrancar.)*
- [x] Inclinar **adelante y atrás** mueve una curva; **izquierda y derecha** mueve la otra. Anotar cuál es cuál, porque depende de cómo quede montado en la vincha. *(Sensor plano: **adelante = pitch +**, **izquierda = roll −**. Marcar la orientación en el módulo.)*
- [ ] Montar el sensor en la vincha y medir cuántos grados se inclina la cabeza **cómodamente** (meta: unos 15°, no 45°). *(En la frente, vertical y con los pines hacia abajo: `IMU_FRENTE 1`, y el neutro debe dar cerca de 0°. Con `IMU_FRENTE 0` daba pitch −84,8° y gestos falsos al teclear. Si el chip mira hacia la frente: `IMU_SIGNO_PITCH -1` e `IMU_SIGNO_ROLL -1`.)*
- [ ] *(Siguiente)* Agregar umbrales con histéresis para generar **un** evento por inclinación (`izq`, `der`, `arriba`, `abajo`).

### 4.2 MAX30102: pulso y SpO₂

**Conexión:**

| MAX30102 | ESP32 |
|---|---|
| VIN | 3V3 |
| GND | GND |
| SCL | GPIO22 (compartido con el MPU6050) |
| SDA | GPIO21 (compartido con el MPU6050) |
| INT | sin conectar |

- [x] Cableado según la tabla.
- [x] Escáner I2C → aparece **0x57** (y **0x68** si el MPU6050 sigue conectado).
- [x] El sensor responde al poner y quitar el dedo (IR ~300 sin dedo, ~100 000 con dedo). El LED rojo se enciende solo cuando un sketch lo configura.
- [x] ~~*Example5_HeartRate*~~ **Su BPM no sirve:** salta entre 7 y 213 (el detector se engancha a la luz ambiental).
- [x] ~~*Example8_SPO2*~~ **Cuelga el ESP32** (usa el GPIO11, que es de la flash). Usar [firmware/pruebas/03b_max30102/](firmware/pruebas/03b_max30102/03b_max30102.ino), que además lee la FIFO directo (con la librería llegaban ~10 de las 25 muestras/s), usa brillo 30 (con 60 se saturaba al 96 %) y no se cuelga si se suelta un cable. **SpO₂ 99 %**.
- [x] **El pulso del algoritmo de Maxim tampoco sirve** (125 BPM con el pulso real en ~79): cuenta la muesca dícrota como otro latido. El pulso se calcula con un pasa banda de 0,7–3,5 Hz y los intervalos entre latidos (validado con la gráfica de `docs/resultados/`).
- [ ] Comparar con un oxímetro de farmacia o un reloj: anotar la diferencia en la sección 6.
- [ ] Probar sujetando el dedo con una **liga o cinta**, porque la presión cambia mucho la lectura. *(El 2026-10-28 el módulo se apagó 3 veces al presionarlo en el protoboard: conectarlo con dupont, sin protoboard.)*

**Si no aparece 0x57:** revisar SDA y SCL (a menudo están cruzados). Algunos módulos morados genéricos tienen problemas con las resistencias pull-up; probar alimentando VIN con 5 V **solo si el módulo tiene regulador**, o cambiar de módulo.

### 4.3 EMG DFRobot Gravity (OYMotion SEN0240): confirmar con la mandíbula

**Datos clave del sensor:**
- Se alimenta con **3,3–5,5 V**, así que no necesita baterías ni divisor.
- La salida va de **0 a 3,0 V**, centrada en **1,5 V** en reposo. Es la señal EMG **amplificada y filtrada, sin rectificar**; el ESP32 hace la rectificación.
- Banda útil de 20–500 Hz, así que hay que **muestrear a 1 kHz**.
- Usa **electrodo seco de metal**, reutilizable y sin gel.

**Conexión (cable Gravity de 3 hilos):**

| Sensor (conector PH2.0) | ESP32 |
|---|---|
| **+** (rojo) | 3V3 |
| **−** (negro) | GND |
| **A** (azul) | GPIO34 |

- [x] Placa del electrodo conectada a la placa de señal por el cable de **3,5 mm**.
- [x] Cable Gravity conectado según la tabla.
- [x] **Laptop a batería, desenchufada del cargador** (el cargador mete ruido de 60 Hz).

**Colocación del electrodo sobre el masetero:**
- [ ] Apretar los dientes con un dedo en la mejilla, entre la oreja y el ángulo de la mandíbula: el músculo que "salta" es el masetero.
- [ ] Limpiar la piel con alcohol y dejarla secar.
- [ ] Colocar el electrodo **sobre el masetero**, con su lado largo **en la dirección de las fibras** (del pómulo hacia el ángulo de la mandíbula, más o menos vertical).
- [ ] Sujetarlo con una **banda elástica o vincha** para que quede presionado contra la piel sin moverse.

**Sketch 1: ver la señal.** [firmware/pruebas/03c_emg_senal/](firmware/pruebas/03c_emg_senal/03c_emg_senal.ino): muestrea a 1 kHz, resta el nivel medio, rectifica y grafica la señal y su envolvente (media móvil de 50 ms).

- [ ] En el Serial Plotter, con la mandíbula **relajada**, la envolvente queda baja y plana.
- [ ] Al **apretar los dientes**, la envolvente sube claramente (varias veces el nivel de reposo).
- [ ] **Hablar, tragar y mover la cabeza** sube poco o nada comparado con el apretón. Si sube mucho, reacomodar el electrodo.
- [ ] Anotar los niveles de reposo y de apretón en la sección 6.

> **Si la señal sale plana en 0:** puede que el GPIO34 esté **saturado** (4095, ~3,17 V fijos), y al restarle el nivel medio queda en 0. En reposo debe marcar **~1,5 V con ruido**. Revisar que el azul esté en **D34** y el rojo en **3V3**, que los **3 contactos** del electrodo toquen la piel y que el cable de 3,5 mm esté metido hasta el fondo. *(Pasó el 2026-10-21 y se resolvió revisando cables y electrodo.)*

> **Si la señal tiene mucho ruido en reposo** (envolvente de cientos en vez de ~11): casi seguro es la **red eléctrica (60 Hz)**. El 2026-10-28, en un salón y con la laptop a batería, el 94 % de la señal en reposo era 60 Hz (en el Serial Plotter a 100 Hz aparece como 40 Hz). `03c_emg_senal` ahora tiene un **filtro notch de 60/120/180 Hz** (conserva el 87 % de la banda de 20–450 Hz) y bajó el reposo de 424 a 37. En los primeros intentos de ese día el sensor no mostró las contracciones, ni en el masetero (saturaba el ADC) ni en el antebrazo. **En el último intento en el antebrazo (electrodo en la piel, laptop a batería) sí se vieron con el filtro:** reposo ~30, puños de 100–150 de media con picos de 240–365 (`2026-10-28_emg_antebrazo_v2`). El sensor y el cable funcionan. **El 2026-10-29, en casa sin ruido, el masetero también funcionó** (electrodo sujeto con el dedo): reposo ~9, apretones de 180–240, sin saturar (`2026-10-29_emg_masetero_casa`). Gráficas en `docs/resultados/2026-10-28_emg_*`.

**Sketch 2: detectar confirmar y cancelar.** [firmware/pruebas/03c_emg_eventos/](firmware/pruebas/03c_emg_eventos/03c_emg_eventos.ino): usa el mismo filtro de 60 Hz que el sketch 1, calibra 5 s en reposo (umbral μ + 3σ, como mínimo μ + 50), confirma con contracciones de 100 ms a 1 s, cancela con más de 1 s y aplica un periodo refractario de 700 ms. Una contracción empieza al pasar el umbral y termina recién al bajar a la mitad entre μ y el umbral (**histéresis**): con un solo umbral, sobre la grabación del salón del 2026-10-28, los apretones largos oscilaban alrededor del umbral y daban `CONFIRMAR` en vez de `CANCELAR` (el más largo, dos veces). Esos valores son constantes al inicio del sketch; con `GRAFICAR = true` muestra la envolvente y los dos umbrales en el Serial Plotter.

La calibración se repite **cada vez que arranca el ESP32**: no queda guardada. Hay que quedarse relajado los primeros 5 s y reiniciar (botón **EN**) al cambiar el electrodo de lugar o de ambiente.

- [x] Al arrancar imprime μ, σ, el umbral y el % de muestras **saturadas** (debe ser 0; si pasa del 1 %, avisa). Referencia de μ: ~11 sin ruido (2026-10-21, antebrazo), ~30 con el filtro en el salón (2026-10-28) y ~8 en el masetero en casa (2026-10-29: μ 7,6, σ 0,9, umbral 57,6, saturadas 0 %).
- [x] **Apretón corto** (unos 0,3 s) → `>>> CONFIRMAR`, una sola vez. *(2026-10-29, masetero en casa.)*
- [x] **Apretón largo** (más de 1 s) → `>>> CANCELAR`, una sola vez. *(2 de 2.)*
- [x] **10 apretones cortos** → ¿cuántos CONFIRMAR? Meta: 9 o más. *(15 `CONFIRMAR` en 65 s, con intervalos regulares de ~4,3 s; se hicieron "más de 10", sin conteo exacto, así que no se puede calcular el porcentaje de aciertos. Repetir con 10 contados.)*
- [x] **5 minutos relajado**, hablando y tragando normal → ¿cuántos eventos falsos? Meta: 1 o menos. *(0 falsos: los 3 eventos fueron apretones a propósito. Ojo: en una grabación aparte, 2 tragadas de 50 s dieron ráfagas de ~0,7 s tan altas como un apretón; en estos 5 min no dispararon, pero no se contó cuántas tragadas hubo.)*
- [ ] Si hay muchos falsos: subir el multiplicador (3σ → 4σ) o reacomodar el electrodo. Si cuesta activarlo: bajarlo a 2,5σ. *(Con σ chica manda `MARGEN_MIN`: en las grabaciones de 21 y 28, σ fue 1,4 y 3,3, así que el umbral quedó en μ + 50.)*
- [ ] **Prueba con ruido, en casa:** reiniciar con la laptop **enchufada al cargador** y sentado junto a una zapatilla con cosas enchufadas; repetir los 10 apretones cortos y 3 largos. Anotar μ y los aciertos: así se simula el salón de la presentación.

---

## 5. Actuadores

### 5.1 Relé optoacoplado → foco LED 12 V

**Conexión del lado de control:**

| Módulo relé | ESP32 |
|---|---|
| VCC | VIN (5 V del USB) |
| GND | GND |
| IN | GPIO26 |

**Conexión del lado de potencia (recién al final):**
- Fuente de 12 V (+) → **COM** del relé
- **NO** del relé → (+) del foco LED 12 V
- (−) del foco → (−) de la fuente de 12 V

Sketch: [firmware/pruebas/04a_rele/](firmware/pruebas/04a_rele/04a_rele.ino). Alterna el GPIO26 entre HIGH y LOW cada 2 s y lo imprime en el Monitor Serie.

- [x] **Sin carga** (solo el módulo): se escucha el "clic" y el LED del módulo cambia cada 2 s. *(Solo con VCC del módulo en **3V3**: ver abajo.)*
- [x] Anotar si el relé se activa con **HIGH** o con **LOW**. Muchos módulos se activan con LOW; en ese caso, en el código final "encender" es `LOW`. *(**LOW**: con HIGH 1 s / LOW 4 s el LED verde quedó 4 s encendido. Sin transistor, `RELE_ENCENDIDO` va en `LOW`; con el 2N2222 del cableado final (sección 7.0), en `HIGH`.)*
- [x] Si el relé **nunca se apaga**, es un problema conocido de módulos de 5 V con lógica de 3,3 V. Soluciones: un módulo con jumper **JD-VCC**, o manejar IN con un transistor 2N2222 (conexión como en la nota de la sección 5.2). *(Nos pasó el 2026-10-28: módulo JQC3F-05VDC-C de 3 pines IN/GND/VCC, sin jumpers; con VCC a 5 V el LED verde quedaba fijo. **Provisional:** VCC del módulo a **3V3** → conmuta. La bobina es de 5 V y a 3,3 V queda justa: la solución final es un **2N2222** que lleve IN a GND, con el módulo de nuevo a 5 V; en el código, la lógica se invierte.)*

> **Actualización (2026-11-08): se reemplazó el JQC3F de 1 canal por un módulo de 2 canales.** Quedó con VCC a **5 V** e IN **directo a D26**, sin transistor, y se enciende con **LOW** (`RELE_ENCENDIDO LOW`). El 2N2222, la lógica HIGH y el VCC a 3V3 de las notas anteriores ya no aplican.

- [ ] Medir el voltaje de IN con D26 desconectado. Si supera 3,3 V, ese pin queda expuesto: usar el jumper **JD-VCC** si el módulo lo trae (VCC a 3V3, JD-VCC a 5 V).
- [ ] Recién entonces conectar el **foco de 12 V** y la fuente. Nunca usar 220 V en este proyecto.
- [ ] ✅ El foco prende y apaga cada 2 s.

### 5.2 Buzzer activo directo al GPIO27 (sin transistor)

**Conexión:**
- GPIO27 (D27) → (+) del buzzer (pata larga, o el "+" grabado arriba)
- (−) del buzzer → GND

Nuestro buzzer de 2 patas suena bien a 3,3 V, así que no necesita transistor. Antes de conectarlo al GPIO, probarlo entre **3V3 y GND**: si suena fuerte, va directo. **Nunca** poner el (+) en VIN y el (−) en el GPIO: eso mete 5 V al pin.

> **Si un buzzer suena bajo a 3,3 V o consume más de ~20 mA:** usar un 2N2222. GPIO27 → 1 kΩ → **Base**; **Emisor** → GND; **Colector** → (−) del buzzer; (+) del buzzer → VIN. Patas del 2N2222A / PN2222A (TO-92), cara plana hacia uno y patas abajo: **E – B – C**.

Sketch: [firmware/pruebas/04b_buzzer/](firmware/pruebas/04b_buzzer/04b_buzzer.ino). Da 3 pitidos de 200 ms y espera 3 s.

- [x] ✅ Suenan 3 pitidos cada 3 s. *(2026-10-28: buzzer **activo**, directo a D27 sin transistor; suena bien a 3,3 V y a 5 V.)*
- [ ] Si no suena: revisar la polaridad (la pata larga va a D27). Al revés no suena, pero no se daña.

### 5.3 Actuadores por MQTT
- [x] Agregar al sketch de coexistencia (paso 3) las acciones `{"accion":"luz","estado":"toggle"}` → relé y `{"accion":"alerta"}` → buzzer por 2 s. *(Hecho en `02b_coexistencia`: además, la frase 4 conmuta la luz y la frase 5 activa el buzzer. Por el Monitor Serie: `a` = alerta, `l` = luz.)*
- [x] `{"accion":"alerta"}` con `mosquitto_pub` → el buzzer suena 2 s. *(2026-10-28, 2 de 2. `{"accion":"frase","id":5}` también lo activa.)*
- [ ] `{"accion":"luz","estado":"toggle"}` con `mosquitto_pub` → el relé conmuta. *(Para probar solo el relé: sketch [firmware/pruebas/04c_rele_mqtt/](firmware/pruebas/04c_rele_mqtt/04c_rele_mqtt.ino) y `uv run laptop/pruebas/foco.py on`, `off` o `toggle`.)*
- [ ] Probar con `mosquitto_pub` mientras suena una frase (con el parlante conectado).

> **Si el ESP32 imprime `falló (rc=-2)`:** no llega al broker. Revisar que la laptop siga en el hotspot (`ipconfig`) y que `MQTT_HOST` en `config.h` sea su IP ahí (con el iPhone suele ser **172.20.10.2**). El 2026-10-28 Windows se cambió solo a la red de UTEC en medio de la prueba: desactivar "Conectar automáticamente" en las otras redes.
- [ ] ✅ **Con esto, el núcleo IoT está completo** (sensores + MQTT + actuadores).

---

## 6. Registro de resultados

Completar a medida que se prueba. Sirve como evidencia para el informe final.

| Prueba | Fecha | Resultado | Notas |
|---|---|---|---|
| A2DP solo: conexión al parlante | 2026-10-21 | ✅ | Sony ULT WEAR (`"ULT WEAR"`). Conecta en modo emparejamiento y se reconecta solo tras recargar el firmware |
| A2DP: las 6 frases suenan bien | 2026-10-21 | ✅ | Audio TTS de ttsmaker. Volumen bien con `set_volume(127)` + ganancia ×2,5 |
| Coexistencia: latencia de ida **sin** audio | 2026-10-21 | ✅ promedio · ⚠️ máximo | Promedio 108 / mediana 86 / p90 154 / máximo 497 ms; 2/30 > 300 ms. Hotspot del celular. Datos: `docs/resultados/` |
| Coexistencia: latencia de ida **con** audio | 2026-10-21 | ✅ promedio · ⚠️ máximo | Promedio 113 / mediana 97 / p90 207 / máximo 440 ms; 2/30 > 300 ms. 22 frases por MQTT durante la prueba, sin reinicios ni caídas |
| Coexistencia: pings recibidos | 2026-10-21 | 30/30 | Con y sin audio |
| Coexistencia: estable 10 min | 2026-10-21 | ⏸ parcial | 3,6 min: 214/214 pings, 11 frases, sin reinicios ni `offline`. Ida: media 139 / p90 289 / máximo 868 ms; 19/214 > 300 ms |
| MPU6050: grados cómodos de inclinación | 2026-10-28 | ⬜ falta en la vincha | En la mano: adelante +24,7° en pitch (roll −1,2°); izquierda −34,8° en roll (pitch −9,8°). Clon con WHO_AM_I 0x74 |
| MAX30102 vs oxímetro de referencia | 2026-10-28 | ✅ sin referencia | 60 s a 25 muestras/s, dedo apoyado: **pulso ~79 BPM** (75–88; espectro 78) · **SpO₂ 99 %** (Maxim). Sin oxímetro para comparar. Gráfica y datos en `docs/resultados/` |
| EMG: envolvente en reposo vs apretón | 2026-10-21 / 28 | ✅ antebrazo (21; 28 con filtro) · ❌ masetero (28, saturado) | **Antebrazo** (flexores): reposo ~11 (σ 1,2), puños 300–420 cuentas (~30×). Simulando `03c_emg_eventos` sobre la grabación, el umbral μ+20 ≈ 31 da 2 falsos en reposo; con ~60 no hay falsos. **28, salón con 60 Hz, con filtro:** reposo ~30 (σ 3,3); 6 puños de 1,0–2,6 s, de 100–150 de media (picos 240–365). Simulando el sketch: con un solo umbral, 7 `CONFIRMAR` y ningún `CANCELAR` (el más largo se partió en dos); con histéresis, 5 `CANCELAR` y 1 `CONFIRMAR` (el de 1,0 s). Gráficas y datos en `docs/resultados/` |
| EMG: aciertos en 10 apretones | 2026-10-29 | ✅ 15 detectados, sin conteo exacto | Masetero, casa sin ruido, dedo como sujeción. Hizo "más de 10"; no se contaron, así que no hay % de aciertos. 2 de 2 apretones largos dieron `CANCELAR`. Datos: `docs/resultados/2026-10-29_emg_masetero_eventos.txt` |
| EMG: falsos en 5 min de reposo | 2026-10-29 | ✅ 0 | Hablando y tragando normal; los 3 eventos fueron apretones a propósito. Falta repetir con ruido (cargador, salón) y con vincha |
| Relé: lógica (HIGH o LOW = encendido) | 2026-10-28 | ✅ LOW | JQC3F-05VDC-C; conmuta solo con VCC del módulo a 3V3 (provisional, falta transistor). Sin carga de 12 V todavía |
| Relé de 2 canales (reemplaza al JQC3F) | 2026-11-08 | ✅ LOW | VCC 5 V, IN directo a D26, sin transistor. Carga en COM y NO, probado con el profesor; el foco arranca apagado |
| Buzzer | 2026-10-28 | ✅ | Activo, directo a D27 sin transistor (suena bien a 3,3 V). `04b_buzzer`: 3 pitidos cada 3 s |
| Buzzer por MQTT (`alerta`) | 2026-10-28 | ✅ | `mosquitto_pub` → broker → ESP32 → buzzer 2 s, 2 de 2. La frase 5 también lo activa. Falta probarlo con una frase sonando |

---

## 7. Prueba de conjunto: el sistema completo

Firmware: [firmware/nodo_asistivo/](firmware/nodo_asistivo/nodo_asistivo.ino). Une todo lo aprobado en las secciones 1–5. **Se prueba por etapas:** si algo falla, se desactiva ese módulo en `config.h` (`USAR_AUDIO`, `USAR_EMG`, `USAR_IMU`, `USAR_PULSO` en 0) y se sigue con el resto.

### 7.0 Cableado final (USB desconectado)

| Componente | Conexión |
|---|---|
| Rieles | **3V3** → EMG, MPU6050, MAX30102 · **VIN (5 V)** → relé · **los dos − unidos al GND** (nunca unir los +) |
| EMG SEN0240 | rojo 3V3 · negro GND · azul **D34** |
| MPU6050 y MAX30102 | VCC/VIN 3V3 · GND · SDA **D21** · SCL **D22** (bus compartido; cable largo hasta la vincha y el dedo) |
| Relé (2 canales) | VCC **5 V** · GND · IN del canal usado → **D26**, directo y sin transistor. Se enciende con **LOW** |
| Buzzer | + (pata larga) → **D27** · − → GND. Directo, sin transistor (sección 5.2) |
| Carga del relé | cable + de la lámpara USB cortado: un extremo a **COM**, el otro a **NO** |

### 7.1 Preparación
- [ ] Hotspot del celular; la laptop conectada a él. IP de la laptop: `ip -4 addr` (Linux) o `ipconfig`.
- [ ] Firewall: puerto **1883** abierto (sección 3).
- [ ] `firmware/nodo_asistivo/config.h` copiado de `config.example.h`: WiFi, `MQTT_HOST` = IP de la laptop, `PARLANTE` = parte del nombre (`"xiaomi"`), `RELE_ENCENDIDO LOW`.
- [ ] Cargar `nodo_asistivo` con **Partition Scheme: Huge APP**. En Linux: **`herramientas/cargar_nodo.sh`** pone sola la IP actual de la laptop en `MQTT_HOST`, compila y carga (avisa si la red o el firewall no cuadran).
- [ ] Laptop: **`laptop/iniciar.sh`** arranca el broker y abre la interfaz y el dashboard (`--vision` suma la mirada; `--simulador`, el ESP32 simulado). A mano: `mosquitto -c laptop/mosquitto.conf -v` y abrir `laptop/interfaz/index.html` y `laptop/dashboard/index.html`.

### 7.2 Etapa 1: nodo y red
- [ ] Monitor Serie: `[wifi] conectado`, `[mqtt] conectado`, `[imu] MPU6050 encontrado`, `[pulso] MAX30102 encontrado`, `[emg] listo: μ=… umbral=…` (mandíbula relajada los primeros 6 s).
- [ ] Dashboard: **Nodo en línea**; la ficha muestra EMG, cabeza, sensor de pulso y parlante (llegan cada 5 s por `nodo1/diag`); hay latencia (ping/pong).
- [ ] Desconectar el USB → el dashboard marca **DESCONECTADO** en ≤ 8 s (LWT). Reconectar → vuelve solo.

### 7.3 Etapa 2: actuadores por MQTT (desde la interfaz, con el teclado)
- [ ] Flechas + **Enter** en cada casilla: suena la frase 1–6 en el parlante.
- [ ] Casilla **4** («Enciende la luz»): la lámpara se enciende; otra vez, se apaga. El dashboard muestra **Luz encendida/apagada**.
- [ ] Casilla **5** («Llamar al cuidador»): el buzzer pita 2 s.

### 7.4 Etapa 3: sensores al dashboard
- [ ] **Pulso:** dedo en el MAX30102 (fijo con liga) → en ~10 s aparecen FC y SpO₂. Comparar con un reloj u oxímetro: anotar en la sección 6.
- [ ] **Cabeza:** con la vincha puesta, la fila «Cabeza» cambia al inclinar (adelante = primer número +, izquierda = segundo −). Si sale al revés o cruzado: `IMU_SIGNO_*` o `IMU_INTERCAMBIAR` en `config.h`. Tecla **I** de la interfaz: nueva posición neutra.
- [ ] **EMG:** la fila «EMG» sube por encima del umbral al apretar la mandíbula y vuelve abajo al relajar. Si el reposo está cerca del umbral: tecla **E** (recalibrar) con la mandíbula relajada.

### 7.5 Etapa 4: entradas del paciente en la interfaz
- [ ] Inclinar la cabeza: el cursor se mueve **una** casilla por gesto (sin pasos dobles).
- [ ] Apretón corto de mandíbula: **confirma** (suena la frase). Apretón largo (> 1 s): **cancela**.
- [ ] Hablar, tragar y mover la cabeza: no confirma (o casi nunca).
- [ ] *(Opcional)* Mirada: `uv run laptop/vision/mirada.py`, calibrar con **C**, comprobar con **K**.

### 7.6 Etapa 5: escenarios completos (la demo)
- [ ] «Enciende la luz»: llegar a la casilla 4 con la cabeza (o la mirada) y apretar la mandíbula → frase + lámpara.
- [ ] «Llamar al cuidador»: casilla 5 → frase + buzzer + aparece en el registro del dashboard.
- [ ] Cancelar: elegir una casilla y mantener el apretón > 1 s → no se envía nada.
- [ ] Alarma de signos vitales: `mosquitto_pub -t asistivo/nodo1/vitales -m '{"bpm":135,"spo2":89}'` varias veces → el dashboard muestra la alarma.
- [ ] Apagar y prender el parlante, y desconectar el WiFi un momento: el sistema se recupera solo.

### 7.7 Etapa 6: mediciones para el informe
- [ ] **Modo prueba** (tecla **M**): 20 selecciones con cabeza + mandíbula → tasa de aciertos (meta ≥ 90 %) y tiempo de selección (meta ≤ 5 s).
- [ ] **Modo reposo**: 5 min sentado, hablando normal → activaciones accidentales (meta ≤ 1 / 5 min).
- [ ] **Estabilidad**: 10 min con todo encendido → sin reinicios ni desconexiones; latencia (meta < 300 ms).
- [ ] **Exportar CSV** en el dashboard y guardarlo en `docs/resultados/`.

| Prueba de conjunto | Fecha | Resultado | Notas |
|---|---|---|---|
| Etapa 1: nodo, red y LWT | | | |
| Etapa 2: frases, luz, buzzer por MQTT | | | |
| Etapa 3: pulso / cabeza / EMG en el dashboard | | | |
| Etapa 4: cabeza mueve el cursor, mandíbula confirma | | | |
| Etapa 5: escenarios de la demo | | | |
| Etapa 6: aciertos · tiempo · accidentales · latencia | | | |
