"""웹 앱 아이콘 (홈 화면에 추가할 때): 게임 속 거점 픽셀 그림을 정수 배로 키워 web/public/에.

python tools/make_icons.py
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.bake.png import save_png  # noqa: E402

text = (ROOT / 'web/src/game/spriteData.ts').read_text(encoding='utf-8')
data = json.loads(re.search(r'SPRITES = (\{.*\})', text, re.S).group(1))
rows = data['buildings']['0']                                    # 거점
pal = {k: v for k, v in data['pal'].items()}
nation = (214, 70, 52)                                           # 붉은 나라 (설정 화면 첫 색)
pal['n'], pal['N'] = nation, tuple(int(c * 0.6) for c in nation)
h, w = len(rows), len(rows[0])
spr = np.zeros((h + 2, w + 2, 4), np.uint8)
filled = lambda y, x: 0 <= y < h and 0 <= x < w and rows[y][x] != '.'
for y in range(h):                                               # 어두운 1칸 테두리
    for x in range(w):
        if filled(y, x):
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if not filled(y + dy, x + dx):
                    spr[y + dy + 1, x + dx + 1] = (*data['outline'], 255)
for y in range(h):
    for x in range(w):
        if filled(y, x):
            spr[y + 1, x + 1] = (*pal[rows[y][x]], 255)

for size in (192, 512):
    bg = np.array([22, 34, 48], np.uint8)                        # 어두운 바다색 바탕
    img = np.tile(bg, (size, size, 1))
    k = int(size * 0.62 // max(spr.shape[:2]))                   # 정수 배 (도트가 고르게)
    big = np.kron(spr, np.ones((k, k, 1), np.uint8))
    y0, x0 = (size - big.shape[0]) // 2 + size // 24, (size - big.shape[1]) // 2
    a = big[..., 3:4] / 255.0
    img[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] = (big[..., :3] * a + img[y0:y0 + big.shape[0], x0:x0 + big.shape[1]] * (1 - a)).astype(np.uint8)
    save_png(ROOT / f'web/public/icon-{size}.png', img)
    print(f'web/public/icon-{size}.png ({k}배)')
