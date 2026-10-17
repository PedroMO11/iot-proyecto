// 04a_rele.ino : conmuta el relé cada 2 s
const int PIN_RELE = 26;
void setup() {
  Serial.begin(115200);
  pinMode(PIN_RELE, OUTPUT);
}
void loop() {
  digitalWrite(PIN_RELE, HIGH); Serial.println("IN = HIGH"); delay(2000);
  digitalWrite(PIN_RELE, LOW);  Serial.println("IN = LOW");  delay(2000);
}
