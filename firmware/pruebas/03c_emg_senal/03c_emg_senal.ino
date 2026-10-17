// 03c_emg_senal.ino : muestreo a 1 kHz, rectificación y envolvente
const int PIN_EMG = 34;
const uint32_t PERIODO_US = 1000;       // 1 kHz
const int VENTANA = 50;                 // media móvil de 50 ms

float base = 0;                         // nivel de reposo (~1,5 V)
float buf[VENTANA] = {0};
float suma = 0;
int ib = 0;

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
  float r = fabsf(x - base);            // rectificación
  suma += r - buf[ib];                  // media móvil
  buf[ib] = r;
  ib = (ib + 1) % VENTANA;
  float env = suma / VENTANA;

  static int n = 0;
  if (++n >= 10) {                      // graficar a 100 Hz
    n = 0;
    Serial.printf("senal:%.0f,envolvente:%.1f\n", x - base, env);
  }
}
