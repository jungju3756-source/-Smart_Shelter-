#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
USB 카메라 + YOLO 사람 감지 스크립트
- USB 카메라에서 실시간 영상 수집
- YOLOv8로 사람 감지
- 감지 결과 화면 표시 및 로깅
- (나중) Modbus를 통해 RP2040 #2로 에어컨 제어
"""

import cv2
import numpy as np
from ultralytics import YOLO
from datetime import datetime
import time
import os
import sys

# ===== 설정 =====
CAMERA_INDEX = 0          # USB 카메라 인덱스 (보통 0)
YOLO_MODEL = 'yolov8n.pt' # YOLOv8 Nano (빠름)
CONF_THRESHOLD = 0.5      # 신뢰도 임계값
PERSON_CLASS_ID = 0       # YOLO에서 사람은 클래스 ID 0

# ===== 감지 결과 저장 =====
LOG_DIR = './detection_logs'
os.makedirs(LOG_DIR, exist_ok=True)


class PersonDetector:
    """사람 감지 클래스"""

    def __init__(self, model_name='yolov8n.pt'):
        """초기화"""
        print("🤖 YOLOv8 모델 로드 중...")
        try:
            self.model = YOLO(model_name)
            print(f"✓ 모델 로드 완료: {model_name}\n")
        except Exception as e:
            print(f"❌ 모델 로드 오류: {e}")
            sys.exit(1)

        self.detection_count = 0
        self.no_detection_count = 0
        self.fps = 0
        self.frame_count = 0
        self.start_time = time.time()

    def detect(self, frame):
        """
        프레임에서 사람 감지

        Returns:
            - frame: 감지 결과가 그려진 프레임
            - person_detected: 사람 감지 여부 (True/False)
            - person_count: 감지된 사람 수
            - confidence: 평균 신뢰도
        """
        # YOLO 추론
        results = self.model(frame, conf=CONF_THRESHOLD, verbose=False)

        person_detected = False
        person_count = 0
        confidence_list = []

        # 감지 결과 처리
        if results and len(results) > 0:
            boxes = results[0].boxes

            for box in boxes:
                # 클래스 ID 확인 (0 = person)
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])

                if cls_id == PERSON_CLASS_ID:
                    person_detected = True
                    person_count += 1
                    confidence_list.append(conf)

                    # 바운딩 박스 좌표
                    x1, y1, x2, y2 = map(int, box.xyxy[0])

                    # 바운딩 박스 그리기 (초록색)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    # 신뢰도 표시
                    label = f'Person {conf:.2f}'
                    cv2.putText(frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # 평균 신뢰도 계산
        avg_confidence = np.mean(confidence_list) if confidence_list else 0

        # 감지 카운트 업데이트
        if person_detected:
            self.detection_count += 1
            self.no_detection_count = 0
        else:
            self.no_detection_count += 1

        return frame, person_detected, person_count, avg_confidence

    def draw_info(self, frame, person_detected, person_count, confidence):
        """
        화면에 감지 정보 표시
        """
        height, width = frame.shape[:2]

        # 배경 (반투명)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (300, 150), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)

        # 텍스트 색상
        status_color = (0, 255, 0) if person_detected else (0, 0, 255)

        # 상태 표시
        status_text = "🟢 감지됨" if person_detected else "🔴 감지 안됨"
        cv2.putText(frame, status_text, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, status_color, 2)

        # 사람 수
        cv2.putText(frame, f'Count: {person_count}', (10, 70),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        # 신뢰도
        cv2.putText(frame, f'Conf: {confidence:.2f}', (10, 100),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        # FPS
        cv2.putText(frame, f'FPS: {self.fps:.1f}', (10, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

        # 시간
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, timestamp, (10, height - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        return frame

    def update_fps(self):
        """FPS 계산"""
        self.frame_count += 1
        elapsed = time.time() - self.start_time
        if elapsed > 1:
            self.fps = self.frame_count / elapsed
            self.frame_count = 0
            self.start_time = time.time()

    def save_frame(self, frame, person_detected, person_count):
        """감지된 프레임 저장"""
        if person_detected:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{LOG_DIR}/person_detected_{timestamp}_{person_count}.jpg"
            cv2.imwrite(filename, frame)
            return filename
        return None

    def log_detection(self, person_detected, person_count, confidence):
        """감지 결과 로깅"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file = f"{LOG_DIR}/detection_log.txt"

        with open(log_file, 'a') as f:
            status = "DETECTED" if person_detected else "NOT_DETECTED"
            f.write(f"[{timestamp}] {status} | Count: {person_count} | Confidence: {confidence:.2f}\n")


def main():
    """메인 함수"""
    print("\n========================================")
    print("  USB 카메라 + YOLO 사람 감지")
    print("========================================")
    print(f"카메라 인덱스: {CAMERA_INDEX}")
    print(f"모델: {YOLO_MODEL}")
    print(f"신뢰도 임계값: {CONF_THRESHOLD}")
    print("========================================\n")

    # 카메라 초기화
    print("📹 카메라 초기화 중...")
    cap = cv2.VideoCapture(CAMERA_INDEX)

    if not cap.isOpened():
        print(f"❌ 카메라 {CAMERA_INDEX}을 열 수 없습니다.")
        print("   - USB 카메라가 연결되어 있는지 확인하세요")
        print("   - 다른 응용프로그램이 카메라를 사용 중인지 확인하세요")
        sys.exit(1)

    print("✓ 카메라 초기화 완료\n")

    # 카메라 설정
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # 감지기 초기화
    detector = PersonDetector(YOLO_MODEL)

    print("🎬 감지 시작...\n")
    print("종료하려면 'q' 키를 누르세요\n")

    frame_count = 0
    detection_log_interval = 30  # 30프레임마다 로깅

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                print("❌ 프레임 읽기 실패")
                break

            # 프레임 크기 조정 (처리 속도 향상)
            frame = cv2.resize(frame, (640, 480))

            # 사람 감지
            frame, person_detected, person_count, confidence = detector.detect(frame)

            # 정보 표시
            frame = detector.draw_info(frame, person_detected, person_count, confidence)

            # FPS 업데이트
            detector.update_fps()

            # 주기적 로깅
            frame_count += 1
            if frame_count % detection_log_interval == 0:
                detector.log_detection(person_detected, person_count, confidence)
                print(f"[{datetime.now().strftime('%H:%M:%S')}] "
                      f"{'✓ 사람 감지' if person_detected else '✗ 감지 안됨'} | "
                      f"수: {person_count} | 신뢰도: {confidence:.2f}")

            # 감지된 경우 프레임 저장
            if person_detected:
                filename = detector.save_frame(frame, person_detected, person_count)

            # 화면 표시
            cv2.imshow('Person Detection - YOLO', frame)

            # 키 입력 처리
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                print("\n\n프로그램 종료 (사용자 입력)")
                break
            elif key == ord('s'):
                # 수동 저장
                filename = f"{LOG_DIR}/manual_capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                cv2.imwrite(filename, frame)
                print(f"✓ 프레임 저장: {filename}")

    except KeyboardInterrupt:
        print("\n\n프로그램 종료 (Ctrl+C)")
    finally:
        # 정리
        cap.release()
        cv2.destroyAllWindows()
        print("카메라 종료")
        print(f"총 {frame_count}프레임 처리")
        print(f"감지됨: {detector.detection_count}회")
        print(f"미감지: {detector.no_detection_count}회")
        print(f"로그 저장 위치: {LOG_DIR}")
        print("\n프로그램 종료\n")


if __name__ == "__main__":
    main()
