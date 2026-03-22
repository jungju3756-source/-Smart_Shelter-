#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YOLO 감지 결과 + Modbus 에어컨 제어
- YOLO에서 사람 감지 결과 수신
- 감지 상태에 따라 에어컨 ON/OFF 제어
- Modbus RTU를 통해 RP2040 #2로 제어 명령 전송
"""

import serial
import time
from datetime import datetime
import sys
import os

# ===== 설정 =====
# Modbus 연결 설정
MODBUS_PORT = '/dev/ttyUSB0'  # Zorin OS 직렬 포트 (USB-RS485 어댑터)
MODBUS_BAUD = 9600
SLAVE_ID = 1  # RP2040 #2 (마스터가 아니라 슬레이브로 설정 필요)

# 에어컨 제어 설정
AIRCOND_COIL_ADDRESS = 0  # Coil 0: 에어컨 ON/OFF
NO_PERSON_TIMEOUT = 300   # 사람이 없을 때 몇 초 후 에어컨 OFF (초)
DEBOUNCE_DELAY = 5        # 상태 변경 확인 지연 (초)

# ===== 로깅 =====
LOG_DIR = './modbus_logs'
os.makedirs(LOG_DIR, exist_ok=True)


class AircondController:
    """에어컨 Modbus 제어 클래스"""

    def __init__(self, port=MODBUS_PORT, baudrate=MODBUS_BAUD):
        """초기화"""
        self.port = port
        self.baudrate = baudrate
        self.serial_conn = None
        self.current_state = False  # False=OFF, True=ON
        self.last_person_detected_time = None
        self.last_state_change_time = time.time()
        self.control_count = 0

        print(f"🔌 Modbus 포트 초기화: {port} ({baudrate} baud)")

    def connect(self):
        """Modbus 연결"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=2
            )
            print("✓ Modbus 연결 완료\n")
            return True
        except serial.SerialException as e:
            print(f"❌ Modbus 연결 오류: {e}")
            print("   - USB-RS485 어댑터가 연결되어 있는지 확인하세요")
            print("   - 포트 설정을 확인하세요: /dev/ttyUSB0 또는 /dev/ttyUSB1")
            return False

    def calculate_crc(self, data):
        """Modbus CRC-16 계산"""
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
        """
        Modbus Function 5: Write Single Coil
        에어컨 ON/OFF 제어
        """
        if not self.serial_conn or not self.serial_conn.is_open:
            print("❌ Modbus 연결 없음")
            return False

        # 프레임 생성
        frame = bytearray([
            SLAVE_ID,
            0x05,  # Function 5: Write Single Coil
            0x00,
            coil_address & 0xFF,
            0xFF if value else 0x00,
            0x00
        ])

        # CRC 계산
        crc = self.calculate_crc(frame)
        frame.append(crc & 0xFF)
        frame.append((crc >> 8) & 0xFF)

        # 전송
        try:
            self.serial_conn.write(bytes(frame))
            self.serial_conn.flush()
            print(f"📤 Modbus 제어 전송: Coil {coil_address} = {value}")
            self.log_control(value)
            self.current_state = value
            self.last_state_change_time = time.time()
            return True
        except serial.SerialException as e:
            print(f"❌ Modbus 전송 오류: {e}")
            return False

    def set_aircond(self, turn_on):
        """에어컨 ON/OFF"""
        if turn_on == self.current_state:
            return  # 이미 같은 상태

        action = "ON" if turn_on else "OFF"
        print(f"\n🌡️ 에어컨 {action} 명령...")
        self.write_coil(AIRCOND_COIL_ADDRESS, turn_on)

    def update_person_detection(self, person_detected):
        """
        사람 감지 상태 업데이트
        """
        if person_detected:
            self.last_person_detected_time = time.time()
            # 에어컨 켜기
            if not self.current_state:
                print("👤 사람 감지됨 → 에어컨 ON")
                self.set_aircond(True)
        else:
            # 사람이 감지되지 않았을 때
            if self.last_person_detected_time is None:
                return

            elapsed = time.time() - self.last_person_detected_time
            if elapsed > NO_PERSON_TIMEOUT:
                # 타임아웃 초과 → 에어컨 끄기
                print(f"👤 {NO_PERSON_TIMEOUT}초 동안 사람 미감지 → 에어컨 OFF")
                self.set_aircond(False)
                self.last_person_detected_time = None

    def log_control(self, state):
        """제어 결과 로깅"""
        self.control_count += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = f"{LOG_DIR}/aircond_control_log.txt"

        status = "ON" if state else "OFF"
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] Aircon {status} | Control #{self.control_count}\n")

    def close(self):
        """연결 종료"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("\nModbus 연결 종료")


def simulate_detection():
    """
    감지 시뮬레이션 (테스트용)
    실제로는 camera_detection.py와 통합됨
    """
    print("\n========================================")
    print("  YOLO + Modbus 에어컨 제어 (시뮬레이션)")
    print("========================================\n")

    controller = AircondController()

    # Modbus 연결 (USB-RS485 어댑터 필요)
    # connect() 호출 시 어댑터가 없으면 실패함
    # if not controller.connect():
    #     print("⚠️  Modbus 연결 실패 - 시뮬레이션만 진행합니다\n")

    print("시뮬레이션: 감지 상태 변화\n")

    try:
        # 시나리오 1: 사람 감지
        print("[시나리오 1] 사람 감지 → 에어컨 ON")
        controller.update_person_detection(True)
        time.sleep(2)

        # 시나리오 2: 사람 계속 감지
        print("\n[시나리오 2] 사람 계속 감지")
        controller.update_person_detection(True)
        time.sleep(2)

        # 시나리오 3: 사람 미감지 시작
        print("\n[시나리오 3] 사람 미감지 (20초 동안)")
        for i in range(20):
            controller.update_person_detection(False)
            print(f"  {i+1}초...")
            time.sleep(1)

        # 시나리오 4: 타임아웃 도달
        print("\n[시나리오 4] 타임아웃 도달 → 에어컨 OFF")
        print(f"  (실제 타임아웃: {NO_PERSON_TIMEOUT}초)\n")

        print("========================================")
        print(f"총 제어 횟수: {controller.control_count}회")
        print(f"로그 저장: {LOG_DIR}/aircond_control_log.txt")
        print("========================================\n")

    except KeyboardInterrupt:
        print("\n\n프로그램 종료 (Ctrl+C)")
    finally:
        controller.close()


def main_with_camera():
    """
    실제 카메라 + YOLO 감지와 통합
    (나중에 camera_detection.py와 함께 실행)
    """
    print("\n========================================")
    print("  USB 카메라 + YOLO + Modbus 통합")
    print("========================================\n")

    print("이 스크립트는 camera_detection.py와 함께 사용됩니다.")
    print("\n사용 예시:")
    print("python camera_detection.py | python modbus_controller.py")
    print("\n또는 통합 스크립트를 작성하여 함께 실행하세요.\n")


if __name__ == "__main__":
    # 시뮬레이션 모드로 실행
    # (실제 카메라가 없을 때도 테스트 가능)
    simulate_detection()

    # 실제 카메라 + YOLO 통합은 나중에:
    # main_with_camera()
