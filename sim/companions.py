"""함께 싸우는 동물의 능력 (지금은 길든 거대 바위거북: 이동형 탱커).

타깃을 지정할 수 있는 게임이라 적이 탱커를 그냥 무시할 수 있다. 그래서 무시하지 못하게:
- 발 구르기 (rules.STOMP): 붙은 땅의 적이 있으면 몇 초마다 앞발로 땅을 내리찍어 둘레 적 모두를 치고 살짝 밀어낸다.
  메인 공격이 아닌 수준이지만, 곁에 붙어 있으면 계속 맞는다.
- 낮은 포효 (rules.TAUNT): 가끔 낮게 울부짖어 둘레 적 병사들이 몇 초 동안 바위거북만 노리게 한다 (명령받은 적도).
- 껍질 숨기 (rules.HIDE): 체력이 낮아지면 껍질 속으로 숨어 잠시 받는 피해를 크게 줄인다 (그동안 움직이지도 치지도 않는다).
화면 표시: 공격 기록(world.recent)에 4 발 구르기, 5 포효 (x0, y0 = 바위거북 자리). 껍질 숨기는 병사 상태 TAME.
"""
from __future__ import annotations

import numpy as np

from sim import rules as R
from sim.entities import ATTACK, IDLE, TAME


class _St:
    __slots__ = ('gen', 'spin', 'taunt', 'curl', 'curl_cd', 'hp')

    def __init__(self, gen, hp, rng):
        self.gen, self.hp = gen, hp
        self.spin, self.taunt = 0.0, float(rng.uniform(4.0, R.TAUNT['cd']))
        self.curl, self.curl_cd = 0.0, 0.0


class Companions:
    def __init__(self, world):
        self.w = world
        self.st: dict[int, _St] = {}
        self.taunted: dict[int, tuple] = {}          # 적 병사 → (끝나는 시각, 바위거북, 그 병사 세대, 바위거북 세대)

    def _foes(self, i: int, r: float):
        """바위거북 i의 둘레 r 안의 땅의 적 (야생 동물·배에 탄 병사·날고 있는 병사는 빼고)."""
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        o = u.own[i]
        ids = ids[(w.diplo.friend[o, u.own[ids]] == 0) & (u.own[ids] < R.NEUTRAL) & ~u.air[ids]]   # 동맹은 빼고
        if not len(ids):
            return ids
        return ids[np.hypot(u.x[ids] - u.x[i], u.y[ids] - u.y[i]) <= r]

    def update(self, dt: float) -> None:
        w, u, m = self.w, self.w.units, self.w.map
        ids = np.flatnonzero((u.kind[:u.n] == R.TORTOISE) & (u.own[:u.n] < R.NEUTRAL)
                             & (u.alive[:u.n] | np.isin(np.arange(u.n), list(self.st))))
        maxhp = R.UNIT_STATS[R.TORTOISE]['hp']
        for i in ids:
            i = int(i)
            s = self.st.get(i)
            if s is None or s.gen != int(u.gen[i]):
                if not u.alive[i]:
                    self.st.pop(i, None)
                    continue
                s = self.st[i] = _St(int(u.gen[i]), float(u.hp[i]), w.rng)
            # 껍질 숨기: 받은 피해를 줄인다 (막 쓰러졌어도 줄인 만큼 남으면 되살린다)
            if s.curl > 0:
                s.curl -= dt
                if u.hp[i] < s.hp:
                    u.hp[i] = s.hp - (s.hp - u.hp[i]) * (1 - R.HIDE['cut'])
                    if u.hp[i] > 0:
                        u.alive[i] = True
                u.state[i], u.tgt[i], u.tgb[i], u.slot[i] = TAME, -1, -1, -1
                if s.curl <= 0:
                    u.state[i] = IDLE
                s.hp = float(u.hp[i])
                continue
            if not u.alive[i]:
                self.st.pop(i, None)
                continue
            s.curl_cd -= dt
            if u.hp[i] < maxhp * R.HIDE['hp'] and s.curl_cd <= 0:
                s.curl, s.curl_cd = R.HIDE['t'], R.HIDE['cd']
                u.state[i], u.tgt[i], u.tgb[i], u.slot[i] = TAME, -1, -1, -1
                s.hp = float(u.hp[i])
                continue
            s.hp = float(u.hp[i])
            # 발 구르기
            s.spin -= dt
            if s.spin <= 0:
                near = self._foes(i, R.STOMP['r'])
                if len(near):
                    s.spin = R.STOMP['cd']
                    for j in near:                                   # 둘레 땅의 적을 치고 밀어낸다
                        d = R.STOMP['dmg'] * w.diplo.hurt[u.own[j]] * u.fx_take[j]
                        u.hp[j] -= d
                        w.diplo.hits[u.own[i], u.own[j]] += d
                        if u.hp[j] <= 0:
                            u.alive[j] = False
                        d = max(float(np.hypot(u.x[j] - u.x[i], u.y[j] - u.y[i])), 0.3)
                        nx, ny = u.x[j] + (u.x[j] - u.x[i]) / d * R.STOMP['push'], u.y[j] + (u.y[j] - u.y[i]) / d * R.STOMP['push']
                        if 0 <= ny < m.H and 0 <= nx < m.W and m.walk[int(ny), int(nx)]:
                            u.x[j], u.y[j] = nx, ny
                    w.recent.append((w.time, float(u.x[i]), float(u.y[i]), float(u.x[i]), float(u.y[i]), 4))
                else:
                    s.spin = 0.3
            # 낮은 포효 (어그로)
            s.taunt -= dt
            if s.taunt <= 0:
                near = self._foes(i, R.TAUNT['r'])
                if len(near):
                    s.taunt = R.TAUNT['cd']
                    w.wild.release(near)
                    for j in near:
                        self.taunted[int(j)] = (w.time + R.TAUNT['t'], i, int(u.gen[j]), int(u.gen[i]))
                    w.recent.append((w.time, float(u.x[i]), float(u.y[i]), float(u.x[i]), float(u.y[i]), 5))
                else:
                    s.taunt = 1.0
        # 포효에 끌린 적: 그동안은 바위거북만 노린다
        for j, (until, src, g, gs) in list(self.taunted.items()):
            ok = u.alive[j] and u.gen[j] == g and u.alive[src] and u.gen[src] == gs and not u.aboard[j]
            if not ok or w.time > until:
                if ok and u.state[j] == ATTACK and u.tgt[j] == src:
                    u.state[j], u.tgt[j] = IDLE, -1               # 끝나면 알아서 가까운 적과 싸운다
                del self.taunted[j]
                continue
            u.state[j], u.tgt[j], u.tgb[j], u.bld[j] = ATTACK, src, -1, -1
            u.slot[j] = -1
