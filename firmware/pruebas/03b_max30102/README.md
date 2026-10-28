# 03b_max30102: pulso y SpO₂

`03b_max30102.ino` adapta el `Example8_SPO2` de la librería **SparkFun MAX3010x** al ESP32. Cableado y criterios en `CHECKLIST_ARMADO.md`, sección 4.2.

**Por qué no se usan los ejemplos tal cual** (probado el 2026-10-28):

| Ejemplo | Problema |
|---|---|
| `Example5_HeartRate` | El BPM salta entre 7 y 213: su detector se engancha a la luz ambiental |
| `Example8_SPO2` | Cuelga el ESP32 (watchdog): usa el GPIO11, que es de la flash interna |
| `check()` / `available()` | Con su búfer de 4 muestras llegaban ~10 de las 25 muestras/s del sensor |

**Qué hace el sketch:** lee la FIFO directo de los registros (25 muestras/s), brillo 30 (con 60 el IR se saturaba al 96 % del tope), imprime `ir:<valor>` por muestra y cada 1 s `HR=… SPO2=…` con el algoritmo de Maxim. Si el sensor deja de responder, avisa y lo reinicia.

**Ojo:** el **pulso** del algoritmo de Maxim no sirve (dio 125 BPM con el pulso real en ~79: cuenta la muesca dícrota como otro latido). Usar solo su **SpO₂**; el pulso se calcula con un pasa banda de 0,7–3,5 Hz y los intervalos entre latidos. Gráfica en `docs/resultados/2026-10-28_max30102_pulso.png`.
