// Arduino Nano RP2040 Connect - Modbus RTU 슬레이브
// 역할: Zorin OS에서 FC5 Coil 명령 수신 → RGB LED ON/OFF
// 통신: USB Serial (9600 baud)
// LED: WiFiNINA RGB (사람 있음=녹색, 없음=빨간색)

#include <Arduino.h>
#include <WiFiNINA.h>

#define SLAVE_ID    1
#define MODBUS_BAUD 9600

bool ledState = false;

byte rxBuffer[32];
int  rxIndex = 0;
unsigned long lastRxTime = 0;

uint16_t calculateCRC(byte* data, int len) {
  uint16_t crc = 0xFFFF;
  for (int i = 0; i < len; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 0x0001) crc = (crc >> 1) ^ 0xA001;
      else              crc >>= 1;
    }
  }
  return crc;
}

void setLED(bool on) {
  if (on) {
    // 사람 감지 → 빨간색
    digitalWrite(LEDR, LOW);
    digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, HIGH);
  } else {
    // 사람 없음 → 꺼짐
    digitalWrite(LEDR, HIGH);
    digitalWrite(LEDG, HIGH);
    digitalWrite(LEDB, HIGH);
  }
}

void setup() {
  Serial.begin(MODBUS_BAUD);
  delay(1000);

  // RGB LED 핀 설정 (LOW=켜짐, HIGH=꺼짐)
  pinMode(LEDR, OUTPUT);
  pinMode(LEDG, OUTPUT);
  pinMode(LEDB, OUTPUT);

  // 초기 상태: 꺼짐
  setLED(false);
}

void loop() {
  while (Serial.available()) {
    byte b = Serial.read();
    if (rxIndex < 32) rxBuffer[rxIndex++] = b;
    lastRxTime = millis();
  }

  // 8바이트 이상 + 10ms 침묵 → 프레임 완성
  if (rxIndex >= 8 && millis() - lastRxTime > 10) {
    processRequest();
    rxIndex = 0;
  }

  // 타임아웃
  if (rxIndex > 0 && millis() - lastRxTime > 1000) {
    rxIndex = 0;
  }
}

void processRequest() {
  if (rxBuffer[0] != SLAVE_ID) return;

  byte func = rxBuffer[1];

  // FC5: Write Single Coil
  if (func == 0x05) {
    uint16_t coilAddr = (rxBuffer[2] << 8) | rxBuffer[3];
    uint16_t coilVal  = (rxBuffer[4] << 8) | rxBuffer[5];

    if (coilAddr == 0x0000) {
      ledState = (coilVal == 0xFF00);
      setLED(ledState);
    }

    // 에코 응답
    Serial.write(rxBuffer, 8);
    Serial.flush();
  }

  // FC1: Read Coils
  else if (func == 0x01) {
    byte tx[6];
    tx[0] = SLAVE_ID;
    tx[1] = 0x01;
    tx[2] = 0x01;
    tx[3] = ledState ? 0x01 : 0x00;
    uint16_t crc = calculateCRC(tx, 4);
    tx[4] = crc & 0xFF;
    tx[5] = (crc >> 8) & 0xFF;
    Serial.write(tx, 6);
    Serial.flush();
  }
}
