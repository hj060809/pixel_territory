"""데모 지도 굽기: python -m engine.bake [--out assets/maps] [--size 512] [--only 이름 ...]

데모 지도마다 assets/maps/<이름>/ 에 bundle.tsb, day.png, ref/*.png(기준 그림)와 maps.json(목록)을 만든다.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from engine.bake import bake_scene
from engine.mapgen import load_preset
from engine.mapgen.defaults import default_config
from engine.scene import TerrainScene

# 데모 지도: (이름, 표시 이름, 프리셋, 시드)
DEMO = [
    ('default', '기본', None, 8767564),
    ('continent', '대륙', 'continent', 42),
    ('tropical', '열대 섬', 'tropical_islands', 42),
    ('island_arc', '열도', 'island_arc', 42),
    ('varied', '다양한 기후', 'varied_climates', 42),
]
# 기준 그림: (이름, 시각, 계절 비중, 물결 시각)
REFERENCE = [
    ('noon_summer', 12.0, (0, 1, 0, 0), 0.0),
    ('morning_spring', 7.5, (1, 0, 0, 0), 3.2),
    ('dusk_autumn', 17.6, (0, 0, 1, 0), 11.7),
    ('twilight_late_autumn', 19.2, (0, 0, 0.3, 0.7), 25.0),
    ('night_winter', 23.5, (0, 0, 0, 1), 40.4),
    ('noon_neutral_still', 12.0, None, None),
]


def main() -> None:
    p = argparse.ArgumentParser(description='데모 지도를 웹용 묶음으로 굽는다')
    p.add_argument('--out', default='assets/maps')
    p.add_argument('--size', type=int, default=512)
    p.add_argument('--cache-dir', default='.cache')
    p.add_argument('--only', nargs='*', help='이 이름의 지도만')
    args = p.parse_args()
    out = Path(args.out)
    listing = []
    for key, title, preset, seed in DEMO:
        if args.only and key not in args.only:
            continue
        t0 = time.time()
        cfg = default_config(args.size, seed)
        cfg = load_preset(preset, cfg) if preset else cfg
        scene = TerrainScene.load(cfg, args.cache_dir, progress=lambda s: None)
        info = bake_scene(scene, out / key, cfg, title, REFERENCE)
        info.update(key=key, preset=preset, seed=seed, seconds=round(time.time() - t0, 1))
        listing.append(info)
        print(f'{key:12s} {title:8s} 묶음 {info["bundle_bytes"] / 1e6:.2f} MB (압축 전 {info["raw_bytes"] / 1e6:.1f} MB) '
              f'{info["seconds"]}초', flush=True)
    if not args.only:
        (out / 'maps.json').write_text(json.dumps({'maps': listing, 'reference': [
            {'name': n, 'hour': h, 'season': s, 'wave_t': t} for n, h, s, t in REFERENCE]}, ensure_ascii=False, indent=1),
            encoding='utf-8')


if __name__ == '__main__':
    main()
