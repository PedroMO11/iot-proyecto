// 03c_emg_eventos.ino : calibración + umbral μ+3σ + confirmar / cancelar
const int PIN_EMG = 34;
const uint32_t PERIODO_US = 1000;       // 1 kHz
const int VENTANA = 50;                 // 50 ms
const uint32_t CALIBRACION_MS = 5000;
const uint32_t MIN_MS = 100;            // contracción mínima para confirmar
const uint32_t CANCELAR_MS = 1000;      // más de 1 s = cancelar
const uint32_t REFRACTARIO_MS = 700;
const float MARGEN_MIN = 50;            // umbral ≥ μ + 50: con +20, movimientos chicos en reposo disparaban (antebrazo, 2026-10-21)

float base = 0, buf[VENTANA] = {0}, suma = 0;
int ib = 0;
float umbral = 0;

bool encima = false, cancelEnviado = false;
uint32_t tInicio = 0, tUltimoEvento = 0;

void esperarPeriodo() {
  static uint32_t t = micros();
  while (micros() - t < PERIODO_US) {}
  t += PERIODO_US;
}

float leerEnvolvente() {
  int x = analogRead(PIN_EMG);
  base = 0.999f * base + 0.001f * x;
  float r = fabsf(x - base);
  suma += r - buf[ib];
  buf[ib] = r;
  ib = (ib + 1) % VENTANA;
  return suma / VENTANA;
}

void calibrar() {
  Serial.println("CALIBRANDO: mantén la mandíbula RELAJADA 5 segundos...");
  for (int i = 0; i < 1000; i++) { esperarPeriodo(); leerEnvolvente(); }   // estabilizar
  double s = 0, s2 = 0;
  uint32_t n = 0, t0 = millis();
  while (millis() - t0 < CALIBRACION_MS) {
    esperarPeriodo();
    float e = leerEnvolvente();
    s += e; s2 += (double)e * e; n++;
  }
  float mu = s / n;
  float sigma = sqrt(max(0.0, s2 / n - (double)mu * mu));
  umbral = max(mu + 3 * sigma, mu + MARGEN_MIN);   // margen mínimo por si σ es muy pequeña
  Serial.printf("μ=%.1f σ=%.1f umbral=%.1f\n", mu, sigma, umbral);
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
  bool activo = env > umbral;

  if (activo && !encima && ahora - tUltimoEvento >= REFRACTARIO_MS) {
    encima = true; tInicio = ahora; cancelEnviado = false;
  }
  if (encima) {
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
}
