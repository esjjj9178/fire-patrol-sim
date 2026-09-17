"""역할: YOLOv8n(ultralytics, CPU) 기반 화재 박스 검출. 모델 파일이 없거나 로드 실패하면
     경고 후 HsvDetector 로 자동 폴백한다. 큐/드롭 정책은 vision_node 가 "최신 프레임만
     저장해두고 타이머에서 꺼내 쓰는" 방식으로 처리하므로 이 클래스는 단일 프레임 추론만 담당.
"""
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

from fire_perception.hsv_detector import HsvDetector


class YoloDetector:

    def __init__(self, model_path: str, imgsz: int = 320, conf_threshold: float = 0.4,
                 device: str = 'cpu', class_name: str = 'fire',
                 fallback: Optional[HsvDetector] = None, logger=None):
        self.imgsz = imgsz
        self.conf_threshold = conf_threshold
        self.device = device
        self.class_name = class_name
        self.fallback = fallback
        self.logger = logger
        self._model = None
        self._use_fallback = False

        path = Path(model_path) if model_path else None
        if not path or not path.is_file():
            self._warn(f'YOLO 모델 파일 없음({model_path}) -> HSV 폴백')
            self._use_fallback = True
            return

        try:
            from ultralytics import YOLO
            self._model = YOLO(str(path))
        except Exception as e:
            self._warn(f'YOLO 모델 로드 실패({e}) -> HSV 폴백')
            self._use_fallback = True

    def _warn(self, msg: str):
        if self.logger:
            self.logger.warn(msg)
        else:
            print(f'[yolo_detector] WARN: {msg}')

    @property
    def using_fallback(self) -> bool:
        return self._use_fallback

    def detect(self, bgr_image: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float]]:
        if self._use_fallback or self._model is None:
            return self.fallback.detect(bgr_image) if self.fallback is not None else []

        results = self._model.predict(
            source=bgr_image, imgsz=self.imgsz, conf=self.conf_threshold,
            device=self.device, verbose=False)
        detections = []
        for r in results:
            boxes = getattr(r, 'boxes', None)
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                conf = float(box.conf[0])
                detections.append(((x1, y1, x2, y2), conf))
        detections.sort(key=lambda d: d[1], reverse=True)
        return detections
