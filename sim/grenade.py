"""유황 척탄병의 단지 (rules.GRENADIER, rules.GRENADE).

- 척탄병이 사거리 안의 적을 치면 커널(sim/kernels/combat.py)이 던진 것만 적는다 (pots: 출발 x, y, 목표 x, y, 나라, 목표 병사, 목표 건물, 공격 배율).
- 척탄기마병의 단지도 같다 (피해·상성은 척탄병의 것).
- 단지는 GRENADE['fly']초 날아가 맞는다: 목표 병사 (아직 GRENADE['hit_r']칸 안에 있으면)나 건물에 직격 피해
  (건물 ×vs_build, 상성 rules.UNIT_VS: 바위거북 ×1.5 등). 그 자리에 burn초 동안 불 (반지름 burn_r칸): 초마다 burn_dps를 땅의 적에게.
- 설원 지역 (sim/tribes.py zones)에 떨어지면 불이 약하다 (직격·불 모두 ×snow).
- 동맹·자기 나라는 맞지 않는다 (diplomacy.friend), 날고 있는 병사·배에 탄 병사는 불을 맞지 않는다 (직격은 날고 있어도 맞는다).
화면 표시: 공격 기록(world.recent)에 15 던짐 (x0, y0 = 척탄병, x1, y1 = 겨눈 곳), 16 불 (x0, y0 = 떨어진 곳, 설원이면 x1 = 1).
"""
from __future__ import annotations

import numpy as np

from sim import rules as R

THROW_SHOT, FIRE_SHOT = 15, 16


class Grenades:
    def __init__(self, world):
        self.w = world
        self.flying: list = []        # [남은 초, x, y, 나라, 목표 병사, 목표 건물, 배율]
        self.fires: list = []         # [남은 초, x, y, 나라, 배율]

    def throw(self, rows) -> None:
        """커널이 적은 던짐 (이번 걸음)."""
        w = self.w
        for x0, y0, tx, ty, o, tu, tb, mul in rows:
            self.flying.append([R.GRENADE['fly'], float(tx), float(ty), int(o), int(tu), int(tb), float(mul)])
            w.recent.append((w.time, float(x0), float(y0), float(tx), float(ty), THROW_SHOT))

    def update(self, dt: float) -> None:
        if not self.flying and not self.fires:
            return
        w, u, b = self.w, self.w.units, self.w.builds
        G = R.GRENADE
        from sim import tribes
        snow, _ = tribes.zones(w.map)
        left = []
        for p in self.flying:
            p[0] -= dt
            if p[0] > 0:
                left.append(p)
                continue
            _, x, y, o, tu, tb, mul = p
            cold = bool(snow[min(max(int(y), 0), w.map.H - 1), min(max(int(x), 0), w.map.W - 1)])
            if cold:
                mul *= G['snow']
            dmg = R.UNIT_STATS[R.GRENADIER]['dmg'] * mul
            if tu >= 0 and u.alive[tu] and not u.aboard[tu] and np.hypot(u.x[tu] - x, u.y[tu] - y) <= G['hit_r']:
                d = dmg * w.k_vs[R.GRENADIER, u.kind[tu]] * w.diplo.hurt[u.own[tu]] * u.fx_take[tu]
                u.hp[tu] -= d
                w.diplo.hits[o, u.own[tu]] += d
                if u.hp[tu] <= 0:
                    u.alive[tu] = False
            elif tb >= 0 and b.alive[tb]:
                d = dmg * G['vs_build'] * w.diplo.hurt[b.own[tb]]
                b.hp[tb] -= d
                w.diplo.hits[o, b.own[tb]] += d
                b.last[tb] = o
            self.fires.append([G['burn'], x, y, o, mul])
            w.recent.append((w.time, x, y, 1.0 if cold else 0.0, 0.0, FIRE_SHOT))
        self.flying = left
        if not self.fires:
            return
        ids = w.unit_ids()
        keep = []
        for f in self.fires:
            f[0] -= dt
            if len(ids):
                _, x, y, o, mul = f
                near = ids[(np.hypot(u.x[ids] - x, u.y[ids] - y) <= G['burn_r']) & ~u.air[ids] & ~u.aboard[ids]]
                near = near[(w.diplo.friend[o, u.own[near]] == 0) & (u.own[near] != R.NEUTRAL)] if len(near) else near
                for j in near:
                    d = G['burn_dps'] * dt * mul * w.k_vs[R.GRENADIER, u.kind[j]] * w.diplo.hurt[u.own[j]] * u.fx_take[j]
                    u.hp[j] -= d
                    w.diplo.hits[o, u.own[j]] += d
                    if u.hp[j] <= 0:
                        u.alive[j] = False
            if f[0] > 0:
                keep.append(f)
        self.fires = keep
