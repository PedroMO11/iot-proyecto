// 03c_emg_senal.ino : muestreo a 1 kHz, filtro de la red eléctrica, rectificación y envolvente
// Filtro notch en 60 Hz y armónicos (la red de Perú es de 60 Hz): el 2026-10-28, en el salón,
// el 94 % de la señal en reposo era interferencia de la red, con la laptop a batería.
// Imprime la envolvente filtrada y la sin filtrar para comparar.
const int PIN_EMG = 34;
const uint32_t PERIODO_US = 1000;       // 1 kHz
const float FS = 1000.0;
const int VENTANA = 50;                 // media móvil de 50 ms

// Biquad notch (RBJ Audio EQ Cookbook): ganancia 0 en f0, ancho de banda f0 / Q
struct Notch {
  float b0, b1, b2, a1, a2, x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  Notch(float f0, float q) {
    float w = 2 * PI * f0 / FS, alfa = sin(w) / (2 * q), a0 = 1 + alfa;
    b0 = 1 / a0; b1 = -2 * cos(w) / a0; b2 = 1 / a0; a1 = -2 * cos(w) / a0; a2 = (1 - alfa) / a0;
  }
  float paso(float x) {
    float y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
    x2 = x1; x1 = x; y2 = y1; y1 = y;
    return y;
  }
};
Notch red[] = {Notch(60, 8), Notch(120, 8), Notch(180, 8)};

struct MediaMovil {
  float buf[VENTANA] = {0}, suma = 0;
  int i = 0;
  float paso(float r) { suma += r - buf[i]; buf[i] = r; i = (i + 1) % VENTANA; return suma / VENTANA; }
};
MediaMovil envFiltrada, envCruda;

float base = 0;                         // nivel de reposo (~1,5 V)

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);             // 0..4095
  analogSetPinAttenuation(PIN_EMG, ADC_11db);
  long acc = 0;
  for (int i = 0; i < 1000; i++) { acc += analogRead(PIN_EMG); delayMicroseconds(1000); }
  base = acc / 1000.0;
}

void loop() {
  static uint32_t t = micros();
  if (micros() - t < PERIODO_US) return;
  t += PERIODO_US;

  int x = analogRead(PIN_EMG);
  base = 0.999f * base + 0.001f * x;    // sigue lentamente el nivel medio
  float s = x - base;
  float f = s;
  for (Notch &n : red) f = n.paso(f);
  float env = envFiltrada.paso(fabsf(f));   // rectificación + media móvil
  float envSin = envCruda.paso(fabsf(s));

  static int n = 0;
  if (++n >= 10) {                      // graficar a 100 Hz
    n = 0;
    Serial.printf("senal:%.0f,envolvente:%.1f,sin_filtro:%.1f\n", f, env, envSin);
  }
}
