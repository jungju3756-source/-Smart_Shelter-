// RP2040 #2: Modbus RTU 마스터
// 역할: RP2040 #1 (슬레이브)에서 데이터를 읽고, 에어컨 Coil 제어

#include <Arduino.h>

// ===== Modbus RTU 마스터 설정 =====
#define SLAVE_ID 1          // 통신 대상 슬레이브 ID
#define MODBUS_BAUD 9600    // 통신 속도

// ===== 핀 설정 =====
#define RS485_DE_PIN 2      // 방향 제어 핀 (Driver Enable)
#define RS485_RE_PIN 3      // 수신 활성화 핀 (Receiver Enable)

// ===== Modbus Coil 주소 =====
#define COIL_AIRCOND_ON 0   // 코일 0: 에어컨 ON/OFF (False=OFF, True=ON)
#define COIL_LIGHT_ON 1     // 코일 1: 조명 ON/OFF

// ===== 데이터 버퍼 =====
byte txBuffer[8];           // 전송 버퍼
byte rxBuffer[32];          // 수신 버퍼
int rxIndex = 0;            // 수신 인덱스
unsigned long lastModbusTime = 0;

// ===== 읽어온 데이터 =====
uint16_t slaveTemperature = 0;   // 슬레이브의 온도 (×100)
uint16_t slaveHumidity = 0;      // 슬레이브의 습도 (×10)
uint16_t slaveCO2 = 0;           // 슬레이브의 CO2 (ppm)

// ===== 제어 상태 =====
bool airconditionerON = false;   // 에어컨 상태

void setup() {
  // 디버깅용 USB Serial (115200)
  Serial.begin(115200);
  delay(2000);

  Serial.println("\n========================================");
  Serial.println("  RP2040 Modbus RTU 마스터 초기화");
  Serial.println("========================================");
  Serial.println("포트: COM (미결정)");
  Serial.println("역할: 슬레이브 #1과 통신");
  Serial.println("통신 속도: 9600 baud");
  Serial.println("인터페이스: UART0 (GPIO0/1)");
  Serial.println("========================================\n");

  // RS-485 방향 제어 핀 설정
  pinMode(RS485_DE_PIN, OUTPUT);
  pinMode(RS485_RE_PIN, OUTPUT);
  digitalWrite(RS485_DE_PIN, LOW);   // 초기: 수신 모드
  digitalWrite(RS485_RE_PIN, LOW);

  // UART0 초기화 (GPIO0=TX, GPIO1=RX)
  Serial1.begin(MODBUS_BAUD);

  Serial.println("✓ UART0 초기화 완료 (9600 baud)");
  Serial.println("✓ RS-485 핀 설정 완료");
  Serial.println("✓ Modbus RTU 마스터 준비 완료\n");

  Serial.println("명령어 입력:");
  Serial.println("  'r' : 슬레이브에서 데이터 READ");
  Serial.println("  'o' : 에어컨 ON");
  Serial.println("  'f' : 에어컨 OFF");
  Serial.println("  'i' : 상태 정보\n");
}

void loop() {
  // USB Serial에서 명령어 입력 처리
  if (Serial.available()) {
    char cmd = Serial.read();
    Serial.print("명령: ");
    Serial.println(cmd);

    switch (cmd) {
      case 'r':
        readSlaveData();  // 슬레이브 데이터 읽기
        break;
      case 'o':
        writeCoil(COIL_AIRCOND_ON, true);   // 에어컨 ON
        break;
      case 'f':
        writeCoil(COIL_AIRCOND_ON, false);  // 에어컨 OFF
        break;
      case 'i':
        printStatus();  // 상태 출력
        break;
      default:
        Serial.println("❌ 알 수 없는 명령어");
        break;
    }
  }

  // 주기적으로 슬레이브 데이터 읽기 (2초마다)
  static unsigned long lastRead = 0;
  if (millis() - lastRead >= 2000) {
    lastRead = millis();
    readSlaveData();
  }

  // Modbus 응답 처리
  if (Serial1.available()) {
    processModbusResponse();
  }

  delay(10);
}

// ===== Modbus Function 3: Read Holding Registers =====
// 슬레이브에서 Holding Registers 읽기
void readSlaveData() {
  Serial.println("\n📤 [마스터] 슬레이브 데이터 요청...");

  // Modbus RTU 요청 프레임 생성
  // Function 3: Read Holding Registers (0x03)
  // Frame: [Slave ID][Function][Start Address High][Start Address Low]
  //        [Quantity High][Quantity Low][CRC Low][CRC High]

  byte slaveID = SLAVE_ID;
  byte function = 0x03;  // Read Holding Registers
  byte startAddr_H = 0x00;  // 시작 주소 0
  byte startAddr_L = 0x00;
  byte quantity_H = 0x00;   // 읽을 레지스터 개수: 5개
  byte quantity_L = 0x05;

  // CRC 계산
  uint16_t crc = calculateCRC(slaveID, function, startAddr_H, startAddr_L,
                              quantity_H, quantity_L);
  byte crc_L = crc & 0xFF;
  byte crc_H = (crc >> 8) & 0xFF;

  // 전송
  digitalWrite(RS485_DE_PIN, HIGH);  // 송신 모드
  digitalWrite(RS485_RE_PIN, HIGH);
  delay(5);

  Serial1.write(slaveID);
  Serial1.write(function);
  Serial1.write(startAddr_H);
  Serial1.write(startAddr_L);
  Serial1.write(quantity_H);
  Serial1.write(quantity_L);
  Serial1.write(crc_L);
  Serial1.write(crc_H);
  Serial1.flush();

  digitalWrite(RS485_DE_PIN, LOW);   // 수신 모드
  digitalWrite(RS485_RE_PIN, LOW);

  Serial.println("✓ 요청 전송 완료, 응답 대기 중...");
  lastModbusTime = millis();
}

// ===== Modbus Function 5: Write Single Coil =====
// 슬레이브의 Coil 쓰기
void writeCoil(int coilAddress, bool value) {
  Serial.println("\n📤 [마스터] Coil 쓰기 명령...");

  // Function 5: Write Single Coil (0x05)
  // Frame: [Slave ID][Function][Coil Address High][Coil Address Low]
  //        [Value High][Value Low][CRC Low][CRC High]

  byte slaveID = SLAVE_ID;
  byte function = 0x05;  // Write Single Coil
  byte coilAddr_H = 0x00;
  byte coilAddr_L = coilAddress & 0xFF;
  byte value_H = value ? 0xFF : 0x00;
  byte value_L = 0x00;

  // CRC 계산
  uint16_t crc = calculateCRCWrite(slaveID, function, coilAddr_H, coilAddr_L,
                                    value_H, value_L);
  byte crc_L = crc & 0xFF;
  byte crc_H = (crc >> 8) & 0xFF;

  // 전송
  digitalWrite(RS485_DE_PIN, HIGH);  // 송신 모드
  digitalWrite(RS485_RE_PIN, HIGH);
  delay(5);

  Serial1.write(slaveID);
  Serial1.write(function);
  Serial1.write(coilAddr_H);
  Serial1.write(coilAddr_L);
  Serial1.write(value_H);
  Serial1.write(value_L);
  Serial1.write(crc_L);
  Serial1.write(crc_H);
  Serial1.flush();

  digitalWrite(RS485_DE_PIN, LOW);   // 수신 모드
  digitalWrite(RS485_RE_PIN, LOW);

  Serial.print("✓ Coil ");
  Serial.print(coilAddress);
  Serial.print(" = ");
  Serial.println(value ? "ON" : "OFF");

  airconditionerON = (coilAddress == COIL_AIRCOND_ON) ? value : airconditionerON;
  lastModbusTime = millis();
}

// ===== Modbus 응답 처리 =====
void processModbusResponse() {
  byte data = Serial1.read();
  rxBuffer[rxIndex++] = data;

  // 타임아웃 체크 (1초)
  if (millis() - lastModbusTime > 1000) {
    Serial.println("❌ Modbus 응답 타임아웃");
    rxIndex = 0;
    return;
  }

  // Function 3 응답 처리 (Read Holding Registers)
  if (rxIndex >= 11 && rxBuffer[1] == 0x03) {
    byte slaveID = rxBuffer[0];
    byte function = rxBuffer[1];
    byte byteCount = rxBuffer[2];

    if (slaveID == SLAVE_ID && function == 0x03) {
      // 레지스터 값 추출
      slaveTemperature = (rxBuffer[3] << 8) | rxBuffer[4];
      slaveHumidity = (rxBuffer[5] << 8) | rxBuffer[6];
      slaveCO2 = (rxBuffer[7] << 8) | rxBuffer[8];

      Serial.println("\n📥 [마스터] 슬레이브 데이터 수신:");
      Serial.print("  온도: ");
      Serial.print(slaveTemperature / 100.0, 2);
      Serial.println("°C");
      Serial.print("  습도: ");
      Serial.print(slaveHumidity / 10.0, 1);
      Serial.println("%");
      Serial.print("  CO2: ");
      Serial.print(slaveCO2);
      Serial.println(" ppm\n");

      rxIndex = 0;
    }
  }
}

// ===== CRC 계산 함수 (Read) =====
uint16_t calculateCRC(byte id, byte func, byte addr_H, byte addr_L,
                      byte qty_H, byte qty_L) {
  byte data[] = {id, func, addr_H, addr_L, qty_H, qty_L};
  return modbusCRC(data, 6);
}

// ===== CRC 계산 함수 (Write) =====
uint16_t calculateCRCWrite(byte id, byte func, byte addr_H, byte addr_L,
                           byte val_H, byte val_L) {
  byte data[] = {id, func, addr_H, addr_L, val_H, val_L};
  return modbusCRC(data, 6);
}

// ===== Modbus CRC-16 계산 =====
uint16_t modbusCRC(byte *data, int len) {
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

// ===== 상태 정보 출력 =====
void printStatus() {
  Serial.println("\n========================================");
  Serial.println("  마스터 상태 정보");
  Serial.println("========================================");
  Serial.print("슬레이브 ID: ");
  Serial.println(SLAVE_ID);
  Serial.print("통신 속도: ");
  Serial.println(MODBUS_BAUD);
  Serial.print("에어컨 상태: ");
  Serial.println(airconditionerON ? "ON ✓" : "OFF");
  Serial.println("\n읽어온 슬레이브 데이터:");
  Serial.print("  온도: ");
  Serial.print(slaveTemperature / 100.0, 2);
  Serial.println("°C");
  Serial.print("  습도: ");
  Serial.print(slaveHumidity / 10.0, 1);
  Serial.println("%");
  Serial.print("  CO2: ");
  Serial.print(slaveCO2);
  Serial.println(" ppm");
  Serial.println("========================================\n");
}
