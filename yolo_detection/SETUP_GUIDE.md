# Zorin OS YOLO 설정 가이드

## 📋 개요

Zorin OS에서 USB 카메라를 사용하여 YOLO로 사람을 감지하고, Modbus를 통해 RP2040 #2로 에어컨을 제어합니다.

---

## 🚀 설치 단계

### 1️⃣ Python 패키지 설치

Zorin OS 터미널에서:

```bash
cd ~/yolo_detection
pip install -r requirements.txt
```

설치 시간: **5~10분** (torch, ultralytics 등 대용량 라이브러리 포함)

---

### 2️⃣ USB 카메라 확인

```bash
# 카메라 디바이스 확인
ls -la /dev/video*
```

출력 예시:
```
/dev/video0  <- USB 카메라
/dev/video1
```

카메라가 보이면 정상입니다!

---

### 3️⃣ YOLOv8 모델 다운로드

처음 실행할 때 자동으로 다운로드되지만, 사전에 다운로드할 수 있습니다:

```bash
python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
```

다운로드 크기: **약 50MB** (Nano 모델)

---

## 🎬 실행 방법

### **옵션 1️⃣: 카메라 + YOLO 감지 (스크립트만)**

```bash
python camera_detection.py
```

**기능:**
- 실시간 카메라 영상 표시
- 사람 감지 및 바운딩 박스 표시
- 감지 결과 로깅
- 프레임 저장

**조작:**
- **q**: 종료
- **s**: 현재 프레임 저장

**출력 예시:**
```
========================================
  USB 카메라 + YOLO 사람 감지
========================================

📹 카메라 초기화 중...
✓ 카메라 초기화 완료

🤖 YOLOv8 모델 로드 중...
✓ 모델 로드 완료: yolov8n.pt

🎬 감지 시작...

[14:30:45] ✓ 사람 감지 | 수: 1 | 신뢰도: 0.85
[14:30:50] ✓ 사람 감지 | 수: 2 | 신뢰도: 0.92
[14:31:00] ✗ 감지 안됨 | 수: 0 | 신뢰도: 0.00
```

---

### **옵션 2️⃣: Modbus 에어컨 제어 (시뮬레이션)**

```bash
python modbus_controller.py
```

**기능:**
- 사람 감지 상태 시뮬레이션
- 에어컨 ON/OFF 제어 로직 테스트
- Modbus 제어 명령 로깅

**출력 예시:**
```
========================================
  YOLO + Modbus 에어컨 제어 (시뮬레이션)
========================================

🔌 Modbus 포트 초기화: /dev/ttyUSB0 (9600 baud)

[시나리오 1] 사람 감지 → 에어컨 ON
👤 사람 감지됨 → 에어컨 ON
🌡️ 에어컨 ON 명령...
📤 Modbus 제어 전송: Coil 0 = True
```

---

## 🔌 Modbus 하드웨어 연결 (나중에)

실제 RP2040 #2와 통신하려면 **USB-RS485 어댑터**가 필요합니다:

```
Zorin OS (USB)
    ↓
USB-RS485 어댑터
    ↓
RS-485 케이블
    ↓
RP2040 #2 (GPIO0/1: UART0)
```

### USB-RS485 어댑터 설정

1. **어댑터 연결**
   ```bash
   ls -la /dev/ttyUSB*
   ```
   보통 `/dev/ttyUSB0` 또는 `/dev/ttyUSB1`

2. **modbus_controller.py 포트 수정**
   ```python
   MODBUS_PORT = '/dev/ttyUSB0'  # 자신의 포트로 변경
   ```

---

## 📊 로그 및 데이터

### 감지 로그
```bash
cat detection_logs/detection_log.txt
```

### 제어 로그
```bash
cat modbus_logs/aircond_control_log.txt
```

### 저장된 프레임
```bash
ls detection_logs/person_detected_*.jpg
```

---

## ⚙️ 설정 값 조정

### `camera_detection.py`
```python
CAMERA_INDEX = 0              # 카메라 인덱스 (기본: 0)
YOLO_MODEL = 'yolov8n.pt'    # 모델 선택
CONF_THRESHOLD = 0.5         # 신뢰도 임계값 (0~1, 높을수록 엄격함)
```

### `modbus_controller.py`
```python
NO_PERSON_TIMEOUT = 300      # 사람 없을 때 OFF까지의 시간 (초)
DEBOUNCE_DELAY = 5           # 상태 변경 확인 지연 (초)
```

---

## 🐛 문제 해결

### ❌ "No module named 'ultralytics'"
```bash
pip install ultralytics
```

### ❌ "카메라를 열 수 없습니다"
```bash
# 카메라 권한 확인
ls -la /dev/video0

# 필요 시 권한 추가
sudo usermod -a -G video $USER
```

### ❌ "Modbus 연결 실패"
- USB-RS485 어댑터 연결 확인
- 포트 설정 확인: `ls /dev/ttyUSB*`
- RS-485 케이블 연결 확인

---

## 📈 성능 최적화

### GPU 사용 (CUDA 지원 시)
```python
# camera_detection.py에서
self.model = YOLO(model_name).to('cuda')  # GPU 사용
```

### 경량 모델 사용
```python
YOLO_MODEL = 'yolov8n.pt'    # Nano (빠름)
YOLO_MODEL = 'yolov8s.pt'    # Small (균형)
YOLO_MODEL = 'yolov8m.pt'    # Medium (정확함)
```

---

## 🔄 다음 단계

1. ✅ **현재**: camera_detection.py 작성 완료
2. ✅ **현재**: modbus_controller.py 작성 완료
3. ⏳ **다음**: 통합 스크립트 작성 (camera_detection + modbus_controller)
4. ⏳ **다음**: RP2040 #2와 실제 통신 테스트
5. ⏳ **다음**: Grafana 대시보드에 감지 결과 표시

---

## 📞 참고 자료

- [YOLOv8 공식 문서](https://docs.ultralytics.com/)
- [OpenCV 문서](https://docs.opencv.org/)
- [Modbus 프로토콜](https://en.wikipedia.org/wiki/Modbus)

---

작성 일시: 2026년 3월 22일
