"""역할: HSV 색공간 기반 빨간 박스(불) 검출. vision_node 의 backend 중 하나이자
     yolo_detector 의 모델 없음/로드 실패 시 폴백으로도 쓰인다.
"""
from typing import List, Tuple

import cv2
import numpy as np


class HsvDetector:
    """파라미터는 config/perception.yaml 의 hsv_detector 절에서 주입된다."""

    def __init__(self, hue_low1=0, hue_low2=10, hue_high1=170, hue_high2=179,
                 sat_min=120, val_min=80, min_area_px=60, morph_kernel=5):
        self.hue_low1 = hue_low1
        self.hue_low2 = hue_low2
        self.hue_high1 = hue_high1
        self.hue_high2 = hue_high2
        self.sat_min = sat_min
        self.val_min = val_min
        self.min_area_px = min_area_px
        self.morph_kernel = max(1, int(morph_kernel))

    def detect(self, bgr_image: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], float]]:
        """반환: [((x1,y1,x2,y2), confidence), ...] 넓은 순으로 정렬."""
        hsv = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2HSV)
        lower1 = np.array([self.hue_low1, self.sat_min, self.val_min])
        upper1 = np.array([self.hue_low2, 255, 255])
        lower2 = np.array([self.hue_high1, self.sat_min, self.val_min])
        upper2 = np.array([self.hue_high2, 255, 255])
        mask = cv2.inRange(hsv, lower1, upper1) | cv2.inRange(hsv, lower2, upper2)

        if self.morph_kernel > 1:
            kernel = np.ones((self.morph_kernel, self.morph_kernel), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        h, w = bgr_image.shape[:2]
        img_area = float(h * w)

        results = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area_px:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            bbox = (x, y, x + bw, y + bh)
            area_ratio = area / img_area
            region_sat = hsv[y:y + bh, x:x + bw, 1]
            mean_sat = float(np.mean(region_sat)) / 255.0 if region_sat.size else 0.0
            confidence = float(np.clip(0.5 * min(1.0, area_ratio * 40.0) + 0.5 * mean_sat, 0.0, 1.0))
            results.append((bbox, confidence))

        results.sort(key=lambda r: (r[0][2] - r[0][0]) * (r[0][3] - r[0][1]), reverse=True)
        return results
