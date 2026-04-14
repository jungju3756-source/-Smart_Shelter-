#!/usr/bin/env python3
"""
3D 오피스 공간 시뮬레이터
- Panda3D 기반 3차원 오피스 공간
- PLC: 5초마다 랜덤 전압/전류 값 생성 및 인디케이터 표시
- 에어컨: 사람 감지 시 ON/OFF 인디케이터 제어
- USB 카메라 + YOLOv8 실시간 사람 감지 → 카메라 뷰 패널 표시
"""

import os
import random
import queue
import threading
import time
import traceback
from pathlib import Path

import cv2
import numpy as np

# Reolink RLC-1212A RTSP 저지연 옵션
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = \
    "rtsp_transport;tcp|buffer_size;1024000|max_delay;100000"

RTSP_URL = "rtsp://admin:qwer1234@192.168.0.69:554/h264Preview_01_sub"

# ── ultralytics를 메인 스레드에서 미리 import (Panda3D+PyTorch 스레드 충돌 방지)
try:
    from ultralytics import YOLO as _YOLO
    _YOLO_AVAILABLE = True
except Exception as _e:
    print(f"[경고] ultralytics import 실패: {_e}")
    _YOLO_AVAILABLE = False

# main.py 와 같은 폴더에 있는 yolov8n.pt 절대경로
_MODEL_PATH = str(Path(__file__).resolve().parent / "yolov8n.pt")

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    PointLight,
    TextNode,
    Texture,
    Vec3,
    Vec4,
    loadPrcFileData,
)

loadPrcFileData("", "window-title 3D Office Simulator")
loadPrcFileData("", "win-size 1280 720")
loadPrcFileData("", "sync-video 0")


# ── 지오메트리 헬퍼 ────────────────────────────────────────────────────────────


def make_box(name: str, sx: float, sy: float, sz: float,
             color: tuple = (0.8, 0.8, 0.8, 1.0)) -> NodePath:
    """
    색상이 적용된 직육면체 NodePath 반환.
      sx = X 폭, sy = Y 깊이, sz = Z 높이
    """
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vtx = GeomVertexWriter(vdata, "vertex")
    nrm = GeomVertexWriter(vdata, "normal")
    clr = GeomVertexWriter(vdata, "color")

    hx, hy, hz = sx / 2, sy / 2, sz / 2
    r, g, b, a = color

    # (법선, [4 꼭짓점]) — 법선 방향에서 볼 때 CCW
    faces = [
        ((0,  0,  1), [(-hx, -hy,  hz), ( hx, -hy,  hz), ( hx,  hy,  hz), (-hx,  hy,  hz)]),
        ((0,  0, -1), [(-hx,  hy, -hz), ( hx,  hy, -hz), ( hx, -hy, -hz), (-hx, -hy, -hz)]),
        ((0,  1,  0), [(-hx,  hy, -hz), ( hx,  hy, -hz), ( hx,  hy,  hz), (-hx,  hy,  hz)]),
        ((0, -1,  0), [(-hx, -hy,  hz), ( hx, -hy,  hz), ( hx, -hy, -hz), (-hx, -hy, -hz)]),
        (( 1, 0,  0), [( hx, -hy, -hz), ( hx,  hy, -hz), ( hx,  hy,  hz), ( hx, -hy,  hz)]),
        ((-1, 0,  0), [(-hx,  hy, -hz), (-hx, -hy, -hz), (-hx, -hy,  hz), (-hx,  hy,  hz)]),
    ]

    tris = GeomTriangles(Geom.UHStatic)
    i = 0
    for norm, verts in faces:
        for v in verts:
            vtx.addData3(*v)
            nrm.addData3(*norm)
            clr.addData4(r, g, b, a)
        tris.addVertices(i, i + 1, i + 2)
        tris.addVertices(i, i + 2, i + 3)
        i += 4

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def make_screen(name: str, left: float, right: float,
                bottom: float, top: float) -> NodePath:
    """
    XZ 평면의 텍스처 쿼드, 법선 = -Y (시청자 방향).
    UV: BL(0,0) BR(1,0) TR(1,1) TL(0,1)
    """
    fmt = GeomVertexFormat.getV3n3t2()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vtx = GeomVertexWriter(vdata, "vertex")
    nrm = GeomVertexWriter(vdata, "normal")
    uv  = GeomVertexWriter(vdata, "texcoord")

    corners = [
        (left,  bottom, 0.0, 0.0),   # BL
        (right, bottom, 1.0, 0.0),   # BR
        (right, top,    1.0, 1.0),   # TR
        (left,  top,    0.0, 1.0),   # TL
    ]
    for x, z, u, v in corners:
        vtx.addData3(x, 0, z)
        nrm.addData3(0, -1, 0)
        uv.addData2(u, v)

    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


def attach_label(parent: NodePath, text: str, scale: float,
                 pos: tuple, color: tuple):
    """텍스트 노드를 부모에 부착하고 빌보드(항상 카메라 방향)로 설정.
    반환: (TextNode, NodePath) — setText()는 TextNode로, setColor()는 NodePath로."""
    tn = TextNode(text)
    tn.setAlign(TextNode.ACenter)
    tn.setTextColor(*color)
    tn.setText(text)
    np_ = parent.attachNewNode(tn)
    np_.setScale(scale)
    np_.setPos(*pos)
    np_.setBillboardAxis()
    return tn, np_


# ── 카메라 / YOLO 워커 스레드 ──────────────────────────────────────────────────


class CameraWorker(threading.Thread):
    """USB 카메라 캡처 + YOLOv8 사람 감지 백그라운드 스레드."""

    # 연속 N프레임 감지돼야 ON, M프레임 미감지돼야 OFF (흔들림 방지)
    _ON_FRAMES  = 3
    _OFF_FRAMES = 15

    def __init__(self, frame_queue: queue.Queue, cam_source: str = RTSP_URL):
        super().__init__(daemon=True, name="CameraWorker")
        self.frame_queue     = frame_queue
        self.cam_source      = cam_source
        self.person_detected = False
        self._det_cnt  = 0   # 연속 감지 프레임 수
        self._nodet_cnt = 0  # 연속 미감지 프레임 수
        self._stop       = threading.Event()

    # ── 메인 루프 ──────────────────────────────────────────────────────────────

    def run(self):
        # YOLOv8 로드 (첫 실행 시 가중치 자동 다운로드)
        yolo = None
        if _YOLO_AVAILABLE:
            try:
                print(f"[Worker] YOLOv8n 모델 로딩 중... ({_MODEL_PATH})")
                yolo = _YOLO(_MODEL_PATH)
                print("[Worker] YOLO 준비 완료.")
            except Exception:
                traceback.print_exc()
                print("[Worker] YOLO 모델 로드 실패 — 감지 없이 카메라만 표시")
        else:
            print("[Worker] ultralytics 없음 — 감지 없이 카메라만 표시")

        # RTSP IP 카메라 연결 (Reolink RLC-1212A)
        print(f"[Worker] RTSP 연결 중: {self.cam_source}")
        cap = cv2.VideoCapture(self.cam_source, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            print(f"[Worker] RTSP 연결 실패 → 더미 모드")
            self._dummy_loop()
            return

        print(f"[Worker] RTSP 연결 완료")

        while not self._stop.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            annotated    = frame.copy()
            person_found = False

            if yolo is not None:
                try:
                    results = yolo(frame, classes=[0], conf=0.35, verbose=False, imgsz=416)
                    for r in results:
                        for box in (r.boxes or []):
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            conf = float(box.conf[0])
                            person_found = True
                            cv2.rectangle(annotated, (x1, y1), (x2, y2),
                                          (0, 230, 60), 2)
                            cv2.putText(annotated,
                                        f"Person {conf:.2f}",
                                        (x1, max(y1 - 8, 10)),
                                        cv2.FONT_HERSHEY_SIMPLEX,
                                        0.55, (0, 230, 60), 2)
                except Exception as exc:
                    print(f"[Worker] YOLO 오류: {exc}")

            # 디바운스: 연속 감지/미감지 프레임 카운트로 상태 확정
            if person_found:
                self._det_cnt   += 1
                self._nodet_cnt  = 0
                if self._det_cnt >= self._ON_FRAMES:
                    self.person_detected = True
            else:
                self._nodet_cnt += 1
                self._det_cnt    = 0
                if self._nodet_cnt >= self._OFF_FRAMES:
                    self.person_detected = False

            # 상태 오버레이
            label_text  = "PERSON DETECTED" if person_found else "NO PERSON"
            label_color = (20, 230, 80)       if person_found else (80, 80, 220)
            cv2.putText(annotated, label_text, (8, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.80, label_color, 2)

            # BGR → RGB 변환 후 큐 전달
            self._push(cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB))

        cap.release()
        print("[Worker] 카메라 종료")

    # ── 더미 루프 (카메라 없을 때) ─────────────────────────────────────────────

    def _dummy_loop(self):
        while not self._stop.is_set():
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "NO CAMERA",        (185, 220),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.4, (80, 80, 80), 3)
            cv2.putText(frame, time.strftime("%H:%M:%S"), (230, 280),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 60), 2)
            self._push(frame)
            time.sleep(1.0)

    def _push(self, rgb: np.ndarray):
        """큐를 최신 프레임 1장만 유지."""
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break
        self.frame_queue.put(rgb)

    def stop(self):
        self._stop.set()


# ── 메인 애플리케이션 ─────────────────────────────────────────────────────────


class OfficeApp(ShowBase):
    """3D 오피스 공간 시뮬레이터."""

    # 방 치수 (단위: m)
    W, D, H = 14.0, 12.0, 3.5

    def __init__(self):
        ShowBase.__init__(self)
        self.disableMouse()

        # 시점 카메라: 높이 올려 바닥 제거, 뒷벽(PLC·카메라·에어컨)만 조망
        self.camera.setPos(0, -4.5, 3.0)
        self.camera.lookAt(0, 5.5, 2.2)
        self.camLens.setFov(55)

        # 배경색 (천장 밖 = 짙은 회색)
        self.setBackgroundColor(0.13, 0.13, 0.15, 1)

        # 상태
        self.plc_voltage = 220.0
        self.plc_current  = 5.0
        self.ac_on        = False

        # 프레임 큐
        self.frame_queue = queue.Queue(maxsize=3)

        # 씬 구성
        self._setup_lighting()
        self._build_room()
        self._build_plc()
        self._build_ac()
        self._build_camera_panel()
        self._setup_texture()

        # PLC 초기값 즉시 표시
        self._refresh_plc()

        # IP 카메라 (Reolink RLC-1212A) + YOLO 워커 시작
        self._worker = CameraWorker(self.frame_queue, cam_source=RTSP_URL)
        self._worker.start()

        # 태스크 등록
        self.taskMgr.doMethodLater(5, self._task_plc,     "plc_update")   # 5초 반복
        self.taskMgr.add(          self._task_texture,    "tex_update")   # 매 프레임
        self.taskMgr.add(          self._task_ac,         "ac_update")    # 매 프레임

        self.accept("escape", self.userExit)
        print("[App] 3D 오피스 시뮬레이터 시작 | ESC: 종료")

    # ── 조명 ──────────────────────────────────────────────────────────────────

    def _setup_lighting(self):
        # 주변광
        amb = AmbientLight("amb")
        amb.setColor(Vec4(0.38, 0.38, 0.38, 1))
        self.render.setLight(self.render.attachNewNode(amb))

        # 태양광 (방향광)
        sun = DirectionalLight("sun")
        sun.setColor(Vec4(0.85, 0.85, 0.80, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(40, -55, 0)
        self.render.setLight(sun_np)

        # 천장 형광등 4개
        for px, py in [(-3.5, -2), (3.5, -2), (-3.5, 3.5), (3.5, 3.5)]:
            pl = PointLight(f"pl_{px}_{py}")
            pl.setColor(Vec4(0.75, 0.75, 0.88, 1))
            pl.setAttenuation(Vec3(0.18, 0.04, 0.002))
            pl_np = self.render.attachNewNode(pl)
            pl_np.setPos(px, py, self.H - 0.2)
            self.render.setLight(pl_np)

    # ── 오피스 방 ─────────────────────────────────────────────────────────────

    def _build_room(self):
        W, D, H = self.W, self.D, self.H
        panels = [
            ("floor",      W,    D,    0.10, (0, 0, -0.05),   (0.56, 0.52, 0.48, 1)),
            ("ceiling",    W,    D,    0.10, (0, 0,  H+0.05), (0.94, 0.94, 0.94, 1)),
            ("wall_back",  W,    0.15, H,   (0, D/2, H/2),    (0.88, 0.86, 0.84, 1)),
            # wall_front 제거: 카메라가 실내를 볼 수 있도록 앞면 개방
            ("wall_left",  0.15, D,    H,   (-W/2, 0, H/2),   (0.85, 0.84, 0.88, 1)),
            ("wall_right", 0.15, D,    H,   ( W/2, 0, H/2),   (0.85, 0.84, 0.88, 1)),
        ]
        for name, sx, sy, sz, pos, col in panels:
            b = make_box(name, sx, sy, sz, col)
            b.reparentTo(self.render)
            b.setPos(*pos)

        # 책상
        desk = make_box("desk", 2.0, 1.0, 0.06, (0.60, 0.45, 0.30, 1))
        desk.reparentTo(self.render)
        desk.setPos(0, -1.0, 0.75)
        for dx, dy in [(-0.85, -0.40), (0.85, -0.40), (-0.85, 0.40), (0.85, 0.40)]:
            leg = make_box(f"leg{dx}{dy}", 0.06, 0.06, 0.76, (0.50, 0.38, 0.25, 1))
            leg.reparentTo(self.render)
            leg.setPos(dx, -1.0 + dy, 0.38)

        # 의자
        seat = make_box("ch_seat", 0.55, 0.55, 0.06, (0.20, 0.20, 0.32, 1))
        seat.reparentTo(self.render)
        seat.setPos(0, -2.2, 0.50)
        bk = make_box("ch_back", 0.55, 0.06, 0.52, (0.20, 0.20, 0.32, 1))
        bk.reparentTo(self.render)
        bk.setPos(0, -2.0, 0.76)

        # 형광등 몸체 (천장 부착)
        for lx, ly in [(-3.5, -2), (3.5, -2), (-3.5, 3.5), (3.5, 3.5)]:
            lt = make_box(f"lamp{lx}{ly}", 0.6, 0.15, 0.05, (0.98, 0.98, 0.95, 1))
            lt.reparentTo(self.render)
            lt.setPos(lx, ly, H - 0.03)

    # ── PLC ───────────────────────────────────────────────────────────────────

    def _build_plc(self):
        # ── PLC 본체 ──────────────────────────────────────────────────────────
        # 가로 1.0 × 깊이 0.45 × 높이 1.8, 전면(y=-0.225) 기준
        DEPTH = 0.45
        FRONT = -(DEPTH / 2) - 0.01   # 전면보다 0.01 앞 → z-fighting 없음

        plc = make_box("plc_body", 1.0, DEPTH, 1.8, (0.18, 0.22, 0.20, 1))
        plc.reparentTo(self.render)
        plc.setPos(-2.8, 4.5, 0.9)
        self.plc_np = plc

        # 전면 패널: 본체 색과 살짝 다른 색으로 입체감
        fp = make_box("plc_fp", 0.90, 0.02, 1.70, (0.24, 0.28, 0.25, 1))
        fp.reparentTo(plc)
        fp.setPos(0, FRONT, 0)

        # 패널 테두리 (상단 밝은 띠 / 하단 어두운 띠로 입체감)
        top_bar = make_box("plc_top", 0.90, 0.025, 0.06, (0.45, 0.50, 0.45, 1))
        top_bar.reparentTo(plc)
        top_bar.setPos(0, FRONT - 0.005, 0.82)

        bot_bar = make_box("plc_bot", 0.90, 0.025, 0.06, (0.12, 0.14, 0.13, 1))
        bot_bar.reparentTo(plc)
        bot_bar.setPos(0, FRONT - 0.005, -0.82)

        # ── 라벨 & 텍스트: 전면 패널보다 0.01 더 앞 ────────────────────────
        TY = FRONT - 0.20

        attach_label(plc, "PLC", 0.17, (0, TY, 0.68), (0.95, 0.95, 0.95, 1))

        self._v_tn, _ = attach_label(plc, "V: 220.0 V", 0.14,
                                     (0.10, TY, 0.35), (0.20, 1.00, 0.20, 1))
        self._a_tn, _ = attach_label(plc, "A:  5.00 A", 0.14,
                                     (0.10, TY, 0.08), (1.00, 0.85, 0.15, 1))

        # ── LED 표시등: 텍스트 왼쪽, 패널 밖으로 살짝 돌출 ─────────────────
        LS = 0.06   # LED 한 변 크기
        LY = FRONT - 0.03

        self._v_led = make_box("v_led", LS, LS, LS, (1, 1, 1, 1))
        self._v_led.reparentTo(plc)
        self._v_led.setPos(-0.32, LY, 0.35)
        self._v_led.setColor(0.20, 1.00, 0.20, 1)   # 초기: 녹색

        self._a_led = make_box("a_led", LS, LS, LS, (1, 1, 1, 1))
        self._a_led.reparentTo(plc)
        self._a_led.setPos(-0.32, LY, 0.08)
        self._a_led.setColor(0.10, 0.85, 1.00, 1)   # 초기: 청색

        print("[PLC] 생성 완료")

    # ── 에어컨 ────────────────────────────────────────────────────────────────

    def _build_ac(self):
        D, H = self.D, self.H

        # 에어컨 본체 — 오른쪽 뒷벽 상단
        # 크기: 가로 2.2 × 깊이 0.35 × 높이 0.65
        # 뒷면(y+)이 뒷벽 내면(y=5.925)에 딱 맞도록 배치 → z-fighting 없음
        ac = make_box("ac", 2.2, 0.35, 0.65, (0.92, 0.92, 0.92, 1))
        ac.reparentTo(self.render)
        # hy = 0.175 → center_y = 5.925 - 0.175 = 5.75
        ac.setPos(3.5, 5.75, H - 0.65)
        self.ac_np = ac

        # 전면 패널
        ff = make_box("ac_ff", 2.10, 0.01, 0.56, (0.97, 0.97, 0.97, 1))
        ff.reparentTo(ac)
        ff.setPos(0, -0.178, -0.02)

        # 에어 슬릿 3개
        for i in range(3):
            s = make_box(f"slit{i}", 1.90, 0.01, 0.035, (0.72, 0.72, 0.72, 1))
            s.reparentTo(ac)
            s.setPos(0, -0.182, -0.06 - i * 0.075)

        # "AIR CON" 라벨
        attach_label(ac, "AIR CON", 0.14, (-0.60, -0.50, 0.22), (1.00, 0.90, 0.00, 1))

        # ON/OFF 상태 텍스트 — NodePath도 저장하여 setColor() 사용
        self._ac_tn = TextNode("ac_status")
        self._ac_tn.setAlign(TextNode.ACenter)
        self._ac_tn.setTextColor(0.95, 0.15, 0.15, 1)  # 초기: 빨간색(OFF)
        self._ac_tn.setText("OFF")
        self._ac_tn_np = ac.attachNewNode(self._ac_tn)
        self._ac_tn_np.setScale(0.20)
        self._ac_tn_np.setPos(0.45, -0.50, 0.22)  # 에어컨 사물보다 앞으로, 왼쪽으로 이동
        self._ac_tn_np.setBillboardAxis()

        # ON/OFF LED (크기 0.18 × 0.14 × 0.18)
        self._ac_led = make_box("ac_led", 0.18, 0.14, 0.18, (1, 1, 1, 1))
        self._ac_led.reparentTo(ac)
        self._ac_led.setPos(1.00, -0.185, 0.22)
        self._ac_led.setColor(0.90, 0.08, 0.08, 1)  # 초기: 빨간색(OFF)

        print("[AC] 생성 완료")

    # ── 카메라 뷰 패널 ────────────────────────────────────────────────────────

    def _build_camera_panel(self):
        D = self.D
        px, py, pz = -0.5, D / 2 - 0.18, 1.90

        # 검정 테두리 프레임
        frm = make_box("cam_frm", 4.10, 0.10, 3.10, (0.07, 0.07, 0.07, 1))
        frm.reparentTo(self.render)
        frm.setPos(px, py + 0.04, pz)

        # "CAMERA VIEW" 라벨
        attach_label(frm, "CAMERA VIEW", 0.14, (0, -0.07, 1.62), (0.30, 0.90, 1.00, 1))

        # 텍스처 화면 쿼드 (4:3 비율, 법선 = -Y)
        self._screen_np = make_screen("cam_screen", -1.92, 1.92, -1.44, 1.44)
        self._screen_np.reparentTo(self.render)
        self._screen_np.setPos(px, py, pz)

        print("[CameraPanel] 생성 완료")

    # ── 카메라 텍스처 초기화 ──────────────────────────────────────────────────

    def _setup_texture(self):
        tex = Texture("cam_feed")
        tex.setup2dTexture(640, 480, Texture.TUnsignedByte, Texture.FRgb)
        tex.setMagfilter(Texture.FTLinear)
        tex.setMinfilter(Texture.FTLinear)
        tex.setWrapU(Texture.WMClamp)
        tex.setWrapV(Texture.WMClamp)

        # 초기 화면 (검정 + 안내 문구)
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(blank, "Initializing camera...", (130, 248),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (60, 60, 60), 2)
        tex.setRamImage(np.flipud(blank).tobytes())

        self._screen_np.setTexture(tex)
        self._cam_tex = tex

    # ── PLC 값 갱신 ───────────────────────────────────────────────────────────

    def _refresh_plc(self):
        self.plc_voltage = random.uniform(207.0, 243.0)
        self.plc_current  = random.uniform(0.5, 16.5)

        self._v_tn.setText(f"V: {self.plc_voltage:5.1f} V")
        self._a_tn.setText(f"A: {self.plc_current:5.2f} A")

        # 전압 LED 색상 (정상=녹, 주의=노, 이상=적)
        if self.plc_voltage < 210 or self.plc_voltage > 240:
            self._v_led.setColor(1.0, 0.25, 0.10, 1)
        elif self.plc_voltage < 215 or self.plc_voltage > 235:
            self._v_led.setColor(1.0, 0.85, 0.10, 1)
        else:
            self._v_led.setColor(0.20, 1.00, 0.20, 1)

        # 전류 LED 색상
        if self.plc_current > 14.0:
            self._a_led.setColor(1.0, 0.20, 0.10, 1)
        elif self.plc_current > 9.0:
            self._a_led.setColor(1.0, 0.85, 0.10, 1)
        else:
            self._a_led.setColor(0.10, 0.85, 1.00, 1)

        print(f"[PLC] V={self.plc_voltage:.1f} V  "
              f"A={self.plc_current:.2f} A")

    # ── 태스크: PLC 5초 갱신 ──────────────────────────────────────────────────

    def _task_plc(self, task):
        self._refresh_plc()
        return task.again   # 동일 딜레이(5초) 후 재실행

    # ── 태스크: 카메라 텍스처 업데이트 ──────────────────────────────────────

    def _task_texture(self, task):
        try:
            frame = self.frame_queue.get_nowait()          # RGB (480, 640, 3)
            if frame.shape[:2] != (480, 640):
                frame = cv2.resize(frame, (640, 480))
            # Panda3D 텍스처 원점 = 좌하단 → 상하 반전으로 보정
            self._cam_tex.setRamImage(np.flipud(frame).tobytes())
        except queue.Empty:
            pass
        return task.cont

    # ── 태스크: 에어컨 ON/OFF 갱신 ───────────────────────────────────────────

    def _task_ac(self, task):
        detected = self._worker.person_detected
        if detected != self.ac_on:
            self.ac_on = detected
            if self.ac_on:
                # 에어컨 ON: LED 밝은 녹색, 텍스트 녹색
                self._ac_led.setColor(0.05, 0.95, 0.20, 1)
                self._ac_tn.setText("ON")
                self._ac_tn.setTextColor(0.10, 1.00, 0.30, 1)  # 초록색
                print("[AC] ON  ← 사람 감지됨")
            else:
                # 에어컨 OFF: LED 빨간색, 텍스트 빨간색
                self._ac_led.setColor(0.90, 0.08, 0.08, 1)
                self._ac_tn.setText("OFF")
                self._ac_tn.setTextColor(0.95, 0.15, 0.15, 1)  # 빨간색
                print("[AC] OFF ← 사람 없음")
        return task.cont

    # ── 종료 정리 ─────────────────────────────────────────────────────────────

    def destroy(self):
        if hasattr(self, "_worker"):
            self._worker.stop()
        super().destroy()


# ─────────────────────────────────────────────────────────────────────────────


def main():
    app = OfficeApp()
    app.run()


if __name__ == "__main__":
    main()
