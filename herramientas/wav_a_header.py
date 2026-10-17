import array
import pathlib
import sys
import wave

TASA = 16000


def main():
    if len(sys.argv) < 3:
        sys.exit("Uso: python wav_a_header.py frases.h frase1.wav frase2.wav ...")
    salida = pathlib.Path(sys.argv[1])
    wavs = [pathlib.Path(p) for p in sys.argv[2:]]
    partes = ["// Generado por wav_a_header.py. No editar a mano.",
              "#pragma once", "#include <stdint.h>", ""]
    nombres, total = [], 0
    for i, ruta in enumerate(wavs, 1):
        with wave.open(str(ruta), "rb") as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2 or w.getframerate() != TASA:
                sys.exit(f"{ruta}: debe ser WAV mono, 16 bits, {TASA} Hz "
                         f"(es {w.getnchannels()} canal(es), {8 * w.getsampwidth()} bits, "
                         f"{w.getframerate()} Hz)")
            datos = array.array("h")
            datos.frombytes(w.readframes(w.getnframes()))
        if sys.byteorder == "big":
            datos.byteswap()
        nombre = f"frase{i}"
        nombres.append(nombre)
        total += len(datos) * 2
        partes.append(f"// {ruta.name}: {len(datos)} muestras ({len(datos) / TASA:.2f} s)")
        partes.append(f"const int16_t {nombre}[] = {{")
        for j in range(0, len(datos), 16):
            partes.append("  " + ", ".join(str(v) for v in datos[j:j + 16]) + ",")
        partes.append("};")
        partes.append("")
    partes.append(f"const int NUM_FRASES = {len(nombres)};")
    partes.append("const int16_t* const FRASES[] = {" + ", ".join(nombres) + "};")
    partes.append("const uint32_t FRASES_LEN[] = {"
                  + ", ".join(f"sizeof({n}) / sizeof({n}[0])" for n in nombres) + "};")
    salida.write_text("\n".join(partes) + "\n", encoding="utf-8")
    print(f"{salida}: {len(nombres)} frases, {total / 1024:.0f} KB en la flash")


if __name__ == "__main__":
    main()
