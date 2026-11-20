"""마스크와 장(field) 도우미."""
from __future__ import annotations

import numpy as np
from scipy import ndimage


def ocean_of(water):
    """지도 가장자리와 이어진 물 = 바다."""
    lab, _ = ndimage.label(water)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    return np.isin(lab, border[border > 0])


def smooth_max(a, b, k=4.0):
    """부드러운 최댓값 (덩어리 이음매에 주름이 생기지 않게)."""
    d = a - b
    return 0.5 * (a + b + np.sqrt(d * d + k * k))
