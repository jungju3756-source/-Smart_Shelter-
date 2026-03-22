#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RP2040 Modbus RTU 클라이언트
- COM6에서 RP2040 #1 (슬레이브) 데이터 읽기
- Zorin OS의 MySQL (192.168.0.53:3306)에 저장
- 2초 주기로 반복
"""

import serial
import time
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import sys

# ===== 설정 =====
SERIAL_PORT = 'COM6'
SERIAL_BAUD = 9600
SERIAL_TIMEOUT = 2

MYSQL_HOST = '192.168.0.53'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'qwer1234'
MYSQL_DATABASE = 'modbus_rtu'

SLAVE_ID = 1
READ_INTERVAL = 2  # 초

# ===== 글로벌 변수 =====
serial_conn = None
mysql_conn = None
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


def init_mysql():
    """MySQL 연결 초기화"""
    global mysql_conn
    try:
        mysql_conn = mysql.connector.connect(
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
    """
    Modbus Function 3: Read Holding Registers
    슬레이브에서 Holding Registers 읽기
    """
    global serial_conn

    # 요청 프레임 생성
    request = build_modbus_request(slave_id, 0x03, start_addr, quantity)

    # 전송 (이전 버퍼 데이터 제거 후 전송)
    try:
        serial_conn.reset_input_buffer()
        serial_conn.write(request)
        print(f"📤 요청 전송: {' '.join(f'{b:02X}' for b in request)}")
    except serial.SerialException as e:
        print(f"❌ 전송 오류: {e}")
        return None

    # 응답 수신 (Function 3, 5레지스터 = 3+10+2 = 15바이트)
    time.sleep(0.2)
    response = serial_conn.read(15)

    if not response:
        print("❌ 응답 없음 (타임아웃)")
        return None

    print(f"📥 응답 수신: {' '.join(f'{b:02X}' for b in response)}")

    # 응답 파싱 (Function 3 응답)
    if len(response) < 9:
        print("❌ 응답 길이 부족")
        return None

    if response[0] != slave_id or response[1] != 0x03:
        print(f"❌ 슬레이브 ID 또는 함수 코드 오류")
        return None

    byte_count = response[2]
    if len(response) < 3 + byte_count + 2:
        print("❌ 응답 데이터 부족")
        return None

    # 레지스터 값 추출
    registers = []
    for i in range(quantity):
        high = response[3 + i * 2]
        low = response[4 + i * 2]
        value = (high << 8) | low
        registers.append(value)

    return registers


def save_to_mysql(temperature, humidity, co2, status):
    """MySQL에 센서 데이터 저장"""
    global mysql_conn

    try:
        cursor = mysql_conn.cursor()
        query = """
            INSERT INTO sensor_data
            (timestamp, temperature, humidity, co2, status)
            VALUES (%s, %s, %s, %s, %s)
        """

        values = (
            datetime.now(),
            temperature,
            humidity,
            co2,
            status
        )

        cursor.execute(query, values)
        cursor.close()

        print(f"✓ MySQL 저장 완료 - 온도: {temperature:.2f}°C, 습도: {humidity:.1f}%, CO2: {co2} ppm")
        return True
    except Error as e:
        print(f"❌ MySQL 저장 오류: {e}")
        return False


def main():
    """메인 루프"""
    global read_count

    print("\n========================================")
    print("  RP2040 Modbus RTU 클라이언트")
    print("========================================")
    print(f"직렬 포트: {SERIAL_PORT}")
    print(f"MySQL 서버: {MYSQL_HOST}:{MYSQL_PORT}")
    print(f"읽기 주기: {READ_INTERVAL}초")
    print("========================================\n")

    # 초기화
    if not init_serial():
        sys.exit(1)

    if not init_mysql():
        sys.exit(1)

    print("✓ 모든 초기화 완료\n")
    print("데이터 수집 시작...\n")

    try:
        while True:
            read_count += 1
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] 읽기 #{read_count}")
            print("-" * 40)

            # Modbus RTU 요청
            # Function 3: Read Holding Registers
            # 시작 주소: 0, 개수: 5
            # Register 0: 온도 (×100)
            # Register 1: 습도 (×10)
            # Register 2: CO2
            # Register 3: 상태
            # Register 4: 카운터

            registers = read_holding_registers(SLAVE_ID, 0, 5)

            if registers:
                temperature = registers[0] / 100.0
                humidity = registers[1] / 10.0
                co2 = registers[2]
                status = registers[3]
                counter = registers[4]

                print(f"\n✓ 데이터 수신:")
                print(f"  온도: {temperature:.2f}°C")
                print(f"  습도: {humidity:.1f}%")
                print(f"  CO2: {co2} ppm")
                print(f"  상태: {status}")
                print(f"  카운터: {counter}")

                # MySQL에 저장
                save_to_mysql(temperature, humidity, co2, status)
            else:
                print("❌ 데이터 수신 실패")

            # 다음 읽기까지 대기
            print(f"\n{READ_INTERVAL}초 대기 중...")
            time.sleep(READ_INTERVAL)

    except KeyboardInterrupt:
        print("\n\n프로그램 종료 (Ctrl+C)")
    finally:
        # 종료 처리
        if serial_conn and serial_conn.is_open:
            serial_conn.close()
            print("직렬 포트 종료")

        if mysql_conn and mysql_conn.is_connected():
            mysql_conn.close()
            print("MySQL 연결 종료")

        print(f"\n총 {read_count}회 읽음")
        print("프로그램 종료\n")


if __name__ == "__main__":
    main()
