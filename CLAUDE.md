# CLAUDE.md

이 파일은 Claude Code(claude.ai/code)가 이 저장소의 코드로 작업할 때 필요한 안내를 제공합니다.

## 프로젝트 개요

이것은 **RP2040** 마이크로컨트롤러(Raspberry Pi Pico 또는 호환 보드)에서 **Modbus RTU** 통신을 구현하는 Arduino 프로젝트입니다. Modbus RTU는 산업용 자동화 및 IoT 애플리케이션에서 일반적으로 사용되는 직렬 기반 마스터-슬레이브 프로토콜입니다.

## 개발 환경 설정

### 필수 사항
- **Arduino IDE** (2.0+) RP2040 보드 지원 설치됨
  - 보드 관리자에서 설치: `Raspberry Pi → Pico/RP2040` (by Earle F. Philhower)
- **USB 케이블** (RP2040 보드에 업로드용)
- **직렬 모니터** 또는 터미널 (Arduino IDE 또는 별도 도구)

### 빌드 및 업로드

**Arduino IDE에서:**
1. `rp2040_modbus_rtu.ino` 열기
2. **Tools → Board → Raspberry Pi Pico** 선택
3. **Tools → Port → COM (RP2040)** 선택
4. **Sketch → Upload** (Ctrl+U) 또는 업로드 버튼 클릭

**명령줄 빌드** (Arduino CLI 사용):
```bash
arduino-cli compile --fqbn rduino:rp2040:rpipico rp2040_modbus_rtu.ino
arduino-cli upload --port COM3 --fqbn arduino:rp2040:rpipico rp2040_modbus_rtu.ino
```
(COM3를 실제 포트로 변경)

## 아키텍처 및 코드 구조

### Modbus RTU 기본 사항
- **프로토콜**: Modbus RTU (원격 터미널 장치)는 RS-485 또는 UART 직렬을 통해 통신
- **마스터**: 슬레이브에서 데이터 요청 (일반적으로 PC 또는 산업용 컨트롤러)
- **슬레이브**: 요청에 응답하고 홀딩 레지스터/코일 관리
- **전송 속도**: 일반적으로 9600, 19200, 또는 38400 bps; 마스터와 슬레이브 간 일치해야 함

### 예상 프로젝트 구조
```
rp2040_modbus_rtu.ino          # 메인 스케치 파일
├── setup()                    # 직렬, Modbus 라이브러리, 주변장치 초기화
├── loop()                     # Modbus 이벤트 폴링 및 상태 처리
└── (미래: 모듈식 코드를 위한 별도 .cpp/.h)

Modbus Poll/       # MbPoll 테스트 도구 (Windows) - 마스터/클라이언트 시뮬레이션
Modbus Slave/      # MbSlave 테스트 도구 (Windows) - 슬레이브/서버 시뮬레이션
```

### 라이브러리 및 의존성
Arduino용 일반적인 Modbus RTU 라이브러리:
- **ArduinoModbus** (공식, RP2040 지원)
- **ModbusMaster** (Nick O'Leary)
- **ModbusRTU** (다양한 구현)

라이브러리 추가 방법:
1. Arduino IDE에서 **Tools → Manage Libraries**
2. 라이브러리 이름 검색 및 설치
3. 스케치에서 라이브러리 헤더 `#include`

### 개발 워크플로우

**Modbus 슬레이브 (RP2040이 마스터에 응답):**
1. 레지스터 배열을 사용하는 Modbus 슬레이브 핸들러 구현
2. UART/RS-485 설정 구성
3. MbPoll (마스터 시뮬레이터, `Modbus Poll/` 디렉토리)으로 테스트

**Modbus 마스터 (RP2040이 요청 시작):**
1. Modbus 마스터 요청 구현 (읽기/쓰기 레지스터)
2. UART/RS-485 설정 구성
3. MbSlave (슬레이브 시뮬레이터, `Modbus Slave/` 디렉토리)로 테스트

### 직렬 통신
- RP2040은 여러 UART 주변장치 (UART0, UART1)를 가짐
- 기본값: **GPIO0 (TX) 및 GPIO1 (RX)의 UART0**
- 일반적인 설정:
  ```cpp
  Serial1.begin(9600, SERIAL_8N1);  // 9600 baud, 8 data, no parity, 1 stop
  ```

### 디버깅
- **Serial.print()** 문을 사용하고 **Tools → Serial Monitor**로 보기 (USB 기본 115200 baud)
- Modbus 디버깅의 경우, 프레임 데이터(원본 바이트)를 로깅하여 프로토콜 흐름 이해
- 포함된 Windows 테스트 도구 (MbPoll/MbSlave)로 테스트

## RP2040 주요 고려 사항

- **듀얼 코어**: RP2040은 두 개의 ARM Cortex-M0+ 코어를 가짐; 기본적으로 Arduino IDE는 코어 0만 사용
- **제한된 RAM**: 총 264KB; Modbus 프레임의 버퍼 크기 제한 주의
- **핀 맵핑**: GPIO 번호가 일부 보드와 다름; 데이터시트에서 핀아웃 확인
- **전원**: 개발 시 일반적으로 USB 전원; 산업용 배포 시 규제된 5V 전원 필요

## 포함된 테스트 도구

- **MbPoll_v7.1.0_cracked.exe**: Modbus 마스터 쿼리 전송을 위한 Windows 유틸리티 (요청/응답 시뮬레이션)
- **MbSlave_v6.2.0_cracked.exe**: Modbus 슬레이브로 작동하는 Windows 유틸리티 (디바이스 시뮬레이터)

두 도구 모두 PC 측 코드를 작성하지 않고 직렬 통신을 확인하는 데 도움이 됩니다.

## 향후 개발

메인 스케치 구현 시:
1. 레지스터 레이아웃 정의 (코일, 이산 입력, 홀딩 레지스터, 입력 레지스터)
2. 마스터 또는 슬레이브 모드 선택 (또는 모드 전환 포함)
3. 에러 처리 구현 (CRC, 타임아웃, 유효하지 않은 주소)
4. 애플리케이션별 로직 추가 (센서 읽기, 릴레이 제어 등)

## 코드 스타일 규칙

### 커밋 메시지
- **커밋 메시지는 한글로 작성**
- 변경 사항과 이유를 설명하는 명확하고 설명적인 제목 사용
- 예시: `기능: Modbus RTU 슬레이브 모드 구현` 또는 `수정: 시리얼 통신 타임아웃 버그`
