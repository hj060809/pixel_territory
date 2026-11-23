"""외교: 동맹과 관계 (OpenFront.io의 동맹을 이 게임에 맞게 옮겼다).

관계 (rel[a, b]: a가 b를 어떻게 보나, -100 ~ 100, 처음 0):
- 적대 (< -50), 경계 (< 0), 보통 (< 50), 우호 (≥ 50). 시간이 지나면 0 쪽으로 천천히 돌아온다 (REL_DECAY).
- b의 병사·건물이 a를 치면 (입힌 피해만큼) a의 b에 대한 관계가 떨어진다.
- 동맹을 맺으면 서로 +60, 자원·병력을 보내 주면 받은 쪽이 고마워한다, 공격을 요청받은 나라는 요청한 나라를 미워한다 (-40).

동맹 (두 나라 사이):
- 요청: 상대의 거점을 눌러 보낸다. REQUEST_TIME 안에 답하지 않으면 사라지고, 거절당하면 REJECT_COOLDOWN 동안 다시 못 보낸다.
  서로 요청하면 바로 맺어진다.
- 맺으면: 서로의 병사·망루·화염탑·전함·바위거북이 서로를 치지 않는다 (명령해도 칠 수 없다).
  자원 보내기 (자원마다 가진 것의 몇 % (최대 DONATE_MAX), DONATE_CD마다),
  병력 보내기 (고른 병사가 동맹의 가장 가까운 거점으로 가서 닿으면 동맹의 병사가 된다. 바다 건너인데 출발하는 땅에
  내 항구가 없으면 못 보낸다. DONATE_CD마다 따로),
  공격 요청 (동맹들에게 한 나라를 TARGET_TIME 동안 표시).
- 기간: ALLY_TIME. 끝나기 EXTEND_PROMPT 전부터 두 나라가 모두 연장하면 다시 처음부터, 아니면 끝난다 (배신이 아니다).
- 파기: 기간 중에 깨면 배신자 (TRAITOR_TIME 동안 모두에게 보인다): 병사·건물이 TRAITOR_HURT배 피해를 받고,
  배신당한 나라의 관계는 -100 (적대), 다른 모든 나라도 -40. AI는 배신자의 동맹 요청을 거의 받지 않는다.
AI는 관계가 나쁜 (적대) 나라를 먼저 친다.
"""
from __future__ import annotations

import numpy as np

from sim import rules as R

ALLY_TIME = 480.0        # 동맹 기간 (초, 게임 시간)
EXTEND_PROMPT = 45.0     # 끝나기 이만큼 전부터 연장할 수 있다
REQUEST_TIME = 30.0      # 요청이 기다리는 시간
REJECT_COOLDOWN = 60.0   # 거절당한 뒤 다시 보낼 수 있기까지
TRAITOR_TIME = 120.0     # 배신자 표시가 남는 시간
TRAITOR_HURT = 1.3       # 배신자의 병사·건물이 받는 피해 배율
DONATE_CD = 10.0         # 자원 보내기, 병력 보내기 간격 (따로)
DONATE_MAX = 1.0         # 한 번에 보낼 수 있는 자원 비율 (가진 것의 100%까지)
TROOP_REACH = 4.0        # 동맹 거점 가장자리에서 이만큼 안에 닿으면 소속이 바뀐다
TROOP_TIME = 240.0       # 이 안에 닿지 못하면 (길이 막혔거나 다른 명령) 그만둔다
TARGET_TIME = 90.0       # 공격 요청 표시가 남는 시간
TARGET_CD = 20.0
REL_DECAY = 0.3          # 관계가 0 쪽으로 돌아오는 빠르기 (초당)
HIT_REL = 0.35           # 받은 피해 1마다 떨어지는 관계 (초당 최대 HIT_REL_MAX)
HIT_REL_MAX = 12.0
LEVELS = ('적대', '경계', '보통', '우호')


def level(v: float) -> int:
    return 0 if v < -50 else 1 if v < 0 else 2 if v < 50 else 3


class Diplomacy:
    def __init__(self, world):
        self.w = world
        n = self.n = len(world.nations)
        self.rel = np.zeros((n, n), np.float32)
        self.allies: dict[tuple[int, int], dict] = {}        # (작은 번호, 큰 번호) → {'until': 시각, 'ext': {연장한 나라}}
        self.requests: dict[tuple[int, int], float] = {}    # (보낸 나라, 받는 나라) → 보낸 시각
        self.cooldown: dict[tuple[int, int], float] = {}    # (보낸 나라, 받는 나라) → 다시 보낼 수 있는 시각
        self.traitor_until = np.zeros(n, np.float64)
        self.targets: dict[int, tuple[int, float]] = {}     # 요청한 나라 → (칠 나라, 끝나는 시각)
        self.target_cd = np.zeros(n, np.float64)
        self.donate_cd = np.zeros(n, np.float64)             # 자원 보내기
        self.troop_cd = np.zeros(n, np.float64)              # 병력 보내기
        self.marches: list[dict] = []                        # 동맹 거점으로 가는 병사들 {a, b, hall, ids, gens, until, retry}
        # 전투 커널에 넘기는 표 (나라 번호 0~255): 같은 편인가, 받는 피해 배율, 서로 입힌 피해 (1초마다 관계에 반영)
        self.friend = np.eye(256, dtype=np.uint8)
        self.hurt = np.ones(256, np.float32)
        self.hits = np.zeros((256, 256), np.float32)
        self._acc = 0.0
        self.version = 0                                     # 바뀔 때마다 (서버가 화면에 보낸다)

    # ------------------------------------------------------------- 묻기
    @staticmethod
    def key(a, b):
        return (a, b) if a < b else (b, a)

    def allied(self, a, b) -> bool:
        return a != b and self.key(a, b) in self.allies

    def foe(self, a, b) -> bool:
        """a가 b를 칠 수 있나 (자기 자신·동맹이 아니다)."""
        return not (a == b or (a < 256 and b < 256 and self.friend[a, b]))

    def allies_of(self, a) -> list[int]:
        return [y if x == a else x for (x, y) in self.allies if a in (x, y)]

    def traitor(self, a) -> bool:
        return self.traitor_until[a] > self.w.time

    def level(self, a, b) -> int:
        return level(float(self.rel[a, b]))

    def _alive(self, a) -> bool:
        return 0 <= a < self.n and self.w.nations[a].alive

    def _name(self, a) -> str:
        return self.w.nations[a].name

    def _say(self, text, *who):
        """who 나라들에게 (누가 읽을지는 조종자가 정한다)."""
        for a in who:
            self.w.say(text, to=a)

    def _bump(self):
        self.version += 1

    def _set_friend(self, a, b, on: bool):
        self.friend[a, b] = self.friend[b, a] = 1 if on else 0

    def _rel(self, a, b, d):
        self.rel[a, b] = float(np.clip(self.rel[a, b] + d, -100, 100))

    # ------------------------------------------------------------- 동맹
    def can_request(self, a, b) -> str | None:
        """a가 b에게 동맹을 청할 수 없으면 그 까닭."""
        if a == b or not (self._alive(a) and self._alive(b)):
            return '청할 수 없는 나라입니다'
        if self.allied(a, b):
            return '이미 동맹입니다'
        if (a, b) in self.requests:
            return '이미 동맹을 청했습니다'
        if self.cooldown.get((a, b), 0) > self.w.time:
            return f'거절당했습니다: {self.cooldown[(a, b)] - self.w.time:.0f}초 뒤에 다시 청할 수 있습니다'
        return None

    def request(self, a, b) -> bool:
        why = self.can_request(a, b)
        if why:
            self._say(why, a)
            return False
        if (b, a) in self.requests:                       # 상대도 청해 두었다: 바로 맺는다
            del self.requests[(b, a)]
            self._ally(a, b)
            return True
        self.requests[(a, b)] = self.w.time
        self._say(f'{self._name(b)}에게 동맹을 청했습니다', a)
        self._say(f'{R.josa(self._name(a), "이", "가")} 동맹을 청합니다', b)
        self._bump()
        return True

    def reply(self, b, a, accept: bool) -> bool:
        """b가 a의 요청에 답한다."""
        if (a, b) not in self.requests:
            return False
        del self.requests[(a, b)]
        if accept and self._alive(a) and self._alive(b) and not self.allied(a, b):
            self._ally(a, b)
        else:
            self.cooldown[(a, b)] = self.w.time + REJECT_COOLDOWN
            self._say(f'{R.josa(self._name(b), "이", "가")} 동맹을 거절했습니다', a)
            self._bump()
        return True

    def _ally(self, a, b):
        self.allies[self.key(a, b)] = {'until': self.w.time + ALLY_TIME, 'ext': set()}
        self.requests.pop((b, a), None)
        self._set_friend(a, b, True)
        self._rel(a, b, 60)
        self._rel(b, a, 60)
        for x, y in ((a, b), (b, a)):                      # 서로를 노리던 병사·공격 요청은 그만
            if x in self.targets and self.targets[x][0] == y:
                del self.targets[x]
        self.w.calm_between(a, b)
        na, nb = self._name(a), self._name(b)
        self._say(f'{R.josa(nb, "과", "와")} 동맹을 맺었습니다 ({ALLY_TIME / 60:.0f}분)', a)
        self._say(f'{R.josa(na, "과", "와")} 동맹을 맺었습니다 ({ALLY_TIME / 60:.0f}분)', b)
        self.w.say(f'{R.josa(na, "과", "와")} {R.josa(nb, "이", "가")} 동맹을 맺었습니다', skip=(a, b))
        self._bump()

    def extend(self, a, b) -> bool:
        al = self.allies.get(self.key(a, b))
        if al is None or al['until'] - self.w.time > EXTEND_PROMPT:
            return False
        al['ext'].add(a)
        if b in al['ext']:
            al['until'] = self.w.time + ALLY_TIME
            al['ext'] = set()
            self._say(f'{R.josa(self._name(b), "과", "와")} 동맹을 연장했습니다', a)
            self._say(f'{R.josa(self._name(a), "과", "와")} 동맹을 연장했습니다', b)
        self._bump()
        return True

    def end(self, a, b, betray: bool):
        """동맹을 끝낸다 (betray: a가 기간 중에 깼다 → 배신자)."""
        k = self.key(a, b)
        if k not in self.allies:
            return False
        del self.allies[k]
        self._set_friend(a, b, False)
        if betray:
            self.traitor_until[a] = self.w.time + TRAITOR_TIME
            self.hurt[a] = TRAITOR_HURT
            self.rel[b, a] = -100.0
            for c in range(self.n):
                if c not in (a, b):
                    self._rel(c, a, -40)
            na, nb = self._name(a), self._name(b)
            self._say(f'{R.josa(nb, "과", "와")}의 동맹을 깼습니다: {TRAITOR_TIME / 60:.0f}분 동안 배신자 (받는 피해 {TRAITOR_HURT:.1f}배, 모든 나라의 관계 하락)', a)
            self._say(f'{R.josa(na, "이", "가")} 우리와의 동맹을 깼습니다! (배신)', b)
            self.w.say(f'{R.josa(na, "이", "가")} {R.josa(nb, "과", "와")}의 동맹을 깼습니다! (배신자)', skip=(a, b))
        else:
            self._say(f'{R.josa(self._name(b), "과", "와")}의 동맹 기간이 끝났습니다', a)
            self._say(f'{R.josa(self._name(a), "과", "와")}의 동맹 기간이 끝났습니다', b)
        self._bump()
        return True

    # ------------------------------------------------------------- 동맹끼리
    def give_res(self, a, b, pcts) -> bool:
        """a가 b에게 자원마다 가진 것의 pcts[k] (0~DONATE_MAX)만큼 보낸다 (식량, 목재, 석재, 유황)."""
        if not self.allied(a, b) or self.donate_cd[a] > self.w.time:
            self._say('잠시 뒤에 다시 보낼 수 있습니다' if self.allied(a, b) else '동맹에게만 보낼 수 있습니다', a)
            return False
        na, nb = self.w.nations[a], self.w.nations[b]
        pcts = (list(pcts) + [0, 0, 0, 0])[:4]
        have = [na.res[0], na.res[1], na.res[2], na.sulfur]
        sent = [float(np.floor(have[k] * min(max(float(p), 0.0), DONATE_MAX))) for k, p in enumerate(pcts)]
        if sum(sent) <= 0:
            self._say('보낼 자원이 없습니다', a)
            return False
        for k in range(3):
            na.res[k] -= sent[k]
            nb.res[k] += sent[k]
        na.sulfur -= sent[3]
        nb.sulfur += sent[3]
        self.donate_cd[a] = self.w.time + DONATE_CD
        self._rel(b, a, min((sum(sent[:3]) + sent[3] * 4) / 10.0, 40.0))          # 유황은 귀하다
        txt = ', '.join(f'{(*R.RES_NAMES, "유황")[k]} {v:.0f}' for k, v in enumerate(sent) if v > 0)
        self._say(f'{self._name(b)}에게 보냈습니다: {txt}', a)
        self._say(f'{R.josa(self._name(a), "이", "가")} 자원을 보냈습니다: {txt}', b)
        self._bump()
        return True

    def give_units(self, a, b, ids) -> int:
        """a가 고른 병사들을 b의 가장 가까운 거점으로 보낸다 (닿으면 b의 병사가 된다: _marches).
        바다 건너인데 병사들이 있는 땅에 a의 항구가 없으면 보내지 않는다. 반환: 보낸 병사 수."""
        w, u, bb = self.w, self.w.units, self.w.builds
        if not self.allied(a, b) or self.troop_cd[a] > w.time:
            self._say('잠시 뒤에 다시 보낼 수 있습니다' if self.allied(a, b) else '동맹에게만 보낼 수 있습니다', a)
            return 0
        ids = np.asarray(ids, np.int64)
        ids = ids[u.alive[ids] & (u.own[ids] == a) & ~u.aboard[ids]] if len(ids) else ids
        if not len(ids):
            self._say('보낼 병사를 먼저 고르세요', a)
            return 0
        halls = w.building_ids(b, R.HALL, done=True)
        if not len(halls):
            self._say(f'{R.josa(self._name(b), "은", "는")} 병사를 받을 거점이 없습니다', a)
            return 0
        comp = w.map.comp
        cy, cx = float(u.y[ids].mean()), float(u.x[ids].mean())
        src = int(comp[int(u.y[ids[0]]), int(u.x[ids[0]])])
        same = [h for h in halls if comp[int(bb.y[h]), int(bb.x[h])] == src]
        if same:                                          # 같은 땅이면 걸어서 가장 가까운 거점으로
            h = min(same, key=lambda h: np.hypot(bb.y[h] - cy, bb.x[h] - cx))
        elif w.fleet.harbors_on(a, src):                  # 바다 건너: 이 땅에 내 항구가 있으면 배로
            h = min(halls, key=lambda h: np.hypot(bb.y[h] - cy, bb.x[h] - cx))
        else:
            self._say(f'{R.josa(self._name(b), "은", "는")} 바다 건너라, 병사들이 있는 땅에 항구가 있어야 보낼 수 있습니다', a)
            return 0
        h = int(h)
        w.wild.release(ids)
        w.order_move(ids, float(bb.y[h]), float(bb.x[h]))
        self.marches.append({'a': a, 'b': b, 'hall': h, 'ids': ids.copy(), 'gens': u.gen[ids].copy(),
                             'until': w.time + TROOP_TIME, 'retry': 2})
        self.troop_cd[a] = w.time + DONATE_CD
        self._say(f'병사 {len(ids)}명이 {self._name(b)}의 거점으로 갑니다 (닿으면 동맹의 병사가 됩니다)', a)
        self._bump()
        return len(ids)

    def _marches(self):
        """동맹 거점으로 가는 병사들: 닿은 병사는 소속이 바뀐다. 다른 명령을 받았거나 죽은 병사는 빠지고,
        길이 막혀 멈춘 병사는 두 번까지 다시 보낸다. 동맹이 끝났거나 거점이 무너졌거나 너무 오래 걸리면 그만둔다."""
        w, u, bb = self.w, self.w.units, self.w.builds
        from sim.entities import IDLE, MOVE
        keep = []
        for m in self.marches:
            a, b, h = m['a'], m['b'], m['hall']
            ids, gens = m['ids'], m['gens']
            ok = u.alive[ids] & (u.gen[ids] == gens) & (u.own[ids] == a)
            ids, gens = ids[ok], gens[ok]
            if not len(ids) or not self.allied(a, b) or not bb.alive[h] or bb.own[h] != b or w.time > m['until']:
                if len(ids):
                    self._say(f'{self._name(b)}에게 가던 병사 {len(ids)}명이 돌아섰습니다', a)
                continue
            on_way = (u.state[ids] == MOVE) | (u.state[ids] == IDLE) | u.aboard[ids]   # 다른 명령을 받은 병사는 빠진다
            ids, gens = ids[on_way], gens[on_way]
            d = np.hypot(u.x[ids] - bb.x[h], u.y[ids] - bb.y[h]) - bb.r[h]
            there = (d <= TROOP_REACH) & ~u.aboard[ids]
            if there.any():
                got = ids[there]
                u.own[got] = b
                u.state[got] = IDLE
                u.tgt[got] = u.tgb[got] = u.bld[got] = u.slot[got] = -1
                self._rel(b, a, min(4.0 * len(got), 50.0))
                self._say(f'병사 {len(got)}명이 {self._name(b)}에 합류했습니다', a)
                self._say(f'{R.josa(self._name(a), "이", "가")} 보낸 병사 {len(got)}명이 합류했습니다', b)
                self._bump()
                ids, gens = ids[~there], gens[~there]
            stuck = ids[(u.state[ids] == IDLE) & ~u.aboard[ids]]
            if len(stuck) and m['retry'] > 0:                 # 길 끝에서 멈췄다: 다시
                m['retry'] -= 1
                w.order_move(stuck, float(bb.y[h]), float(bb.x[h]))
            if len(ids):
                m['ids'], m['gens'] = ids, gens
                keep.append(m)
        self.marches = keep

    def target(self, a, t) -> bool:
        """a가 동맹들에게 t를 치자고 한다."""
        w = self.w
        if not self.allies_of(a) or t == a or not self._alive(t) or self.allied(a, t):
            self._say('동맹이 있어야, 동맹이 아닌 나라만 공격을 요청할 수 있습니다', a)
            return False
        if self.target_cd[a] > w.time:
            self._say(f'{self.target_cd[a] - w.time:.0f}초 뒤에 다시 요청할 수 있습니다', a)
            return False
        self.targets[a] = (t, w.time + TARGET_TIME)
        self.target_cd[a] = w.time + TARGET_CD
        self._rel(t, a, -40)
        nt, na = self._name(t), self._name(a)
        self._say(f'동맹들에게 {R.josa(nt, "을", "를")} 함께 치자고 했습니다', a)
        self._say(f'동맹 {R.josa(na, "이", "가")} {R.josa(nt, "을", "를")} 함께 치자고 합니다', *self.allies_of(a))
        self._bump()
        return True

    # ------------------------------------------------------------- 진행
    def update(self, dt: float) -> None:
        w, now = self.w, self.w.time
        self._acc += dt
        if self._acc < 1.0:
            return
        step, self._acc = self._acc, 0.0
        n = self.n
        # 받은 피해 → 관계 (맞은 나라가 친 나라를 미워한다)
        h = self.hits[:n, :n]
        if h.any():
            drop = np.minimum(h * HIT_REL, HIT_REL_MAX)
            self.rel[:n, :n] = np.clip(self.rel[:n, :n] - drop.T, -100, 100)   # rel[b, a] -= hits[a, b]
            self.hits[:n, :n] = 0
        # 0 쪽으로 천천히
        r = self.rel
        r[:] = np.where(np.abs(r) <= REL_DECAY * step, 0, r - np.sign(r) * REL_DECAY * step)
        changed = False
        if self.marches:
            self._marches()
        for k, t0 in list(self.requests.items()):        # 답이 없는 요청은 사라진다
            if now - t0 > REQUEST_TIME or not (self._alive(k[0]) and self._alive(k[1])):
                del self.requests[k]
                changed = True
        for (a, b), al in list(self.allies.items()):     # 기간이 끝났거나 한쪽이 망했다
            if now >= al['until'] or not (self._alive(a) and self._alive(b)):
                self.end(a, b, betray=False)
        for a in range(n):                                # 배신자 표시가 끝났다
            if self.hurt[a] != 1.0 and self.traitor_until[a] <= now:
                self.hurt[a] = 1.0
                changed = True
        for a, (t, until) in list(self.targets.items()):
            if until <= now or not self._alive(t):
                del self.targets[a]
                changed = True
        if changed:
            self._bump()

    def state_for(self, me: int) -> dict:
        """화면에 보낼 것 (me 나라의 눈으로)."""
        now = self.w.time
        return {
            'allies': {str(b): round(self.allies[self.key(me, b)]['until'] - now) for b in self.allies_of(me)},
            'extend': [b for b in self.allies_of(me)
                       if self.allies[self.key(me, b)]['until'] - now <= EXTEND_PROMPT and me not in self.allies[self.key(me, b)]['ext']],
            'incoming': [a for (a, b) in self.requests if b == me],
            'outgoing': [b for (a, b) in self.requests if a == me],
            'cooldown': {str(b): round(t - now) for (a, b), t in self.cooldown.items() if a == me and t > now},
            'pairs': [[a, b] for (a, b) in self.allies],
            'traitors': {str(a): round(self.traitor_until[a] - now) for a in range(self.n) if self.traitor_until[a] > now},
            'theirs': [self.level(b, me) if b != me else 3 for b in range(self.n)],     # 그 나라가 나를 보는 눈
            'mine': [self.level(me, b) if b != me else 3 for b in range(self.n)],       # 내가 그 나라를 보는 눈
            'targets': [[a, t, round(until - now)] for a, (t, until) in self.targets.items() if a == me or self.allied(a, me)],
            'donate_cd': max(0, round(self.donate_cd[me] - now)),
            'troop_cd': max(0, round(self.troop_cd[me] - now)),
            'donate_max': DONATE_MAX,
            'ally_time': ALLY_TIME, 'extend_prompt': EXTEND_PROMPT, 'traitor_time': TRAITOR_TIME,
        }
