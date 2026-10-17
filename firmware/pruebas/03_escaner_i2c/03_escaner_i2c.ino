// 03_escaner_i2c.ino
#include <Wire.h>
void setup() {
  Serial.begin(115200);
  Wire.begin(21, 22);                     // SDA, SCL
  delay(500);
  Serial.println("Escaneando I2C...");
  for (uint8_t dir = 1; dir < 127; dir++) {
    Wire.beginTransmission(dir);
    if (Wire.endTransmission() == 0) Serial.printf("Dispositivo en 0x%02X\n", dir);
  }
  Serial.println("Fin");
}
void loop() {}
