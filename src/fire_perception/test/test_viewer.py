"""viewer_node 의 순수 함수(draw_score_bars/thermal_to_colormap)를 검증한다(ROS/시뮬 불필요)."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fire_perception.viewer_node import draw_score_bars, thermal_to_colormap  # noqa: E402


def test_draw_score_bars_shape():
    panel = draw_score_bars(213, 300, {'vision': 0.9, 'thermal': 0.8, 'gas': 0.6, 'fused': 0.83},
                             'CONFIRMED', 'APPROACH', 720.0)
    assert panel.shape == (300, 213, 3)
    assert panel.dtype == np.uint8


def test_draw_score_bars_handles_missing_key():
    panel = draw_score_bars(100, 150, {}, 'NONE', 'PATROL', 0.0)
    assert panel.shape == (150, 100, 3)


def test_thermal_to_colormap_hot_pixel_and_tmax():
    kelvin = np.full((24, 32), 293.0, dtype=np.float32)
    kelvin[10, 20] = 600.0
    color, tmax, hot_xy = thermal_to_colormap(kelvin, 330.0, 450.0, 320, 240)
    assert color.shape == (240, 320, 3)
    assert tmax == 600.0
    scale_x, scale_y = 320 / 32, 240 / 24
    assert hot_xy == (int(20 * scale_x), int(10 * scale_y))


def test_thermal_to_colormap_clips_below_low():
    kelvin = np.full((4, 4), 293.0, dtype=np.float32)
    color, tmax, _ = thermal_to_colormap(kelvin, 330.0, 450.0, 8, 8)
    assert tmax == 293.0
    # 293K < low_k(330) -> 정규화 0 -> INFERNO 최저색(어두운 보라/검정 계열)이어야 함
    assert color.max() < 255
