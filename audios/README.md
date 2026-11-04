# Audios

Aquí van las 6 frases: los `.mp3` originales generados con voz sintética en [ttsmaker.com](https://ttsmaker.com), los `.wav` convertidos (mono, 16 bits, 16 000 Hz, máximo 2,5 s) y el `frases.h` generado. Pasos completos en `CHECKLIST_ARMADO.md`, sección 1.

| Archivo | Frase |
|---|---|
| `frase1` | Tengo hambre |
| `frase2` | Hola |
| `frase3` | Tengo sed |
| `frase4` | Enciende la luz |
| `frase5` | Llamar al cuidador |
| `frase6` | Siento dolor |

Para rehacer una frase, generarla en ttsmaker.com con la misma voz que las demás, descargarla en MP3 y guardarla con su nombre (`fraseN.mp3`). Comprobar que cada archivo sea distinto: la página a veces vuelve a descargar el audio anterior.

Desde esta carpeta, convertir a WAV. El filtro recorta el silencio del inicio y del final (deja 80 ms) y normaliza el volumen.

PowerShell:

```powershell
$T = "silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08"
foreach ($i in 1..6) { ffmpeg -y -i "frase$i.mp3" -af "$T,areverse,$T,areverse,loudnorm" -ac 1 -ar 16000 -sample_fmt s16 "frase$i.wav" }
```

Mac/Linux:

```bash
T="silenceremove=start_periods=1:start_threshold=-50dB:start_silence=0.08"
for i in 1 2 3 4 5 6; do ffmpeg -y -i frase$i.mp3 -af "$T,areverse,$T,areverse,loudnorm" -ac 1 -ar 16000 -sample_fmt s16 frase$i.wav; done
```

Luego generar `frases.h`:

```bash
uv run ../herramientas/wav_a_header.py frases.h frase1.wav frase2.wav frase3.wav frase4.wav frase5.wav frase6.wav
```

Por último, copiar `frases.h` a cada sketch que lo use (`02a_a2dp_solo`, `02b_coexistencia` y `nodo_asistivo`), reemplazando el marcador de posición en silencio que traen.
