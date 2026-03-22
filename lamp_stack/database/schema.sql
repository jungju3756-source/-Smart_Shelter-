-- RP2040 Modbus RTU 데이터베이스 스키마
-- MariaDB/MySQL 용

-- 데이터베이스 생성
CREATE DATABASE IF NOT EXISTS modbus_rtu;
USE modbus_rtu;

-- 센서 데이터 테이블 (RP2040 #1에서 수집)
CREATE TABLE IF NOT EXISTS sensor_data (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    temperature FLOAT COMMENT '온도 (°C)',
    humidity FLOAT COMMENT '습도 (%)',
    co2 INT COMMENT 'CO2 농도 (ppm)',
    status INT COMMENT '상태 (1=정상, 0=오류)',
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 에어컨 제어 로그 테이블
CREATE TABLE IF NOT EXISTS aircond_control_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    action VARCHAR(50) COMMENT 'ON 또는 OFF',
    reason VARCHAR(255) COMMENT '제어 이유',
    status INT COMMENT '제어 성공 여부 (1=성공, 0=실패)',
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 사람 감지 로그 테이블 (YOLO)
CREATE TABLE IF NOT EXISTS detection_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    detected_persons INT COMMENT '감지된 사람 수',
    confidence FLOAT COMMENT '신뢰도 (0~1)',
    action_taken VARCHAR(100) COMMENT '수행된 조치',
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 시스템 상태 테이블
CREATE TABLE IF NOT EXISTS system_status (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    component VARCHAR(100) COMMENT '시스템 컴포넌트',
    status VARCHAR(50) COMMENT '상태 (online, offline, error)',
    message TEXT COMMENT '상세 메시지',
    INDEX idx_timestamp (timestamp),
    INDEX idx_component (component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 초기 데이터 삽입 (테스트용)
INSERT INTO system_status (component, status, message) VALUES
('RP2040 Slave #1', 'online', 'Modbus RTU 슬레이브 대기 중'),
('RP2040 Master #2', 'offline', '아직 연결되지 않음'),
('LAMP Stack', 'online', 'MySQL 및 Grafana 실행 중'),
('YOLO Detection', 'offline', 'Ubuntu 24.04 준비 중');

-- 데이터베이스 확인
SHOW DATABASES;
USE modbus_rtu;
SHOW TABLES;
DESC sensor_data;
