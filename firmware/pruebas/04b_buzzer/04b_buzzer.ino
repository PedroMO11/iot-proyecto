// 04b_buzzer.ino : patrón de alerta
const int PIN_BUZZER = 27;
void setup() { pinMode(PIN_BUZZER, OUTPUT); }
void loop() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(PIN_BUZZER, HIGH); delay(200);
    digitalWrite(PIN_BUZZER, LOW);  delay(200);
  }
  delay(3000);
}
