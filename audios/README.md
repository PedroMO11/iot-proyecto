# Audios

Aquí van las 6 frases: los `.m4a` originales del iPhone, los `.wav` convertidos (mono, 16 bits, 16 000 Hz, máximo 2,5 s) y el `frases.h` generado. Pasos completos en `CHECKLIST_ARMADO.md`, sección 1.

| Archivo | Frase |
|---|---|
| `frase1` | Tengo hambre |
| `frase2` | Hola |
| `frase3` | Tengo sed |
| `frase4` | Enciende la luz |
| `frase5` | Llamar al cuidador |
| `frase6` | Siento dolor |

Desde esta carpeta:

```bash
python ../herramientas/wav_a_header.py frases.h frase1.wav frase2.wav frase3.wav frase4.wav frase5.wav frase6.wav
```

Luego copiar `frases.h` a cada sketch que lo use (`02a_a2dp_solo`, `02b_coexistencia` y `nodo_asistivo`), reemplazando el marcador de posición en silencio que traen.
