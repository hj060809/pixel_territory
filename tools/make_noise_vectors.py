"""웹 클라이언트가 옮길 '지도와 상관없는 노이즈'의 정답 값 (3단계 TypeScript 포팅 검증용).

python tools/make_noise_vectors.py  → assets/test/noise_vectors.json
- OpenSimplex(시드).noise2(x, y) 값 (시드 0, 31 / 음수·큰 좌표 포함)
- 셰이더 색 노이즈(_fbm 두 장 → RGB 변화량)와 물결 흐름 노이즈 필드의 몇 칸 (512 지도)
"""
import json
import sys
from pathlib import Path

import numpy as np
import opensimplex

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.render.shader import PixelArtShader, _fbm  # noqa: E402
from engine.render.water import PARAMS, water_noise_fields  # noqa: E402

rng = np.random.default_rng(1)
coords = np.concatenate([rng.uniform(-50, 50, (40, 2)), rng.uniform(0, 5000, (20, 2)), [[0, 0], [0.5, 0.5], [1e-9, -1e-9]]])
out = {'noise2': []}
for seed in (0, 31):
    gen = opensimplex.OpenSimplex(seed)
    out['noise2'] += [{'seed': seed, 'x': float(x), 'y': float(y), 'v': float(gen.noise2(x, y))} for x, y in coords]

H = W = 512
pix = [(0, 0), (0, 511), (511, 0), (511, 511), (100, 200), (256, 256), (377, 41)]
sh = PixelArtShader()
gen = opensimplex.OpenSimplex(sh.seed)
warm = _fbm(gen, H, W, sh.color_noise_scale, 3, 0.0)
bright = _fbm(gen, H, W, sh.color_noise_scale * 0.7, 3, 1000.0)
out['color_noise'] = [{'y': y, 'x': x, 'warm': float(warm[y, x]), 'bright': float(bright[y, x])} for y, x in pix]
F = water_noise_fields(H, W, PARAMS)
out['water_fields'] = [{'y': y, 'x': x, **{k: float(F[k][y, x]) for k in F}} for y, x in pix]
dst = Path(__file__).resolve().parents[1] / 'assets' / 'test' / 'noise_vectors.json'
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(json.dumps(out, indent=1), encoding='utf-8')
print('saved', dst, len(out['noise2']), 'noise2 values')
