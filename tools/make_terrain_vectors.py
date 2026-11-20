"""웹 CPU 단계(계절 칠하기 + 물결)의 정답 그림: client_ref로 빛을 입히기 전 그림을 뽑는다.

python tools/make_terrain_vectors.py → assets/test/terrain/<지도>/<장면>.rgb (H*W*3 바이트) + states.json
웹 쪽 검사: node --experimental-strip-types web/tests/terrain_check.mts
"""
import json
import sys
from pathlib import Path

import numpy as np

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB))
from engine.bake.client_ref import BundleRenderer  # noqa: E402
from engine.bake.container import unpack  # noqa: E402

STATES = [('neutral', None, None), ('summer_still', (0, 1, 0, 0), None), ('spring_wave', (1, 0, 0, 0), 3.2),
          ('autumn_wave', (0, 0, 1, 0), 11.7), ('late_autumn', (0, 0, 0.3, 0.7), 25.0), ('winter', (0, 0, 0, 1), 40.4)]

for name in sys.argv[1:] or ['default']:
    meta, arrays = unpack((WEB / 'assets' / 'maps' / name / 'bundle.tsb').read_bytes())
    r = BundleRenderer(meta, arrays)
    out = WEB / 'assets' / 'test' / 'terrain' / name
    out.mkdir(parents=True, exist_ok=True)
    for key, season, t in STATES:
        day, ice = r.paint(season)
        base = day if t is None else r.waves(day, t)
        if t is not None and season is not None and ice.any():
            base[ice] = day[ice]
        (out / f'{key}.rgb').write_bytes(np.ascontiguousarray(base).tobytes())
    (out / 'states.json').write_text(json.dumps([{'name': k, 'season': s, 'wave_t': t} for k, s, t in STATES]))
    print('saved', out)
