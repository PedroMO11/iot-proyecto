// 03c_emg_eventos.ino : filtro de la red + calibración + umbral μ+3σ con histéresis + confirmar / cancelar
// Filtra la red eléctrica igual que 03c_emg_senal: el 2026-10-28, en el salón, sin el filtro el reposo
// se movía de 240 a 150 después de calibrar; con el filtro quedó estable en ~30.
const int PIN_EMG = 34;
const uint32_t PERIODO_US = 1000;       // 1 kHz
const float FS = 1000.0;
const int VENTANA = 50;                 // 50 ms
const uint32_t CALIBRACION_MS = 5000;
const uint32_t MIN_MS = 100;            // contracción mínima para confirmar
const uint32_t CANCELAR_MS = 1000;      // más de 1 s = cancelar
const uint32_t REFRACTARIO_MS = 700;
const float MARGEN_MIN = 50;            // umbral ≥ μ + 50: con +20, movimientos chicos en reposo disparaban (antebrazo, 2026-10-21)
const float HISTERESIS = 0.5;           // la contracción termina al bajar de μ + 0,5·(umbral − μ): con un solo umbral, en el salón
                                        // (2026-10-28) los apretones largos oscilaban alrededor del umbral y daban CONFIRMAR, no CANCELAR
const bool GRAFICAR = false;            // true: envolvente y umbrales para el Serial Plotter (100 Hz)

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

float base = 0, buf[VENTANA] = {0}, suma = 0;
int ib = 0;
float umbral = 0, umbralBajo = 0;
uint32_t saturadas = 0;                 // muestras en los extremos del ADC (señal recortada)

bool encima = false, cancelEnviado = false;
uint32_t tInicio = 0, tUltimoEvento = 0;

void esperarPeriodo() {
  static uint32_t t = micros();
  while (micros() - t < PERIODO_US) {}
  t += PERIODO_US;
}

float leerEnvolvente() {
  int x = analogRead(PIN_EMG);
  if (x <= 5 || x >= 4090) saturadas++;
  base = 0.999f * base + 0.001f * x;
  float f = x - base;
  for (Notch &n : red) f = n.paso(f);
  float r = fabsf(f);
  suma += r - buf[ib];
  buf[ib] = r;
  ib = (ib + 1) % VENTANA;
  return suma / VENTANA;
}

void calibrar() {
  Serial.println("CALIBRANDO: mantén la mandíbula RELAJADA 5 segundos...");
  for (int i = 0; i < 1000; i++) { esperarPeriodo(); leerEnvolvente(); }   // estabilizar (filtros y media móvil)
  double s = 0, s2 = 0;
  uint32_t n = 0, t0 = millis();
  saturadas = 0;
  while (millis() - t0 < CALIBRACION_MS) {
    esperarPeriodo();
    float e = leerEnvolvente();
    s += e; s2 += (double)e * e; n++;
  }
  float mu = s / n;
  float sigma = sqrt(max(0.0, s2 / n - (double)mu * mu));
  umbral = max(mu + 3 * sigma, mu + MARGEN_MIN);   // margen mínimo por si σ es muy pequeña
  umbralBajo = mu + HISTERESIS * (umbral - mu);
  float pctSat = 100.0 * saturadas / n;
  Serial.printf("μ=%.1f σ=%.1f umbral=%.1f (termina bajo %.1f) saturadas=%.1f %%\n", mu, sigma, umbral, umbralBajo, pctSat);
  if (pctSat > 1) Serial.println("AVISO: la señal toca los extremos del ADC. Revisar el electrodo y el cable de 3,5 mm; si sigue, es ruido de la red");
}

void setup() {
  Serial.begin(115200);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_EMG, ADC_11db);
  long acc = 0;
  for (int i = 0; i < 1000; i++) { acc += analogRead(PIN_EMG); delayMicroseconds(1000); }
  base = acc / 1000.0;
  calibrar();
}

void loop() {
  esperarPeriodo();
  float env = leerEnvolvente();
  uint32_t ahora = millis();

  if (!encima && env > umbral && ahora - tUltimoEvento >= REFRACTARIO_MS) {
    encima = true; tInicio = ahora; cancelEnviado = false;
  }
  if (encima) {
    bool activo = env > umbralBajo;
    uint32_t dur = ahora - tInicio;
    if (activo && !cancelEnviado && dur > CANCELAR_MS) {
      Serial.println(">>> CANCELAR");
      cancelEnviado = true;
    }
    if (!activo) {
      if (!cancelEnviado && dur >= MIN_MS) Serial.println(">>> CONFIRMAR");
      if (cancelEnviado || dur >= MIN_MS) tUltimoEvento = ahora;
      encima = false;
    }
  }

  static int n = 0;
  if (GRAFICAR && ++n >= 10) {          // graficar a 100 Hz
    n = 0;
    Serial.printf("envolvente:%.1f,umbral:%.1f,umbral_bajo:%.1f\n", env, umbral, umbralBajo);
  }
}
