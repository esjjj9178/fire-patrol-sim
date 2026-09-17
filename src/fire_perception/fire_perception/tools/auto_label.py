#!/usr/bin/env python3
"""역할: data/raw/ 의 원본 이미지에 HSV 검출기로 bbox 를 자동 라벨링해 YOLO 형식 데이터셋을 만든다.
     **/check 4 에서 사용자가 직접 실행**(시뮬/ROS 불필요 — 순수 오프라인 이미지 처리).
구독/발행: 없음 (파일 입출력 전용 CLI 도구)

사용:
  ros2 run fire_perception auto_label
  ros2 run fire_perception auto_label --raw-dir ~/fire_ws/data/raw --out-dir ~/fire_ws/data/fire_yolo

출력:
  data/fire_yolo/images/{train,val}/*.png, labels/{train,val}/*.txt, data.yaml
  data/preview/*.png (라벨 bbox 를 그린 미리보기 몇 장)
불이 없는 이미지는 빈 라벨 파일로 남긴다(YOLO 표준 음성 샘플 — 배경 학습에 필요).
"""
import argparse
import random
from pathlib import Path

import cv2

from fire_perception.hsv_detector import HsvDetector


def _default_workspace_dir() -> Path:
    return Path.home() / 'fire_ws'


def label_image(detector: HsvDetector, img_path: Path):
    img = cv2.imread(str(img_path))
    if img is None:
        return None, []
    h, w = img.shape[:2]
    detections = detector.detect(img)
    lines = []
    for (x1, y1, x2, y2), _conf in detections:
        cx = (x1 + x2) / 2.0 / w
        cy = (y1 + y2) / 2.0 / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        lines.append(f'0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}')
    return img, lines


def main():
    ws = _default_workspace_dir()
    parser = argparse.ArgumentParser()
    parser.add_argument('--raw-dir', default=str(ws / 'data' / 'raw'))
    parser.add_argument('--out-dir', default=str(ws / 'data' / 'fire_yolo'))
    parser.add_argument('--preview-dir', default=str(ws / 'data' / 'preview'))
    parser.add_argument('--split', type=float, default=0.8, help='train 비율')
    parser.add_argument('--preview-count', type=int, default=8)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    out_dir = Path(args.out_dir)
    preview_dir = Path(args.preview_dir)

    images = sorted(raw_dir.glob('*.png')) + sorted(raw_dir.glob('*.jpg'))
    if not images:
        raise SystemExit(f'원본 이미지가 없음: {raw_dir} (collect_images 먼저 실행)')

    detector = HsvDetector()

    random.seed(args.seed)
    shuffled = images[:]
    random.shuffle(shuffled)
    n_train = int(len(shuffled) * args.split)
    splits = {'train': shuffled[:n_train], 'val': shuffled[n_train:]}

    for split_name in splits:
        (out_dir / 'images' / split_name).mkdir(parents=True, exist_ok=True)
        (out_dir / 'labels' / split_name).mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    n_labeled = 0
    n_empty = 0
    preview_saved = 0

    for split_name, files in splits.items():
        for img_path in files:
            img, lines = label_image(detector, img_path)
            if img is None:
                continue
            dst_img = out_dir / 'images' / split_name / img_path.name
            dst_lbl = out_dir / 'labels' / split_name / (img_path.stem + '.txt')
            cv2.imwrite(str(dst_img), img)
            dst_lbl.write_text('\n'.join(lines) + ('\n' if lines else ''))

            if lines:
                n_labeled += 1
            else:
                n_empty += 1

            if lines and preview_saved < args.preview_count:
                preview = img.copy()
                h, w = preview.shape[:2]
                for line in lines:
                    _, cx, cy, bw, bh = (float(v) for v in line.split())
                    x1 = int((cx - bw / 2) * w)
                    y1 = int((cy - bh / 2) * h)
                    x2 = int((cx + bw / 2) * w)
                    y2 = int((cy + bh / 2) * h)
                    cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.imwrite(str(preview_dir / img_path.name), preview)
                preview_saved += 1

    data_yaml = out_dir / 'data.yaml'
    data_yaml.write_text(
        f'path: {out_dir}\n'
        f'train: images/train\n'
        f'val: images/val\n'
        f'names:\n'
        f'  0: fire\n'
    )

    print(f'라벨링 완료: {len(images)}장 (불 검출 {n_labeled} / 배경 {n_empty}), '
          f'train {len(splits["train"])} / val {len(splits["val"])}')
    print(f'data.yaml: {data_yaml}')
    print(f'미리보기 {preview_saved}장: {preview_dir}')


if __name__ == '__main__':
    main()
