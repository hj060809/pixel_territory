"""화염탑: 불을 뿜는 범위 공격 건물 (설원 드래곤과 강한 동물을 막는다).

- 다 지은 화염탑은 FIRE['cd']초마다 사거리 안의 가장 가까운 적에게 불을 뿜는다. 맞은 자리 둘레의 적도 덜 맞는다.
  날고 있는 용기사, 깨어 싸우는 야생 드래곤도 맞힌다 (잠든 야생 동물은 건드리지 않는다).
- 상성: 드래곤(용기사, 야생 드래곤)은 얼음이라 불에 약하다 (FIRE['vs_dragon']), 바위거북은 껍질이 견딘다 (FIRE['vs_tortoise']).
- 연료: 한 번 뿜을 때마다 나라의 유황을 1 쓴다. 유황이 없으면 약한 불 (피해 FIRE['weak']배).
- 균형: 용기사와 1대1이면 화염탑이 아슬아슬하게 이긴다 (rules.py 화염탑 수치 참고).
화면 표시: 공격 기록(world.recent)에 6 센 불, 7 약한 불 (x0, y0 = 탑 꼭대기, x1, y1 = 맞은 자리).
"""
from __future__ import annotations

import numpy as np

from sim import rules as R


class FireTowers:
    def __init__(self, world):
        self.w = world

    def update(self, dt: float) -> None:
        w, u, b = self.w, self.w.units, self.w.builds
        F = R.FIRE
        towers = np.flatnonzero(b.alive[:b.n] & (b.kind[:b.n] == R.FIRE_TOWER) & (b.prog[:b.n] >= 1))
        if not len(towers):
            return
        ids = w.unit_ids()
        for t in towers:
            b.cd[t] -= dt
            if b.cd[t] > 0:
                continue
            o = b.own[t]
            foes = ids[(w.diplo.friend[o, u.own[ids]] == 0) & (u.own[ids] != R.NEUTRAL) & ~u.passive[ids]] if len(ids) else ids   # 동맹, 호위 중인 병사는 빼고
            if not len(foes):
                b.cd[t] = 0.3
                continue
            d = np.hypot(u.x[foes] - b.x[t], u.y[foes] - b.y[t])
            k = int(np.argmin(d))
            if d[k] > F['range']:
                b.cd[t] = 0.3
                continue
            tgt = int(foes[k])
            nat = w.nations[o]
            strong = nat.sulfur >= 1
            if strong:
                nat.sulfur -= 1
            dmg = F['dmg'] * (1.0 if strong else F['weak'])
            tx, ty = float(u.x[tgt]), float(u.y[tgt])
            near = foes[np.hypot(u.x[foes] - tx, u.y[foes] - ty) <= F['splash']]
            for j in near:
                kind = int(u.kind[j])
                mul = F['vs_dragon'] if kind in (R.DRAGON_RIDER, R.WILD_DRAGON) else F['vs_tortoise'] if kind == R.TORTOISE else 1.0
                d = dmg * mul * (1.0 if j == tgt else F['splash_mul']) * w.diplo.hurt[u.own[j]]
                u.hp[j] -= d
                w.diplo.hits[o, u.own[j]] += d
                if u.hp[j] <= 0:
                    u.alive[j] = False
            b.cd[t] = F['cd']
            w.recent.append((w.time, float(b.x[t]), float(b.y[t]), tx, ty, 6 if strong else 7))
