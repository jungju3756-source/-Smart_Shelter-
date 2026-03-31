#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YOLO 감지 결과 → RP2040 #2 LED 제어
- 사람 감지 시 Modbus FC5 Coil ON → LED ON (에어컨 가동)
- 300초 동안 사람 미감지 시 Coil OFF → LED OFF (에어컨 정지)
- 통신: USB-RS485 어댑터 → /dev/ttyUSB0 → RP2040 #2
"""

import serial
import time
from datetime import datetime
import sys
import os

# ===== 설정 =====
MODBUS_PORT  = '/dev/ttyACM1'   # USB-RS485 어댑터 포트
MODBUS_BAUD  = 9600
SLAVE_ID     = 1                # RP2040 #2 Slave ID
LED_COIL_ADDRESS  = 0           # Coil 0: LED (에어컨 코일 시뮬레이션)
NO_PERSON_TIMEOUT = 5          # 사람 없음 유지 시 OFF까지 대기 시간 (초) - 테스트용

LOG_DIR = os.path.expanduser('~/smart_shelter/logs')
os.makedirs(LOG_DIR, exist_ok=True)


class LEDController:
    """RP2040 #2 LED Modbus 제어 클래스"""

    def __init__(self):
        self.serial_conn = None
        self.current_state = False          # False=OFF, True=ON
        self.last_person_time = None
        self.control_count = 0

    def connect(self):
        """Modbus 직렬 연결"""
        try:
            self.serial_conn = serial.Serial(
                port=MODBUS_PORT,
                baudrate=MODBUS_BAUD,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2
            )
            print(f"✓ Modbus 연결 완료: {MODBUS_PORT}")
            return True
        except serial.SerialException as e:
            print(f"❌ Modbus 연결 오류: {e}")
            print("   USB-RS485 어댑터 연결 확인: /dev/ttyUSB0 또는 /dev/ttyUSB1")
            return False

    def calculate_crc(self, data):
        """Modbus CRC-16"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def write_coil(self, coil_address, value):
        """Modbus FC5: Write Single Coil → LED ON/OFF"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("❌ Modbus 연결 없음")
            return False

        frame = bytearray([
            SLAVE_ID,
            0x05,
            0x00,
            coil_address & 0xFF,
            0xFF if value else 0x00,
            0x00
        ])
        crc = self.calculate_crc(frame)
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)

        try:
            self.serial_conn.write(bytes(frame))
            self.serial_conn.flush()
            state_str = "ON" if value else "OFF"
            print(f"송신: {' '.join(f'{b:02X}' for b in frame)}")
            print(f"→ LED {state_str} (에어컨 {'가동' if value else '정지'})")
            self._log(value)
            self.current_state = value
            self.control_count += 1
            return True
        except serial.SerialException as e:
            print(f"❌ 전송 오류: {e}")
            return False

    def set_led(self, turn_on):
        """LED ON/OFF (상태 변경 시에만 전송)"""
        if turn_on == self.current_state:
            return
        self.write_coil(LED_COIL_ADDRESS, turn_on)

    def update(self, person_detected):
        """
        YOLO 감지 결과 업데이트
        - person_detected=True  → LED ON
        - person_detected=False → 300초 후 LED OFF
        """
        if person_detected:
            self.last_person_time = time.time()
            if not self.current_state:
                print("사람 감지 → LED ON")
                self.set_led(True)
        else:
            if self.last_person_time is None:
                return
            elapsed = time.time() - self.last_person_time
            remaining = NO_PERSON_TIMEOUT - elapsed
            if remaining > 0:
                print(f"사람 없음 ({elapsed:.0f}초 경과, {remaining:.0f}초 후 OFF)")
            else:
                print(f"사람 없음 {NO_PERSON_TIMEOUT}초 초과 → LED OFF")
                self.set_led(False)
                self.last_person_time = None

    def _log(self, state):
        """제어 로그 저장"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = os.path.join(LOG_DIR, 'led_control.log')
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] LED {'ON' if state else 'OFF'} | #{self.control_count + 1}\n")

    def close(self):
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Modbus 연결 종료")


def main():
    """camera_detection.py 와 통합 실행용 메인"""
    print("\n========================================")
    print("  YOLO → Modbus LED 제어")
    print("========================================")
    print(f"포트: {MODBUS_PORT}  Slave ID: {SLAVE_ID}")
    print(f"OFF 타임아웃: {NO_PERSON_TIMEOUT}초")
    print("========================================\n")

    controller = LEDController()

    if not controller.connect():
        print("⚠️  연결 실패 - USB-RS485 어댑터 확인 후 재시작")
        sys.exit(1)

    # camera_detection.py 에서 stdin으로 "PERSON" / "EMPTY" 수신
    print("camera_detection.py 출력 대기 중 (stdin)...\n")
    try:
        for line in sys.stdin:
            line = line.strip()
            if line == "PERSON":
                controller.update(True)
            elif line == "EMPTY":
                controller.update(False)
    except KeyboardInterrupt:
        print("\n종료 (Ctrl+C)")
    finally:
        controller.close()
        print(f"총 제어 횟수: {controller.control_count}회")


if __name__ == "__main__":
    main()
