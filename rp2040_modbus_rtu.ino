// RP2040 Modbus RTU 슬레이브 (USB Serial 버전)
// USB (COM6)으로 Modbus RTU 직렬 통신
// 태양광 모듈 시뮬레이션: 전압(23~24V), 전류(1~2A)
// Function 3: Read Holding Registers 지원

#include <Arduino.h>

// ===== 태양광 시뮬레이션 데이터 =====
float voltage = 23.5;   // 전압 (V), 범위: 23.0~24.0
float current = 1.5;    // 전류 (A), 범위: 1.0~2.0

// Modbus Holding Registers 배열
// Register 0: 전압 (×100, 예: 2350 = 23.50V)
// Register 1: 전류 (×100, 예: 150 = 1.50A)
// Register 2: 상태 플래그 (1=정상)
// Register 3: 업데이트 카운터
uint16_t holdingRegisters[10] = {0};

// 통신 설정
#define MODBUS_BAUD 9600
#define SLAVE_ID 1
#define MODBUS_TIMEOUT 1000  // 1초

// Modbus 버퍼
byte rxBuffer[32];
int rxIndex = 0;
unsigned long lastRxTime = 0;

void setup() {
  // USB Serial을 Modbus RTU로 사용 (9600 baud)
  Serial.begin(MODBUS_BAUD);
  delay(1000);

  // LED 핀 (디버깅용)
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);

  // 초기화 완료 신호 (LED 깜빡임)
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_BUILTIN, LOW);
    delay(100);
    digitalWrite(LED_BUILTIN, HIGH);
    delay(100);
  }
}

void loop() {
  // ===== 태양광 데이터 시뮬레이션 업데이트 =====
  updateSolarData();

  // ===== Holding Registers 업데이트 =====
  holdingRegisters[0] = (uint16_t)(voltage * 100);   // 전압 ×100
  holdingRegisters[1] = (uint16_t)(current * 100);   // 전류 ×100
  holdingRegisters[2] = 1;                            // 상태: 1 = 정상
  holdingRegisters[3]++;                              // 카운터 증가

  // ===== Modbus RTU 요청 수신 =====
  while (Serial.available()) {
    byte data = Serial.read();
    rxBuffer[rxIndex++] = data;
    lastRxTime = millis();

    // 버퍼 오버플로우 방지
    if (rxIndex >= 32) {
      rxIndex = 0;
    }
  }

  // ===== 프레임 완료 감지 및 처리 =====
  if (rxIndex >= 8 && millis() - lastRxTime > 10) {
    processModbusRequest();
    rxIndex = 0;
  }

  // ===== 디버깅 출력 (1초마다) =====
  static unsigned long lastPrint = 0;
  if (rxIndex == 0 && millis() - lastPrint >= 1000) {
    lastPrint = millis();
    printSolarData();
  }

  // 타임아웃 처리
  if (rxIndex > 0 && millis() - lastRxTime > MODBUS_TIMEOUT) {
    rxIndex = 0;
  }

  delay(5);
}

// ===== Modbus RTU 요청 처리 (Function 3: Read Holding Registers) =====
void processModbusRequest() {
  byte slaveID = rxBuffer[0];
  byte function = rxBuffer[1];

  if (slaveID != SLAVE_ID) {
    return;
  }

  if (function == 0x03) {
    uint16_t startAddr = (rxBuffer[2] << 8) | rxBuffer[3];
    uint16_t quantity  = (rxBuffer[4] << 8) | rxBuffer[5];

    byte txBuffer[32];
    int txIndex = 0;

    txBuffer[txIndex++] = SLAVE_ID;
    txBuffer[txIndex++] = function;
    txBuffer[txIndex++] = quantity * 2;  // Byte count

    for (int i = 0; i < quantity && (startAddr + i) < 10; i++) {
      uint16_t regValue = holdingRegisters[startAddr + i];
      txBuffer[txIndex++] = (regValue >> 8) & 0xFF;
      txBuffer[txIndex++] = regValue & 0xFF;
    }

    uint16_t crc = calculateCRC(txBuffer, txIndex);
    txBuffer[txIndex++] = crc & 0xFF;
    txBuffer[txIndex++] = (crc >> 8) & 0xFF;

    Serial.write(txBuffer, txIndex);
    Serial.flush();

    // LED 깜빡임 (통신 표시)
    digitalWrite(LED_BUILTIN, LOW);
    delay(50);
    digitalWrite(LED_BUILTIN, HIGH);
  }
}

// ===== CRC-16 계산 =====
uint16_t calculateCRC(byte* data, int len) {
  uint16_t crc = 0xFFFF;
  for (int i = 0; i < len; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 0x0001) {
        crc = (crc >> 1) ^ 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

// ===== 태양광 데이터 시뮬레이션 =====
void updateSolarData() {
  // 전압: 23.0~24.0V 변동
  static float voltageTrend = 0.05;
  voltage += voltageTrend;
  if (voltage > 24.0) voltageTrend = -0.05;
  if (voltage < 23.0) voltageTrend =  0.05;

  // 전류: 1.0~2.0A 변동
  static float currentTrend = 0.05;
  current += currentTrend;
  if (current > 2.0) currentTrend = -0.05;
  if (current < 1.0) currentTrend =  0.05;
}

// ===== 디버깅 출력 =====
void printSolarData() {
  Serial.print("[Slave #1] ");
  Serial.print("전압: ");
  Serial.print(voltage, 2);
  Serial.print("V | 전류: ");
  Serial.print(current, 2);
  Serial.print("A | 카운터: ");
  Serial.println(holdingRegisters[3]);
}
