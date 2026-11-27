#include <Adafruit_MLX90614.h>
#include <Wire.h>

Adafruit_MLX90614 thermometer;
bool thermometerFound;

void setup() {
  Serial.begin(9600);
  Wire.begin(D2, D1);  // SDA, SCL
  thermometerFound = thermometer.begin();
}

void loop() {
  if (thermometerFound) {
    const double ambient = thermometer.readAmbientTempC();
    if (isfinite(ambient)) {
      Serial.print(F("Ambient: "));
      Serial.print(ambient, 1);
      Serial.println(F(" C"));
    } else {
      Serial.println(F("MLX90614 read failed"));
    }
  } else {
    Serial.println(F("MLX90614 not found; check D2/SDA, D1/SCL, 3V and GND"));
  }

  delay(1000);
}
