// RP2040 Modbus RTU 슬레이브 (USB Serial 버전)
// USB (COM6)으로 Modbus RTU 직렬 통신
// Function 3: Read Holding Registers 지원

#include <Arduino.h>

// ===== 센서 데이터 변수 (시뮬레이션용) =====
float temperature = 25.5;      // 온도 (Celsius)
float humidity = 60.0;          // 습도 (%)
int co2_level = 450;            // CO2 농도 (ppm)

// Modbus Holding Registers 배열
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
  // ===== 센서 데이터 시뮬레이션 업데이트 =====
  updateSensorData();

  // ===== Holding Registers 업데이트 =====
  // Register 0: 온도 (×100, 예: 2550 = 25.50°C)
  // Register 1: 습도 (×10, 예: 600 = 60.0%)
  // Register 2: CO2 (ppm)
  // Register 3: 상태 플래그 (1=정상)
  // Register 4: 업데이트 카운터

  holdingRegisters[0] = (uint16_t)(temperature * 100);
  holdingRegisters[1] = (uint16_t)(humidity * 10);
  holdingRegisters[2] = (uint16_t)co2_level;
  holdingRegisters[3] = 1;  // 상태: 1 = 정상
  holdingRegisters[4]++;    // 카운터 증가

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

  // ===== 프레임 완료 감지 및 처리 (Serial.available() 밖에서 체크) =====
  if (rxIndex >= 8 && millis() - lastRxTime > 10) {
    processModbusRequest();
    rxIndex = 0;
  }

  // ===== 디버깅 출력 (Modbus 응답 없을 때만, 1초마다) =====
  static unsigned long lastPrint = 0;
  if (rxIndex == 0 && millis() - lastPrint >= 1000) {
    lastPrint = millis();
    printSensorData();
  }

  // 타임아웃 처리
  if (rxIndex > 0 && millis() - lastRxTime > MODBUS_TIMEOUT) {
    rxIndex = 0;  // 버퍼 초기화
  }

  delay(5);
}

// ===== Modbus RTU 요청 처리 (Function 3: Read Holding Registers) =====
void processModbusRequest() {
  byte slaveID = rxBuffer[0];
  byte function = rxBuffer[1];

  // Slave ID 확인
  if (slaveID != SLAVE_ID) {
    return;
  }

  // Function 3: Read Holding Registers
  if (function == 0x03) {
    uint16_t startAddr = (rxBuffer[2] << 8) | rxBuffer[3];
    uint16_t quantity = (rxBuffer[4] << 8) | rxBuffer[5];

    // CRC 확인 (간단화: 생략)

    // 응답 프레임 생성
    byte txBuffer[32];
    int txIndex = 0;

    txBuffer[txIndex++] = SLAVE_ID;
    txBuffer[txIndex++] = function;
    txBuffer[txIndex++] = quantity * 2;  // Byte count

    // 레지스터 값 추가
    for (int i = 0; i < quantity && (startAddr + i) < 10; i++) {
      uint16_t regValue = holdingRegisters[startAddr + i];
      txBuffer[txIndex++] = (regValue >> 8) & 0xFF;
      txBuffer[txIndex++] = regValue & 0xFF;
    }

    // CRC 계산 및 추가
    uint16_t crc = calculateCRC(txBuffer, txIndex);
    txBuffer[txIndex++] = crc & 0xFF;
    txBuffer[txIndex++] = (crc >> 8) & 0xFF;

    // 응답 전송
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

// ===== 센서 데이터 업데이트 함수 (시뮬레이션) =====
void updateSensorData() {
  // 온도: 25~30°C 변동
  static float tempTrend = 0.1;
  temperature += tempTrend;
  if (temperature > 30.0) tempTrend = -0.1;
  if (temperature < 25.0) tempTrend = 0.1;

  // 습도: 40~70% 변동
  static float humidityTrend = 0.5;
  humidity += humidityTrend;
  if (humidity > 70.0) humidityTrend = -0.5;
  if (humidity < 40.0) humidityTrend = 0.5;

  // CO2: 400~600 ppm 변동
  static int co2Trend = 5;
  co2_level += co2Trend;
  if (co2_level > 600) co2Trend = -5;
  if (co2_level < 400) co2Trend = 5;
}

// ===== 디버깅 출력 함수 =====
void printSensorData() {
  Serial.print("📊 [Slave #1] ");
  Serial.print("온도: ");
  Serial.print(temperature, 2);
  Serial.print("°C | 습도: ");
  Serial.print(humidity, 1);
  Serial.print("% | CO2: ");
  Serial.print(co2_level);
  Serial.print(" ppm | 카운터: ");
  Serial.println(holdingRegisters[4]);
}
