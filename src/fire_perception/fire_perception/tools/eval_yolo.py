#!/usr/bin/env python3
"""역할: 학습된 src/fire_perception/models/fire_yolov8n.pt 를 검증셋(data/fire_yolo)으로 평가해
     mAP50 과 CPU 추론 FPS 를 출력한다. **/check 4 에서 사용자가 직접 실행**.
구독/발행: 없음.

사용:
  ros2 run fire_perception eval_yolo
"""
import argparse
import time
from pathlib import Path

import numpy as np


def _default_workspace_dir() -> Path:
    return Path.home() / 'fire_ws'


def main():
    ws = _default_workspace_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default=str(ws / 'src' / 'fire_perception' / 'models' / 'fire_yolov8n.pt'))
    parser.add_argument('--data', default=str(ws / 'data' / 'fire_yolo' / 'data.yaml'))
    parser.add_argument('--imgsz', type=int, default=320)
    parser.add_argument('--fps-samples', type=int, default=30)
    args = parser.parse_args()

    model_path = Path(args.model)
    if not model_path.is_file():
        raise SystemExit(f'모델 없음: {model_path} (train_yolo 먼저 실행)')

    from ultralytics import YOLO
    model = YOLO(str(model_path))

    metrics = model.val(data=args.data, imgsz=args.imgsz, device='cpu')
    map50 = float(metrics.box.map50)
    print(f'mAP50 = {map50:.3f} (목표 >= 0.80)')

    dummy = (np.random.rand(args.imgsz, args.imgsz, 3) * 255).astype('uint8')
    for _ in range(3):
        model.predict(source=dummy, imgsz=args.imgsz, device='cpu', verbose=False)
    t0 = time.time()
    for _ in range(args.fps_samples):
        model.predict(source=dummy, imgsz=args.imgsz, device='cpu', verbose=False)
    elapsed = time.time() - t0
    fps = args.fps_samples / elapsed
    print(f'CPU 추론 FPS = {fps:.1f} (목표 >= 5)')


if __name__ == '__main__':
    main()
