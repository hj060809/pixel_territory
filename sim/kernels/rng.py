"""numba 난수 시드. numba 안의 np.random은 파이썬 쪽 np.random.seed와 따로 놀아서, 여기서 따로 정한다."""
import numpy as np
from numba import njit


@njit(cache=True)
def seed(s):
    np.random.seed(s)
