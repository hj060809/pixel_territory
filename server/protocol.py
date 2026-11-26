"""서버 → 브라우저 상태 메시지 (이진, little-endian). 바뀐 것만 보낸다.

브라우저 → 서버 명령은 JSON (초당 몇 번뿐이라 작다): session.py 참고.

상태 메시지 (걸음마다 하나):
    u8  종류 = 1
    u32 걸음 번호
    f32 게임 시각(초), f32 하루 시각(0~24), f32 1년 위치(0~1)
    u8  상태 비트 (1 일시정지, 2 끝남, 4 승리), u8 속도×10, u16 서버 계산 시간(0.01 ms 단위)
    (공격 종류: 0 칼 1 화살·망루 2 포탄 3 서리 숨결 4 발 구르기 5 포효 (x0,y0 = 바위거북 자리) 6 화염탑 불 7 약한 불)
    -- 병사 (바뀐 것만) --
    u16 n, 그다음 n개: u16 칸, u16 세대, u16 x×64, u16 y×64, u8 나라, u8 종류, u8 체력(0~255, 최대 체력 비율),
                      u8 상태(IDLE MOVE AMOVE ATTACK BUILD TAME), u8 비트(1 걷는 중, 2 배에 탐, 4 날고 있음)   = 14바이트
                      (야생 나라 rules.NEUTRAL 이상의 병사는 보내지 않는다: 동물 칸으로 간다)
    u16 m, 그다음 m개: u16 칸 (사라진 병사)
    -- 건물 (바뀐 것만) --
    u16 n, 그다음 n개: u16 칸, u16 세대, u16 x×2, u16 y×2, u8 종류, u8 나라, u8 체력(0~255), u8 지은 정도(0~255),
                      u8 대기열 길이, u8 맨 앞 종류(0 보병 1 궁수 2 전함 255 없음), u16 맨 앞 남은 시간×10, i16 자원지,
                      u16 대기열 앞 5개 (3비트씩)                                                = 22바이트
    u16 m, 그다음 m개: u16 칸 (사라진 건물)
    -- 배 (전부, 수가 적다) --
    u16 n, 그다음 n개: u32 번호, u8 종류(0 나룻배 1 전함), u8 나라, u16 x×64, u16 y×64, u8 체력(0~255), i8 방향,
                      u8 상태, u8 탄 병사 수, u8 비트(1 출발 전이라 숨김)                          = 17바이트
    -- 공격 (이번 걸음에 새로 난 것) --
    u16 n, 그다음 n개: u16 x0×64, u16 y0×64, u16 x1×64, u16 y1×64, u8 종류(0 칼 1 화살·망루 2 포탄) = 9바이트
    -- 야생 동물 (바뀐 것만) --
    u16 n, 그다음 n개: u32 번호, u8 종류(rules.WILDLIFE), u16 x×64, u16 y×64,
                      u8 상태(0 풀 뜯기 1 거닒 2 달아남 3 기다림 4 길드는 중 5 잠 6 싸움 7 쓰러짐),
                      u8 길든 정도(0~255), i8 방향, u8 체력(0~255), u8 쓰러져 있는 남은 초         = 14바이트
    u16 m, 그다음 m개: u32 번호 (사라진 동물: 길들었거나 물에 빠짐)
    -- 나라 (몇 걸음마다) --
    u8 있음(0/1), 있으면 u8 n, 그다음 n개: f32 자원×3, f32 증감×3, f32 유황, f32 유황 증감, u16 병사 수, u16 건물 수, u8 살아 있음, u8 굶주림 = 38바이트
"""
from __future__ import annotations

import struct

import numpy as np

from sim import rules as R

MSG_STATE = 1
POS = 64.0                         # 위치 단위 (1/64칸)
BOAT_STATES = {'idle': 0, 'move': 1, 'hunt': 2, 'pickup': 3, 'wait': 4, 'cross': 5, 'return': 6,
               'load': 7, 'ahead': 8, 'anchor': 9}     # 나룻배: 항구에서 태우는 중 / 앞바다로 / 기다림
_U_HP = np.array([R.UNIT_STATS[k]['hp'] for k in range(len(R.UNIT_STATS))], np.float32)
_QUEUE_KIND = {R.INFANTRY: 0, R.ARCHER: 1, R.WARSHIP: 2}    # 대기열 병종 번호


def _q(v, scale=POS):
    return np.clip(np.rint(np.asarray(v, np.float64) * scale), 0, 65535).astype('<u2')


class StateEncoder:
    """세계의 지금 상태를 직전에 보낸 것과 비교해 바뀐 것만 이진으로 만든다. 브라우저 하나에 하나."""

    UNIT_DT = np.dtype([('slot', '<u2'), ('gen', '<u2'), ('x', '<u2'), ('y', '<u2'), ('own', 'u1'), ('kind', 'u1'),
                        ('hp', 'u1'), ('state', 'u1'), ('bits', 'u1')])
    BUILD_DT = np.dtype([('slot', '<u2'), ('gen', '<u2'), ('x', '<u2'), ('y', '<u2'), ('kind', 'u1'), ('own', 'u1'),
                         ('hp', 'u1'), ('prog', 'u1'), ('qlen', 'u1'), ('qkind', 'u1'), ('qtime', '<u2'), ('site', '<i2'),
                         ('qbits', '<u2')])   # qbits: 대기열 앞 5개를 3비트씩 (0 없음, 대기열 병종 번호+1)
    BOAT_DT = np.dtype([('id', '<u4'), ('kind', 'u1'), ('own', 'u1'), ('x', '<u2'), ('y', '<u2'), ('hp', 'u1'),
                        ('dir', 'i1'), ('state', 'u1'), ('cargo', 'u1'), ('bits', 'u1')])
    SHOT_DT = np.dtype([('x0', '<u2'), ('y0', '<u2'), ('x1', '<u2'), ('y1', '<u2'), ('kind', 'u1')])
    ANIMAL_DT = np.dtype([('id', '<u4'), ('kind', 'u1'), ('x', '<u2'), ('y', '<u2'), ('state', 'u1'), ('prog', 'u1'),
                          ('dir', 'i1'), ('hp', 'u1'), ('sub', 'u1')])
    PEN = struct.Struct('<HHBBffBBB')             # 목장 하나의 머리 (sim/pasture.py Pen)
    NATION = struct.Struct('<12f2HBB')         # 자원 3, 수입 3, 유황, 유황 수입, 자원마다 한도 4 (sim/storage.py), 병사 수, 건물 수, 살아 있음, 굶주림

    def __init__(self, world):
        self.w = world
        self.prev_units = np.zeros(0, self.UNIT_DT)
        self.prev_builds = np.zeros(0, self.BUILD_DT)
        self.prev_animals: dict = {}
        self.shot_time = -1.0
        self.tick = 0
        self.pen_v = -1                                    # 보낸 목장 판 (sim/pasture.py Pastures.version)

    def reset(self, world=None):
        """처음부터 다시 (새 판, 다시 접속): 다음 메시지는 모든 병사/건물을 담는다."""
        if world is not None:
            self.w = world
        self.prev_units = np.zeros(0, self.UNIT_DT)
        self.prev_builds = np.zeros(0, self.BUILD_DT)
        self.prev_animals = {}
        self.shot_time = -1.0
        self.pen_v = -1

    # ------------------------------------------------------------- 지금 상태 → 배열
    def _units(self):
        u = self.w.units
        n = u.n
        a = np.zeros(n, self.UNIT_DT)
        a['slot'] = np.arange(n)
        a['gen'] = u.gen[:n]
        a['x'], a['y'] = _q(u.x[:n]), _q(u.y[:n])
        a['own'], a['kind'] = u.own[:n], u.kind[:n]
        a['hp'] = np.clip(np.rint(u.hp[:n] / _U_HP[u.kind[:n]] * 255), 0, 255)
        a['state'] = u.state[:n]
        a['bits'] = u.moving[:n].astype(np.uint8) | (u.aboard[:n].astype(np.uint8) << 1) | (u.air[:n].astype(np.uint8) << 2)
        return a, u.alive[:n] & (u.own[:n] < R.NEUTRAL)       # 야생 동물(드래곤)은 동물 칸으로 간다

    def _builds(self):
        b = self.w.builds
        n = b.n
        a = np.zeros(n, self.BUILD_DT)
        a['slot'] = np.arange(n)
        a['gen'] = b.gen[:n]
        a['x'], a['y'] = _q(b.x[:n], 2), _q(b.y[:n], 2)
        a['kind'], a['own'] = b.kind[:n], b.own[:n]
        a['hp'] = np.clip(np.rint(b.hp[:n] / np.maximum(b.maxhp[:n], 1) * 255), 0, 255)
        a['prog'] = np.clip(np.rint(b.prog[:n] * 255), 0, 255)
        a['site'] = b.site[:n]
        a['qkind'] = 255
        for i in np.flatnonzero(b.alive[:n]):
            q = b.queue[i]
            if q:
                a['qlen'][i] = min(len(q), 255)
                a['qkind'][i] = _QUEUE_KIND.get(q[0][0], 255)
                a['qtime'][i] = min(int(round(q[0][1] * 10)), 65535)
                a['qbits'][i] = sum((_QUEUE_KIND.get(item[0], 0) + 1) << (3 * k) for k, item in enumerate(q[:5]))
        return a, b.alive[:n].copy()

    @staticmethod
    def _diff(cur, alive, prev):
        """바뀐(또는 새로 생긴) 것과 사라진 칸."""
        n = len(cur)
        prev_full = np.zeros(n, cur.dtype)
        m = min(n, len(prev))
        prev_full[:m] = prev[:m]
        was = np.zeros(n, bool)
        was[:m] = prev[:m]['gen'] > 0                     # 직전에 보낸 적 있는(살아 있던) 칸
        changed = alive & (~was | (cur != prev_full))
        gone = was & ~alive
        kept = cur.copy()
        kept[~alive] = np.zeros(1, cur.dtype)             # 사라진 칸은 비운다 (세대 0 = 보낸 적 없음)
        return changed, gone, kept

    # ------------------------------------------------------------- 메시지
    def encode(self, header: dict, nations: bool, sim_ms: float) -> bytes:
        w = self.w
        self.tick += 1
        parts = [struct.pack('<BIfffBBH', MSG_STATE, self.tick, w.time, header['hour'], header['year'],
                             header['flags'], int(round(header['speed'] * 10)), min(int(sim_ms * 100), 65535))]
        for cur_fn, attr in ((self._units, 'prev_units'), (self._builds, 'prev_builds')):
            cur, alive = cur_fn()
            changed, gone, kept = self._diff(cur, alive, getattr(self, attr))
            ch = cur[changed]
            parts.append(struct.pack('<H', len(ch)) + ch.tobytes())
            gs = np.flatnonzero(gone).astype('<u2')
            parts.append(struct.pack('<H', len(gs)) + gs.tobytes())
            setattr(self, attr, kept)
        # 배
        boats = [b for b in w.fleet.boats if b.alive]
        a = np.zeros(len(boats), self.BOAT_DT)
        for i, b in enumerate(boats):
            a[i] = (b.id, 1 if b.kind == 'warship' else 0, b.own, _q(b.x), _q(b.y),
                    int(np.clip(round(b.hp / b.maxhp * 255), 0, 255)), int(np.sign(b.dir) or 1),
                    BOAT_STATES.get(b.state, 0), min(len(b.cargo) or len(b.assigned), 255), int(b.pos < 0))
        parts.append(struct.pack('<H', len(a)) + a.tobytes())
        # 공격: 이번 걸음 동안 새로 난 것
        new = [r for r in w.recent if r[0] > self.shot_time]
        if w.recent:
            self.shot_time = max(self.shot_time, w.recent[-1][0])
        s = np.zeros(len(new), self.SHOT_DT)
        for i, (_, x0, y0, x1, y1, kind) in enumerate(new):
            s[i] = (_q(x0), _q(y0), _q(x1), _q(y1), int(kind))
        parts.append(struct.pack('<H', len(s)) + s.tobytes())
        # 야생 동물: 바뀐 것과 사라진 것
        cur = {}
        for an in w.wild.animals.values():
            cur[an.id] = (an.id, an.kind, int(_q(an.x)), int(_q(an.y)), an.mode, int(min(an.prog, 1.0) * 255), an.dir,
                          int(np.clip(round(an.hp * 255), 0, 255)), int(np.clip(np.ceil(an.sub), 0, 255)))
        ch = [r for k, r in cur.items() if self.prev_animals.get(k) != r]
        gone = np.array([k for k in self.prev_animals if k not in cur], '<u4')
        a = np.array(ch, self.ANIMAL_DT) if ch else np.zeros(0, self.ANIMAL_DT)
        parts.append(struct.pack('<H', len(a)) + a.tobytes() + struct.pack('<H', len(gone)) + gone.tobytes())
        self.prev_animals = cur
        # 나라
        if nations:
            body = b''.join(self.NATION.pack(*n.res, *n.rate, n.sulfur, n.sulfur_rate, *n.caps, min(n.n_units, 65535), min(n.n_buildings, 65535),
                                             int(n.alive), int(n.starving)) for n in w.nations)
            parts.append(struct.pack('<BB', 1, len(w.nations)) + body)
        else:
            parts.append(b'\0')
        # 목장: 바뀌었을 때만 모두 (헛간 번호·세대, 나라, 동물, 가운데, 다 지었나, 든 수, 울타리 방향마다 반지름 ×4, 든 동물 자리 ×4)
        pens = getattr(w, 'pastures', None)
        if pens is not None and pens.version != self.pen_v:
            self.pen_v = pens.version
            out = [struct.pack('<BB', 1, len(pens.pens))]
            for p in pens.pens.values():
                n = min(p.n, len(p.spots), 255)
                out.append(self.PEN.pack(p.b, p.gen & 0xFFFF, p.own, p.kind, p.cx, p.cy, int(p.done), n, len(p.radii)))
                out.append(bytes(int(np.clip(round(r * 4), 0, 255)) for r in p.radii))
                out.append(np.array([[np.clip(round(dx * 4), -127, 127), np.clip(round(dy * 4), -127, 127)] for dx, dy in p.spots[:n]],
                                    np.int8).reshape(-1).tobytes())
            parts.append(b''.join(out))
        else:
            parts.append(b'\0')
        return b''.join(parts)


def decode(blob: bytes) -> dict:
    """상태 메시지 풀기 (시험용 파이썬 클라이언트와 테스트가 쓴다. 웹은 같은 형식을 TypeScript로 읽는다)."""
    head = struct.Struct('<BIfffBBH')
    kind, tick, t, hour, year, flags, speed, sim = head.unpack_from(blob, 0)
    off = head.size
    out = {'tick': tick, 'time': t, 'hour': hour, 'year': year, 'flags': flags, 'speed': speed / 10, 'sim_ms': sim / 100}

    def arr(dt):
        nonlocal off
        n = struct.unpack_from('<H', blob, off)[0]
        off += 2
        a = np.frombuffer(blob, dt, n, off)
        off += n * dt.itemsize
        return a

    out['units'] = arr(StateEncoder.UNIT_DT)
    out['units_gone'] = arr(np.dtype('<u2'))
    out['builds'] = arr(StateEncoder.BUILD_DT)
    out['builds_gone'] = arr(np.dtype('<u2'))
    out['boats'] = arr(StateEncoder.BOAT_DT)
    out['shots'] = arr(StateEncoder.SHOT_DT)
    out['animals'] = arr(StateEncoder.ANIMAL_DT)
    out['animals_gone'] = arr(np.dtype('<u4'))
    has = blob[off]
    off += 1
    if has:
        n = blob[off]
        off += 1
        out['nations'] = [StateEncoder.NATION.unpack_from(blob, off + i * StateEncoder.NATION.size) for i in range(n)]
        off += n * StateEncoder.NATION.size
    has = blob[off] if off < len(blob) else 0
    off += 1
    if has:
        cnt = blob[off]
        off += 1
        pens = []
        for _ in range(cnt):
            b, gen, own, kind, cx, cy, done, n, nd = StateEncoder.PEN.unpack_from(blob, off)
            off += StateEncoder.PEN.size
            radii = [v / 4 for v in blob[off:off + nd]]
            off += nd
            sp = np.frombuffer(blob, np.int8, n * 2, off).reshape(-1, 2) / 4
            off += n * 2
            pens.append({'b': b, 'gen': gen, 'own': own, 'kind': kind, 'cx': cx, 'cy': cy, 'done': bool(done), 'n': n,
                         'radii': radii, 'spots': sp.tolist()})
        out['pens'] = pens
    return out
