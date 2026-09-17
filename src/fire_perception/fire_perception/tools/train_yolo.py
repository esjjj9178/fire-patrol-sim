#!/usr/bin/env python3
"""역할: data/fire_yolo/data.yaml 로 YOLOv8n(CPU) 을 학습해
     src/fire_perception/models/fire_yolov8n.pt 를 만든다.
     **/check 4 에서 사용자가 직접 실행**(CPU 전용, 대략 10~30분 소요).
구독/발행: 없음.

사용:
  ros2 run fire_perception train_yolo
  ros2 run fire_perception train_yolo --resume   # 중간에 끊긴 학습 이어서

ultralytics 는 runs/detect/<name>/weights/{last,best}.pt 에 체크포인트를 남기므로,
같은 --name 으로 다시 실행하고 --resume 을 주면 이어서 학습한다.
"""
import argparse
import shutil
import time
from pathlib import Path


def _default_workspace_dir() -> Path:
    return Path.home() / 'fire_ws'


def main():
    ws = _default_workspace_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', default=str(ws / 'data' / 'fire_yolo' / 'data.yaml'))
    parser.add_argument('--epochs', type=int, default=25)
    parser.add_argument('--imgsz', type=int, default=320)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--workers', type=int, default=2)
    parser.add_argument('--name', default='fire_yolov8n')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--out', default=str(ws / 'src' / 'fire_perception' / 'models' / 'fire_yolov8n.pt'),
                         help='학습 완료 후 best.pt 를 복사할 경로')
    args = parser.parse_args()

    data_path = Path(args.data)
    if not data_path.is_file():
        raise SystemExit(f'data.yaml 없음: {data_path} (auto_label 먼저 실행)')

    from ultralytics import YOLO

    per_epoch_est_s = 25  # CPU/320px/batch16 기준 대략치(실측과 다를 수 있음)
    est_min = args.epochs * per_epoch_est_s / 60.0
    print(f'예상 소요시간: 약 {est_min:.0f}분(대략치, CPU 성능에 따라 다름) - epochs={args.epochs}')

    t0 = time.time()
    model = YOLO('yolov8n.pt')
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=args.workers,
        device='cpu',
        project=str(ws / 'runs' / 'detect'),
        name=args.name,
        resume=args.resume,
    )
    elapsed_min = (time.time() - t0) / 60.0
    print(f'학습 완료: {elapsed_min:.1f}분 소요')

    best = ws / 'runs' / 'detect' / args.name / 'weights' / 'best.pt'
    if not best.is_file():
        raise SystemExit(f'best.pt 를 찾을 수 없음: {best}')

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(best, out_path)
    print(f'모델 복사: {best} -> {out_path}')


if __name__ == '__main__':
    main()
