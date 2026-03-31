#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RP2040 #1 Modbus RTU 클라이언트
- /dev/ttyACM0 에서 RP2040 #1 (슬레이브) 데이터 읽기
- 전압(23~24V), 전류(1~2A) 태양광 시뮬레이션 데이터
- SQLite DB에 저장
- 2초 주기로 반복
"""

import serial
import time
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import sys

# ===== 설정 =====
SERIAL_PORT = '/dev/ttyACM0'   # Zorin OS에서 RP2040 #1 USB 포트
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 2

MYSQL_HOST     = '127.0.0.1'
MYSQL_PORT     = 3306
MYSQL_USER     = 'root'
MYSQL_PASSWORD = 'qwer1234'
MYSQL_DATABASE = 'modbus_rtu'

SLAVE_ID = 1
READ_INTERVAL = 2  # 초

# ===== 글로벌 변수 =====
serial_conn = None
db_conn = None
read_count = 0


def init_serial():
    """직렬 포트 초기화"""
    global serial_conn
    try:
        serial_conn = serial.Serial(
            port=SERIAL_PORT,
            baudrate=SERIAL_BAUD,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=SERIAL_TIMEOUT
        )
        print(f"✓ 직렬 포트 초기화 완료: {SERIAL_PORT} ({SERIAL_BAUD} baud)")
        return True
    except serial.SerialException as e:
        print(f"❌ 직렬 포트 오류: {e}")
        return False


def init_db():
    """MySQL 연결 초기화"""
    global db_conn
    try:
        db_conn = mysql.connector.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            autocommit=True
        )
        print(f"✓ MySQL 연결 완료: {MYSQL_HOST}:{MYSQL_PORT}")
        return True
    except Error as e:
        print(f"❌ MySQL 연결 오류: {e}")
        return False


def calculate_crc(data):
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


def build_modbus_request(slave_id, function_code, start_addr, quantity):
    """Modbus RTU 요청 프레임 생성"""
    frame = bytearray([
        slave_id,
        function_code,
        (start_addr >> 8) & 0xFF,
        start_addr & 0xFF,
        (quantity >> 8) & 0xFF,
        quantity & 0xFF
    ])
    crc = calculate_crc(frame)
    frame.append(crc & 0xFF)
    frame.append((crc >> 8) & 0xFF)
    return bytes(frame)


def read_holding_registers(slave_id, start_addr, quantity):
    """Modbus FC3: Read Holding Registers"""
    global serial_conn

    request = build_modbus_request(slave_id, 0x03, start_addr, quantity)

    try:
        serial_conn.reset_input_buffer()
        serial_conn.write(request)
        print(f"송신: {' '.join(f'{b:02X}' for b in request)}")
    except serial.SerialException as e:
        print(f"❌ 전송 오류: {e}")
        return None

    # 응답: 3 + (quantity×2) + 2 바이트
    expected = 3 + quantity * 2 + 2
    time.sleep(0.2)
    response = serial_conn.read(expected)

    if not response:
        print("❌ 응답 없음 (타임아웃)")
        return None

    print(f"수신: {' '.join(f'{b:02X}' for b in response)}")

    if len(response) < expected:
        print("❌ 응답 길이 부족")
        return None

    if response[0] != slave_id or response[1] != 0x03:
        print("❌ 슬레이브 ID 또는 함수 코드 오류")
        return None

    registers = []
    for i in range(quantity):
        value = (response[3 + i * 2] << 8) | response[4 + i * 2]
        registers.append(value)

    return registers


def save_to_db(voltage, current, status):
    """MySQL에 태양광 데이터 저장"""
    global db_conn
    try:
        cursor = db_conn.cursor()
        cursor.execute(
            "INSERT INTO solar_data (timestamp, voltage, current, status) VALUES (%s, %s, %s, %s)",
            (datetime.now(), voltage, current, status)
        )
        cursor.close()
        print(f"✓ DB 저장 완료 - 전압: {voltage:.2f}V, 전류: {current:.2f}A")
        return True
    except Error as e:
        print(f"❌ DB 저장 오류: {e}")
        return False


def main():
    global read_count

    print("\n========================================")
    print("  RP2040 #1 Modbus 클라이언트 (태양광)")
    print("========================================")
    print(f"직렬 포트: {SERIAL_PORT}")
    print(f"DB: {MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}")
    print(f"읽기 주기: {READ_INTERVAL}초")
    print("========================================\n")

    if not init_serial():
        sys.exit(1)

    if not init_db():
        sys.exit(1)

    print("데이터 수집 시작...\n")

    try:
        while True:
            read_count += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] #{read_count}")
            print("-" * 40)

            # Register 0: 전압 ×100, Register 1: 전류 ×100, Register 2: 상태
            registers = read_holding_registers(SLAVE_ID, 0, 3)

            if registers:
                voltage = registers[0] / 100.0
                current = registers[1] / 100.0
                status  = registers[2]

                print(f"\n  전압: {voltage:.2f}V")
                print(f"  전류: {current:.2f}A")
                print(f"  상태: {status}")

                save_to_db(voltage, current, status)
            else:
                print("❌ 데이터 수신 실패")

            time.sleep(READ_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n프로그램 종료 (Ctrl+C)")
    finally:
        if serial_conn and serial_conn.is_open:
            serial_conn.close()
            print("직렬 포트 종료")
        if db_conn and db_conn.is_connected():
            db_conn.close()
            print("DB 연결 종료")
        print(f"\n총 {read_count}회 읽음\n")


if __name__ == "__main__":
    main()
