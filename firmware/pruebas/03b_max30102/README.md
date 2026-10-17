# 03b_max30102: pulso y SpO₂

Esta prueba usa los ejemplos de la librería **SparkFun MAX3010x Pulse and Proximity Sensor Library**, así que no hay sketch propio. Detalle de cableado y criterios en `CHECKLIST_ARMADO.md`, sección 4.2.

1. Escáner I2C (`../03_escaner_i2c/`) → debe aparecer **0x57**.
2. *File → Examples → SparkFun MAX3010x → Example1_Basic_Readings*: los valores cambian al poner y quitar el dedo.
3. *Example5_HeartRate*: el BPM promedio se estabiliza tras 10–15 s.
4. *Example8_SPO2*: SpO₂ entre 95 y 100 % en una persona sana.

Si se adapta algún ejemplo (por ejemplo, para publicar en `asistivo/nodo1/vitales`), guardarlo aquí como `03b_max30102.ino`.
