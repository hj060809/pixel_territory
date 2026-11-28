"""전장의 안개 (판 설정 fog, 판을 만들 때 정하고 게임 중엔 바꿀 수 없다).

나라마다 CELL칸 격자로 지금 보이는 곳 (view)과 가 본 곳 (seen)을 잰다 (update: SEC초마다).
- 보는 것: 병사 (병종 시야 k_sight), 다 지은 건물 (반지름 + build, 망루·화염탑은 tower. 자리만 잡거나 짓는 중인 건물은 보지 않고 (그 둘레 반지름 + site칸만 '가 본 곳'이 된다), 무너지면 다시 가려진다),
  배 (전함 warship, 나룻배 ferry). 배에 탄 병사는 보지 않는다 (배가 본다). 동맹은 시야를 나눈다.
- 지형은 가리지 않는다 (둘레만큼 동그랗게).
서버 (server/protocol.py)가 사람 나라마다 보이는 것만 보낸다: 남의 병사·배·야생 동물·공격은 보이는 칸에서만,
남의 건물은 본 적 있으면 마지막으로 본 모습. 화면 (web/src/game/draw.ts drawFog)은 안 가 본 곳을 가리고 가 본 곳을 어둡게.
AI는 안개를 받지 않는다 (모두 안다). 수치는 rules.FOG.
"""
from __future__ import annotations

import numpy as np
from numba import njit

from sim import rules as R


@njit(cache=True, nogil=True)
def _stamp(vis, own, xs, ys, rs, cell):
    """나라 own[k]의 vis에 (xs[k], ys[k])에서 rs[k]칸 안의 격자 칸 (가운데가 들면)을 켠다."""
    nn, gh, gw = vis.shape
    for k in range(len(xs)):
        o = own[k]
        if o < 0 or o >= nn:
            continue
        x, y, r = xs[k], ys[k], rs[k]
        gy0, gy1 = max(int((y - r) / cell), 0), min(int((y + r) / cell), gh - 1)
        gx0, gx1 = max(int((x - r) / cell), 0), min(int((x + r) / cell), gw - 1)
        r2 = r * r
        for gy in range(gy0, gy1 + 1):
            dy = (gy + 0.5) * cell - y
            for gx in range(gx0, gx1 + 1):
                dx = (gx + 0.5) * cell - x
                if dx * dx + dy * dy <= r2:
                    vis[o, gy, gx] = True


class Vision:
    def __init__(self, world):
        self.w = world
        F = R.FOG
        self.cell = int(F['cell'])
        self.gh = (world.map.H + self.cell - 1) // self.cell
        self.gw = (world.map.W + self.cell - 1) // self.cell
        nn = len(world.nations)
        self.view = np.zeros((nn, self.gh, self.gw), bool)    # 지금 보인다 (동맹 시야까지)
        self.seen = np.zeros((nn, self.gh, self.gw), bool)    # 가 본 적 있다
        self.version = np.zeros(nn, np.int64)                 # 나라마다 view·seen이 바뀔 때마다 +1 (서버가 보낸다)
        self.t = -1e9
        self.update(force=True)

    def update(self, force: bool = False) -> None:
        w = self.w
        if not force and w.time - self.t < R.FOG['sec']:
            return
        self.t = w.time
        F, u, b = R.FOG, w.units, w.builds
        nn = len(w.nations)
        xs, ys, rs, own = [], [], [], []
        ids = np.flatnonzero(u.alive[:u.n] & ~u.aboard[:u.n] & (u.own[:u.n] < nn))
        xs.append(u.x[ids]); ys.append(u.y[ids]); rs.append(w.k_sight[u.kind[ids]]); own.append(u.own[ids])
        bi = np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] < nn) & (b.prog[:b.n] >= 1))   # 다 지은 건물만
        tower = np.isin(b.kind[bi], (R.TOWER, R.FIRE_TOWER))
        xs.append(b.x[bi]); ys.append(b.y[bi]); rs.append(np.where(tower, F['tower'], b.r[bi] + F['build'])); own.append(b.own[bi])
        boats = [s for s in w.fleet.boats if s.alive and s.own < nn and s.pos >= 0]
        if boats:
            xs.append(np.array([s.x for s in boats])); ys.append(np.array([s.y for s in boats]))
            rs.append(np.array([F['warship'] if s.kind == 'warship' else F['ferry'] for s in boats]))
            own.append(np.array([s.own for s in boats]))
        si = np.flatnonzero(b.alive[:b.n] & (b.own[:b.n] < nn) & (b.prog[:b.n] < 1))   # 짓는 중: 둘레만 조금 '가 본 곳'으로
        sites = np.zeros((nn, self.gh, self.gw), np.bool_)
        if len(si):
            _stamp(sites, b.own[si].astype(np.int64), b.x[si].astype(np.float64), b.y[si].astype(np.float64),
                   (b.r[si] + F['site']).astype(np.float64), float(self.cell))
        mine = np.zeros((nn, self.gh, self.gw), np.bool_)
        _stamp(mine, np.concatenate(own).astype(np.int64), np.concatenate(xs).astype(np.float64),
               np.concatenate(ys).astype(np.float64), np.concatenate(rs).astype(np.float64), float(self.cell))
        fr = w.diplo.friend[:nn, :nn] != 0                     # 동맹 (자기 나라 포함)은 시야를 나눈다
        for a in range(nn):
            team = fr[a] | (np.arange(nn) == a)
            v = mine[team].any(axis=0)
            s = self.seen[a] | v | sites[team].any(axis=0)
            if not (np.array_equal(v, self.view[a]) and np.array_equal(s, self.seen[a])):
                self.view[a], self.seen[a] = v, s
                self.version[a] += 1

    def visible(self, nid: int, x, y) -> np.ndarray:
        """나라 nid에게 (x, y) 자리가 지금 보이나 (배열)."""
        gx = np.clip((np.asarray(x) // self.cell).astype(np.int64), 0, self.gw - 1)
        gy = np.clip((np.asarray(y) // self.cell).astype(np.int64), 0, self.gh - 1)
        return self.view[nid][gy, gx]

    def levels(self, nid: int) -> np.ndarray:
        """화면에 보낼 격자: 0 안 가 봄, 1 가 봤지만 지금은 안 보임, 2 보인다."""
        return (self.seen[nid].astype(np.uint8) + self.view[nid].astype(np.uint8))
