#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RP2040 Modbus RTU 클라이언트 (데이터 시각화 버전)
- COM6에서 RP2040 #1 (슬레이브) 데이터 읽기
- Zorin OS의 MySQL (192.168.0.53:3306)에 저장
- matplotlib로 실시간 그래프 표시
- 2초 주기로 반복
"""

import serial
import time
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import sys
import threading
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np
from collections import deque

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

# 그래프 데이터 저장 (최근 50개)
MAX_DATAPOINTS = 50

# ===== 글로벌 변수 =====
serial_conn = None
mysql_conn = None
read_count = 0

# 데이터 저장소
data_buffer = {
    'timestamp': deque(maxlen=MAX_DATAPOINTS),
    'temperature': deque(maxlen=MAX_DATAPOINTS),
    'humidity': deque(maxlen=MAX_DATAPOINTS),
    'co2': deque(maxlen=MAX_DATAPOINTS)
}

data_lock = threading.Lock()
stop_event = threading.Event()


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

    # 전송
    try:
        serial_conn.write(request)
    except serial.SerialException as e:
        print(f"❌ 전송 오류: {e}")
        return None

    # 응답 수신
    time.sleep(0.1)
    response = serial_conn.read(32)

    if not response:
        print("❌ 응답 없음 (타임아웃)")
        return None

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
        return True
    except Error as e:
        print(f"❌ MySQL 저장 오류: {e}")
        return False


def modbus_read_thread():
    """Modbus 데이터 읽기 스레드"""
    global read_count

    while not stop_event.is_set():
        read_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Modbus RTU 요청
        registers = read_holding_registers(SLAVE_ID, 0, 5)

        if registers:
            temperature = registers[0] / 100.0
            humidity = registers[1] / 10.0
            co2 = registers[2]
            status = registers[3]

            # 데이터 버퍼에 추가
            with data_lock:
                data_buffer['timestamp'].append(timestamp)
                data_buffer['temperature'].append(temperature)
                data_buffer['humidity'].append(humidity)
                data_buffer['co2'].append(co2)

            # MySQL에 저장
            save_to_mysql(temperature, humidity, co2, status)

            print(f"[{timestamp}] ✓ 온도: {temperature:.2f}°C, 습도: {humidity:.1f}%, CO2: {co2} ppm")
        else:
            print(f"[{timestamp}] ❌ 데이터 수신 실패")

        # 다음 읽기까지 대기
        time.sleep(READ_INTERVAL)


def setup_plots():
    """그래프 설정"""
    plt.style.use('seaborn-v0_8-darkgrid')
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle('RP2040 Modbus RTU 센서 데이터 실시간 모니터링', fontsize=16, fontweight='bold')

    # 각 서브플롯 설정
    ax_temp = axes[0, 0]
    ax_humidity = axes[0, 1]
    ax_co2 = axes[1, 0]
    ax_stats = axes[1, 1]

    # 온도 그래프
    ax_temp.set_title('온도 (°C)', fontsize=12, fontweight='bold')
    ax_temp.set_ylabel('온도 (°C)')
    ax_temp.set_ylim(20, 35)
    ax_temp.grid(True, alpha=0.3)

    # 습도 그래프
    ax_humidity.set_title('습도 (%)', fontsize=12, fontweight='bold')
    ax_humidity.set_ylabel('습도 (%)')
    ax_humidity.set_ylim(30, 80)
    ax_humidity.grid(True, alpha=0.3)

    # CO2 그래프
    ax_co2.set_title('CO2 농도 (ppm)', fontsize=12, fontweight='bold')
    ax_co2.set_ylabel('CO2 (ppm)')
    ax_co2.set_ylim(300, 700)
    ax_co2.grid(True, alpha=0.3)

    # 통계 정보 (텍스트)
    ax_stats.axis('off')
    ax_stats.set_title('통계 정보', fontsize=12, fontweight='bold')

    return fig, (ax_temp, ax_humidity, ax_co2, ax_stats)


def update_plots(frame, axes):
    """그래프 업데이트"""
    ax_temp, ax_humidity, ax_co2, ax_stats = axes

    with data_lock:
        if len(data_buffer['temperature']) == 0:
            return

        # 데이터 복사 (스레드 안전)
        temps = list(data_buffer['temperature'])
        humidities = list(data_buffer['humidity'])
        co2s = list(data_buffer['co2'])
        timestamps = list(data_buffer['timestamp'])

    # x축 인덱스
    x = np.arange(len(temps))

    # 온도 그래프 업데이트
    ax_temp.clear()
    ax_temp.plot(x, temps, 'r-o', linewidth=2, markersize=6, label='온도')
    ax_temp.set_title('온도 (°C)', fontsize=12, fontweight='bold')
    ax_temp.set_ylabel('온도 (°C)')
    ax_temp.set_ylim(20, 35)
    ax_temp.grid(True, alpha=0.3)
    if len(temps) > 0:
        ax_temp.axhline(y=np.mean(temps), color='red', linestyle='--', alpha=0.5, label=f'평균: {np.mean(temps):.1f}°C')
        ax_temp.legend()

    # 습도 그래프 업데이트
    ax_humidity.clear()
    ax_humidity.plot(x, humidities, 'b-o', linewidth=2, markersize=6, label='습도')
    ax_humidity.set_title('습도 (%)', fontsize=12, fontweight='bold')
    ax_humidity.set_ylabel('습도 (%)')
    ax_humidity.set_ylim(30, 80)
    ax_humidity.grid(True, alpha=0.3)
    if len(humidities) > 0:
        ax_humidity.axhline(y=np.mean(humidities), color='blue', linestyle='--', alpha=0.5, label=f'평균: {np.mean(humidities):.1f}%')
        ax_humidity.legend()

    # CO2 그래프 업데이트
    ax_co2.clear()
    ax_co2.plot(x, co2s, 'g-o', linewidth=2, markersize=6, label='CO2')
    ax_co2.set_title('CO2 농도 (ppm)', fontsize=12, fontweight='bold')
    ax_co2.set_ylabel('CO2 (ppm)')
    ax_co2.set_ylim(300, 700)
    ax_co2.grid(True, alpha=0.3)
    if len(co2s) > 0:
        ax_co2.axhline(y=np.mean(co2s), color='green', linestyle='--', alpha=0.5, label=f'평균: {np.mean(co2s):.0f} ppm')
        ax_co2.legend()

    # 통계 정보 업데이트
    ax_stats.clear()
    ax_stats.axis('off')
    ax_stats.set_title('통계 정보', fontsize=12, fontweight='bold')

    stats_text = f"""
    📊 실시간 센서 데이터

    🌡️ 온도
    현재: {temps[-1] if temps else 0:.2f}°C
    평균: {np.mean(temps) if temps else 0:.2f}°C
    최대/최소: {max(temps) if temps else 0:.2f}°C / {min(temps) if temps else 0:.2f}°C

    💧 습도
    현재: {humidities[-1] if humidities else 0:.1f}%
    평균: {np.mean(humidities) if humidities else 0:.1f}%
    최대/최소: {max(humidities) if humidities else 0:.1f}% / {min(humidities) if humidities else 0:.1f}%

    🌍 CO2
    현재: {co2s[-1] if co2s else 0:.0f} ppm
    평균: {np.mean(co2s) if co2s else 0:.0f} ppm
    최대/최소: {max(co2s) if co2s else 0:.0f} / {min(co2s) if co2s else 0:.0f} ppm

    ⏱️ 데이터 포인트: {len(temps)}개
    🕐 마지막 업데이트: {timestamps[-1] if timestamps else 'N/A'}
    """

    ax_stats.text(0.1, 0.5, stats_text, fontsize=10, verticalalignment='center',
                  fontfamily='monospace', bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))


def main():
    """메인 함수"""
    print("\n========================================")
    print("  RP2040 Modbus RTU 클라이언트")
    print("  (데이터 시각화 버전)")
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

    # Modbus 읽기 스레드 시작
    modbus_thread = threading.Thread(target=modbus_read_thread, daemon=True)
    modbus_thread.start()

    print("📊 그래프 준비 중...\n")

    # 그래프 설정
    fig, axes = setup_plots()

    # 애니메이션 설정 (500ms마다 업데이트)
    ani = FuncAnimation(fig, update_plots, fargs=(axes,), interval=500, blit=False)

    # 그래프 표시
    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        print("\n\n프로그램 종료 (Ctrl+C)")
    finally:
        # 종료 처리
        stop_event.set()
        modbus_thread.join(timeout=2)

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
