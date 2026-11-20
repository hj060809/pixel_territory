"""병사와 건물: 배열 묶음(구조체 대신 배열)으로 들고 다닌다. 한 걸음 계산은 sim.kernels.combat.

병사 상태
- IDLE: 서 있다. 시야 안의 적이 오면 싸운다
- MOVE: 거리 지도를 따라 이동. 적이 있어도 무시한다 (후퇴할 때)
- AMOVE: 공격하며 이동. 가다가 시야 안의 적과 싸운다
- ATTACK: 정해 준 적 병사/건물을 쫓아가 친다
- BUILD: 건물 자리로 가서 짓는다

자연: 숲 속의 병사는 화살을 덜 맞는다 (cover). 걷는 속도는 지형을 따른다 (평지 1, 숲·습지·산은 느리다).
"""
from __future__ import annotations

import numpy as np

IDLE, MOVE, AMOVE, ATTACK, BUILD = range(5)


class Units:
    def __init__(self, cap: int = 4000):
        self.cap = cap
        self.x = np.zeros(cap, np.float32)
        self.y = np.zeros(cap, np.float32)
        self.hp = np.zeros(cap, np.float32)
        self.own = np.zeros(cap, np.int16)
        self.kind = np.zeros(cap, np.int8)
        self.state = np.zeros(cap, np.int8)
        self.slot = np.full(cap, -1, np.int16)
        self.tgt = np.full(cap, -1, np.int32)
        self.tgb = np.full(cap, -1, np.int32)
        self.bld = np.full(cap, -1, np.int32)
        self.cd = np.zeros(cap, np.float32)
        self.search = np.zeros(cap, np.float32)
        self.anim = np.zeros(cap, np.float32)
        self.moving = np.zeros(cap, np.bool_)
        self.alive = np.zeros(cap, np.bool_)
        self.aboard = np.zeros(cap, np.bool_)      # 배에 타고 있다 (걷지도 싸우지도 않고, 표적도 되지 않는다)
        self.gen = np.zeros(cap, np.uint16)        # 칸을 새로 쓸 때마다 +1 (화면이 '같은 병사'인지 알게)
        self.n = 0                       # 쓴 적 있는 칸 수 (alive가 아닌 칸은 다시 쓴다)

    def add(self, own, kind, x, y, hp) -> int:
        free = np.flatnonzero(~self.alive[:self.n])
        if len(free):
            i = int(free[0])
        elif self.n < self.cap:
            i = self.n
            self.n += 1
        else:
            return -1
        self.x[i], self.y[i], self.hp[i] = x, y, hp
        self.own[i], self.kind[i], self.state[i] = own, kind, IDLE
        self.slot[i] = self.tgt[i] = self.tgb[i] = self.bld[i] = -1
        self.cd[i] = self.search[i] = 0.0
        self.anim[i] = np.random.random() * 4
        self.alive[i] = True
        self.aboard[i] = False
        self.gen[i] = (int(self.gen[i]) + 1) & 0xFFFF
        return i


class Buildings:
    def __init__(self, cap: int = 600):
        self.cap = cap
        self.x = np.zeros(cap, np.float32)
        self.y = np.zeros(cap, np.float32)
        self.kind = np.zeros(cap, np.int8)
        self.own = np.zeros(cap, np.int16)
        self.hp = np.zeros(cap, np.float32)
        self.maxhp = np.zeros(cap, np.float32)
        self.r = np.zeros(cap, np.float32)
        self.prog = np.zeros(cap, np.float32)      # 0~1, 1이면 완성
        self.cd = np.zeros(cap, np.float32)
        self.site = np.full(cap, -1, np.int32)
        self.alive = np.zeros(cap, np.bool_)
        self.queue = [[] for _ in range(cap)]      # 거점의 훈련 대기열 [(종류, 남은 시간)]
        self.gen = np.zeros(cap, np.uint16)        # 칸을 새로 쓸 때마다 +1
        self.n = 0

    def add(self, own, kind, x, y, hp, r, prog=0.0, site=-1) -> int:
        free = np.flatnonzero(~self.alive[:self.n])
        if len(free):
            i = int(free[0])
        elif self.n < self.cap:
            i = self.n
            self.n += 1
        else:
            return -1
        self.x[i], self.y[i], self.kind[i], self.own[i] = x, y, kind, own
        self.maxhp[i] = hp
        self.hp[i] = hp * max(prog, 0.1)
        self.r[i], self.prog[i], self.site[i], self.cd[i] = r, prog, site, 0.0
        self.alive[i] = True
        self.queue[i] = []
        self.gen[i] = (int(self.gen[i]) + 1) & 0xFFFF
        return i
