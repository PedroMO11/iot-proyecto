// MARCADOR DE POSICIÓN: frases en silencio, solo para que el sketch compile.
// Reemplazar por el frases.h que genera herramientas/wav_a_header.py (CHECKLIST_ARMADO.md, paso 1.4).
#pragma once
#include <stdint.h>

const int16_t frase1[] = {0};
const int16_t frase2[] = {0};
const int16_t frase3[] = {0};
const int16_t frase4[] = {0};
const int16_t frase5[] = {0};
const int16_t frase6[] = {0};

const int NUM_FRASES = 6;
const int16_t* const FRASES[] = {frase1, frase2, frase3, frase4, frase5, frase6};
const uint32_t FRASES_LEN[] = {sizeof(frase1) / sizeof(frase1[0]), sizeof(frase2) / sizeof(frase2[0]), sizeof(frase3) / sizeof(frase3[0]), sizeof(frase4) / sizeof(frase4[0]), sizeof(frase5) / sizeof(frase5[0]), sizeof(frase6) / sizeof(frase6[0])};
