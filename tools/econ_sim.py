"""경제 비교: AI끼리 여러 판을 돌려 정한 시각마다 나라별 자원·수입·병사·건물을 본다 (docs/ECONOMY_PLAN.md 단계마다 숫자 확인용).

시작 지형(시작 거점 둘레 R칸의 설원·사막 비율)으로 나라를 나눠 평균을 낸다 (온대 / 설원 / 사막).
나라의 부족 판정이 들어가면 (5단계, sim/tribes.py) 그 판정으로 바꾼다.

python -m tools.econ_sim                       # 시드 4개, 5나라, 600초
python -m tools.econ_sim --seeds 1 2 3 --at 300 600 900 --nations 6
"""
from __future__ import annotations

import argparse
import time
from collections import defaultdict

import numpy as np

from engine.mapgen.defaults import default_config
from engine.render import materials as S
from engine.render.seasons import SeasonCycle
from engine.scene import TerrainScene
from sim import rules as R
from sim.match import Match
from sim.terrain import GameMap
from sim.world import World

START_R = 20                 # 시작 지형을 볼 둘레 (칸)
START_SHARE = 0.4            # 이 비율 이상이면 그 지형에서 시작한 나라


def start_kind(gm, y: int, x: int) -> str:
    """시작 거점 둘레의 지형으로 '온대' / '설원' / '사막'."""
    pre = gm.layers['pre']
    y0, y1, x0, x1 = max(y - START_R, 0), y + START_R + 1, max(x - START_R, 0), x + START_R + 1
    land = gm.land[y0:y1, x0:x1]
    if not land.any():
        return '온대'
    p = pre[y0:y1, x0:x1]
    snow = (np.isin(p, (S.SNOW, S.SNOW_OLD, S.ICE, S.TUNDRA)) & land).sum() / land.sum()
    sand = (np.isin(p, (S.DESERT, S.DUNE)) & land).sum() / land.sum()
    if max(snow, sand) < START_SHARE:
        return '온대'
    return '설원' if snow >= sand else '사막'


def snapshot(w) -> list[dict]:
    out = []
    for n in w.nations:
        out.append(dict(alive=n.alive, res=list(n.res), rate=list(n.rate), sulfur=n.sulfur,
                        units=n.n_units, builds=int(sum(len(w.building_ids(n.id, k)) for k in R.BUILD_STATS)),
                        cap=float(sum(getattr(n, 'caps', [0.0] * 4)[:3]) / 3), stores=0))
    return out


def play(seed: int, nations: int, at: list[int], size: int, cache_dir: str):
    scene = TerrainScene.load(default_config(size, seed), cache_dir, progress=lambda s: None)
    gm = GameMap(scene)
    w = World(gm, nations, seed=seed * 7 + 1, map_seed=seed)
    kinds = {}
    for n in w.nations:
        halls = w.building_ids(n.id, R.HALL)
        kinds[n.id] = start_kind(gm, int(w.builds.y[halls[0]]), int(w.builds.x[halls[0]])) if len(halls) else '온대'
    m = Match(w)
    cyc = SeasonCycle(year=0.05, year_length=360)
    painted, shots = None, {}
    for t in range(1, max(at) + 1):
        cyc.advance(1 / 360)
        step = int(cyc.year * 240)
        if step != painted:
            painted = step
            gm.set_season(cyc.weights())
        m.update(1.0, cyc.weights())
        if t in at:
            shots[t] = snapshot(w)
    return kinds, shots, len(w.sites), {k: sum(1 for s in w.sites if s.kind == k) for k in range(5)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seeds', type=int, nargs='+', default=[8767564, 12345, 777, 4242])
    ap.add_argument('--nations', type=int, default=5)
    ap.add_argument('--at', type=int, nargs='+', default=[300, 600])
    ap.add_argument('--size', type=int, default=512)
    ap.add_argument('--cache', default='.cache')
    a = ap.parse_args()
    agg = defaultdict(list)                      # (시각, 시작 지형) → 스냅샷들
    sites_total = defaultdict(int)
    t0 = time.perf_counter()
    for seed in a.seeds:
        kinds, shots, _, per_kind = play(seed, a.nations, a.at, a.size, a.cache)
        for k, v in per_kind.items():
            sites_total[k] += v
        print(f'시드 {seed}: 시작 지형 {sorted(kinds.values())}, 자원지 {per_kind}  ({time.perf_counter() - t0:.0f}초)', flush=True)
        for t, snap in shots.items():
            for nid, s in enumerate(snap):
                agg[(t, kinds[nid])].append(s)
    names = R.RES_NAMES
    print(f'\n자원지 합 (시드 {len(a.seeds)}개): ' + ', '.join(f'{R.SITE_NAMES[k]} {v}' for k, v in sites_total.items()))
    for t in a.at:
        print(f'\n== {t}초 ==')
        print(f'{"시작":<4} {"수":>3} {"살아남음":>6} ' + ' '.join(f'{n:>7}' for n in names) + '   '
              + ' '.join(f'{n + "/초":>7}' for n in names) + f' {"병사":>6} {"건물":>5} {"창고":>5} {"한도":>6}')
        for kind in ('온대', '설원', '사막'):
            rows = agg.get((t, kind))
            if not rows:
                continue
            mean = lambda f: float(np.mean([f(r) for r in rows]))
            print(f'{kind:<4} {len(rows):>3} {mean(lambda r: r["alive"]) * 100:>5.0f}% '
                  + ' '.join(f'{mean(lambda r, k=k: r["res"][k]):>7.0f}' for k in range(3)) + '   '
                  + ' '.join(f'{mean(lambda r, k=k: r["rate"][k]):>7.2f}' for k in range(3))
                  + f' {mean(lambda r: r["units"]):>6.1f} {mean(lambda r: r["builds"]):>5.1f}'
                  + f' {mean(lambda r: r["stores"]):>5.1f} {mean(lambda r: r["cap"]):>6.0f}')


if __name__ == '__main__':
    main()
