"""야생 동물과 길들이기.

동물 하나 = rules.WILDLIFE 표 한 줄 (지금은 말. 사막 동물 등은 같은 틀에 한 줄 더하면 된다):
- 사는 곳: 표의 habitat (말 = 넓고 평평한 초원, HABITATS가 지형에서 고른다). 작은 무리(group)로 넓게 흩어져 살고,
  수가 줄면 regrow초마다 새 무리가 생긴다 (겨울엔 거의 안 생긴다). 지도의 최대 수 = 사는 땅 넓이 / per_area (cap까지).
- 동물은 풀을 뜯거나 천천히 거닐다가, 병사가 가까이 오거나 싸움이 나면 달아난다.
- 길들이기: 병사를 고르고 동물을 오른쪽 클릭하면 (order_tame) 그 둘레 무리의 동물마다 가까운 병사 하나씩 간다.
  병사가 다가가는 동안 동물은 얌전히 기다리고, 닿으면 tame초 동안 길들인다 (병사 상태 TAME).
  다른 명령을 받거나, 맞거나, 죽으면 끊긴다 (동물은 놀라 달아나고, 진행은 처음부터).
- 다 길들이면 병사와 동물이 합쳐져 표의 mounts 병종이 된다 (보병 → 창기병, 궁수 → 기마궁수, 척탄병 → 척탄기마병). 체력 비율은 그대로.
  기병이 죽으면 말도 함께 죽는다 (돌아오지 않는다).

사나운 동물 (표의 hostile, 지금은 드래곤):
- 큰 설원 덩어리마다 가장 높은 곳에 둥지 (lairs_for, 지도에 최대 cap개, 지도만으로 정해져 맵 생성 화면에도 보인다).
  둥지마다 하나가 산다. 실제로는 야생 나라(rules.NEUTRAL)의 병사 하나 (표의 unit 병종)로 싸운다.
- 평소엔 잔다 (병사들이 저절로 덤비지 않는다). 둥지 가까이(wake) 오거나 맞으면 깨어 둥지 둘레(guard)의 병사를 친다
  (서리 숨결, 범위 피해). 깨어 있는 동안은 모두가 서로 싸운다 (나라 번호 WILD). 둘레에 아무도 없으면 둥지로 돌아가 잔다.
- 체력이 subdue 비율 아래로 떨어지면 쓰러진다 (subdue_time초, 그동안 맞지 않고 몸부림쳐 둘레 병사에게 작은 피해.
  길들이는 병사는 다치지 않는다).
  그동안 병사 하나가 길들이면 (tame초) 표의 mounts 병종 (용기사)이 된다. 나라마다 limit기까지.
  시간 안에 못 하면 체력 절반으로 일어나 다시 싸운다. 그래서 죽일 수는 없고 길들일 수만 있다.
- 길들여지면 regrow초 뒤 그 둥지에 새로 난다.

화면: 동물은 상태 메시지의 동물 칸에 실린다 (server/protocol.py, 바뀐 것만).
"""
from __future__ import annotations

import numpy as np
from scipy import ndimage

from sim import rules as R
from sim import climate
from sim.entities import IDLE, MOVE, TAME

GRAZE, WALK, FLEE, HELD, TAMING, SLEEP, FIGHT, SUBDUED = range(8)    # 동물 상태 (화면에 그대로 간다)
NOVA, FLY, AIR_NOVA = 8, 9, 10   # 드래곤: 눈보라를 모은다 (prog = 모은 정도), 날고 있다, 날며 (공중에 멈춰) 눈보라를 모은다
FLEE_P, TURN_P, STRIKE_P, HOLD_P = 0, 1, 2, 3   # 날기 단계: 사거리 밖으로 빠진다, 돌아본다, 날아가 숨결, 그 자리에서 공격을 마친다
RAID, HOMEWARD = 11, 12           # 드래곤 겨울 습격: 설원의 병사·건물을 치며 날아다닌다, 둥지로 날아 돌아간다 (둘 다 길들일 수 없다)
NOVA_SHOT, AIM_SHOT, THROW_SHOT, BLAST_SHOT = 10, 12, 13, 14   # 공격 기록 kind: 맞은 병사 자리 얼음 폭발, 겨눈 곳 (x1, y1), 던짐 (x0, y0 → x1, y1), 떨어진 곳 큰 폭발
WILD = R.NEUTRAL + 1  # 깨어 싸우는 야생 동물의 나라 번호 (병사·망루가 저절로 덤빈다)
STRUGGLE = (3.0, 4.0, 4.5)     # 쓰러진 사나운 동물의 몸부림: 간격(초), 피해, 반지름
DRAGON_REACH = 3.4    # 큰 동물은 이만큼에서 길들인다
LAIR_CLEAR = 32       # 둥지에서 이만큼 안에서는 나라가 시작하지 않는다 (칸)
LAIR_FIELD = 10000    # 둥지가 생기는 설원 덩어리의 최소 넓이 (512×512 지도 기준 칸)

FEAR = 4.5            # 길들이러 오지 않는 병사가 이만큼 가까이 오면 달아난다 (칸)
SHOT_FEAR = 9.0       # 싸움(칼부림, 화살)이 이만큼 가까이서 나면 달아난다
ROAM = 9.0            # 무리 자리에서 이만큼 안을 거닌다
WALK_SPEED, RUN_SPEED = 0.9, 5.5
PEN_WALK = 1.6       # 목장 몫인 동물이 울타리 안으로 걸어 들어가는 빠르기
REACH = 1.7           # 병사가 이만큼 가까이 오면 길들이기 시작
TAKEOVER = 7.0        # 길을 따라오던 병사가 이만큼 가까이 오면 곧장 동물에게 다가간다
STUCK = 4.0           # 곧장 다가가다 이만큼(초) 못 닿으면 그만둔다
SPAWN_CLEAR_B, SPAWN_CLEAR_U = 16.0, 12.0     # 새 무리는 건물·병사에서 이만큼 떨어진 곳에


def _grass(gmap):
    """넓은 풀밭 (풀밭·관목·추운 초원, 조금 기울어도: 둘레 15칸의 45% 넘게 그런 칸)."""
    from engine.render import materials as S
    from sim.sites import GRASSY
    flat = np.isin(gmap.layers['pre'], (*GRASSY, S.SHRUB, S.COLD_STEPPE)) & (gmap.base_cost <= 1.35) & gmap.walk
    if flat.sum() < 200:
        return np.zeros_like(flat)
    return flat & (ndimage.uniform_filter(flat.astype(np.float32), 15) > 0.45)


def _desert(gmap):
    """넓은 사막·모래 언덕 (둘레 15칸의 60% 넘게 사막인 칸)."""
    from engine.render import materials as S
    d = np.isin(gmap.layers['pre'], (S.DESERT, S.DUNE)) & gmap.walk_static
    if d.sum() < 300:
        return np.zeros_like(d)
    return d & (ndimage.uniform_filter(d.astype(np.float32), 15) > 0.6)


def _snowfield(gmap):
    """넓고 낮은 설원·툰드라 (눈·얼음 땅·툰드라·이끼, 높은 산은 빼고: 둘레 15칸의 50% 넘게 그런 칸). 순록이 산다."""
    from engine.render import materials as S
    low = 1.0 + np.clip(gmap.layers['alt'] - 0.35, 0, 1) * 0.8 <= 1.15        # 높을수록 비싸지는 배율 (sim/terrain.py)이 작은 곳
    s = np.isin(gmap.layers['pre'], (S.SNOW, S.SNOW_OLD, S.ICE, S.TUNDRA, S.MOSS)) & gmap.land & gmap.walk_static & low
    if s.sum() < 300:
        return np.zeros_like(s)
    return s & (ndimage.uniform_filter(s.astype(np.float32), 15) > 0.5)


HABITATS = {'grass': _grass, 'desert': _desert, 'snow': _snowfield}    # 사는 땅 이름 → 지도에서 그 땅 고르기


def lairs_for(gmap, cap: int = 3) -> list[tuple[int, int]]:
    """사나운 동물(드래곤)의 둥지: 봄·가을(맵 생성 화면 미리보기와 같은 계절)에도 눈이 덮여 있는 큰 설원 덩어리마다 하나.
    덩어리는 하나로 이어진 눈 덮인 땅이 LAIR_FIELD칸 (512×512 지도 기준, 지도 넓이에 비례) 넘어야 한다.
    자리는 그 덩어리 안쪽(둘레 25칸의 85% 넘게 눈)에서 가장 높은 곳. 큰 덩어리부터 최대 cap개, 서로 60칸 넘게.
    넓은 설원이 없는 지도에는 없다. 지도만으로 정해진다 (맵 생성 화면에도 같은 자리)."""
    cache = gmap.__dict__.setdefault('_lairs_cache', {})
    if cap in cache:
        return list(cache[cap])
    from sim.terrain import _SNOWY_LUT
    mat, _ = gmap.seasons.state(None)
    snow = _SNOWY_LUT[mat] & gmap.land & gmap.walk_static
    need = LAIR_FIELD * gmap.H * gmap.W / (512 * 512)
    out: list[tuple[int, int]] = []
    lab, n = ndimage.label(snow)
    if n:
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        dens = ndimage.uniform_filter(snow.astype(np.float32), 25)
        alt = gmap.layers['alt']
        for c in np.argsort(-sizes):
            if sizes[c] < need or len(out) >= cap:
                break
            ys, xs = np.nonzero((lab == c) & (dens > 0.85))
            ok = (ys >= 12) & (ys < gmap.H - 12) & (xs >= 12) & (xs < gmap.W - 12)
            ys, xs = ys[ok], xs[ok]
            if not len(ys):
                continue
            for k in np.argsort(-(alt[ys, xs] + dens[ys, xs] * 0.05)):
                y, x = int(ys[k]), int(xs[k])
                if all((y - a) ** 2 + (x - b) ** 2 >= 60 ** 2 for a, b in out):
                    out.append((y, x))
                    break
    cache[cap] = out
    return list(out)


class Lair:
    __slots__ = ('kind', 'y', 'x', 'aid', 'timer')

    def __init__(self, kind, y, x):
        self.kind, self.y, self.x, self.aid, self.timer = kind, y, x, 0, 0.0


class Animal:
    __slots__ = ('id', 'kind', 'x', 'y', 'hx', 'hy', 'tx', 'ty', 'mode', 't', 'dir', 'prog', 'unit', 'hp', 'sub', 'lasthp', 'pen',
                 'nova_cd', 'tm', 'fang', 'bcd', 'fph', 'ftm', 'raid')

    def __init__(self, aid, kind, x, y, rng):
        self.id, self.kind = aid, kind
        self.x = self.hx = self.tx = x
        self.y = self.hy = self.ty = y
        self.mode, self.t = GRAZE, float(rng.uniform(0, 4))
        self.dir = 1 if rng.random() < 0.5 else -1
        self.prog = 0.0
        self.unit = -1            # 사나운 동물: 싸우는 병사 번호
        self.hp = 1.0             # 체력 비율 (화면에)
        self.sub = 0.0            # 쓰러져 있는 남은 시간
        self.lasthp = 0.0
        self.nova_cd = 0.0                  # 드래곤 기술: 다음 눈보라까지
        self.tm = 0.0                       # 지금 기술의 남은 시간 (눈보라 모으기, 날기, 지침)
        self.fang = 0.0                     # (쓰지 않음)
        self.bcd = 0.0                      # 날며 다음 숨결까지
        self.fph = FLEE_P                   # 날기 단계 (FLEE_P / TURN_P / STRIKE_P), 그 단계에 든 지 ftm초
        self.ftm = 0.0
        self.raid = False                   # 겨울 습격 중 (RAID·HOMEWARD, 습격 중에 모으는 눈보라도)
        self.pen = -1             # 목장 몫 (짓는 중인 헛간 번호, sim/pasture.py): 울타리 안을 거닐고, 짓는 나라 병사에겐 놀라지 않는다


class Tamer:
    """길들이는 병사. 진행(prog)은 병사마다 따로: 여러 나라가 한 동물을 함께 길들이면 먼저 끝낸 나라가 가져간다."""
    __slots__ = ('aid', 'gen', 'slot', 'hp', 'stuck', 'prog')

    def __init__(self, aid, gen, slot, hp):
        self.aid, self.gen, self.slot, self.hp, self.stuck, self.prog = aid, gen, slot, hp, 0.0, 0.0


class Wildlife:
    def __init__(self, world, rng):
        self.w = world
        self.rng = rng
        self.animals: dict[int, Animal] = {}
        self.tamers: dict[int, Tamer] = {}            # 병사 번호 → 길들이는 중
        self._next = 1
        self._fear_t = 0.0
        self.home, self.cap, self.timer = {}, {}, {}
        self.lairs: list[Lair] = []
        self._struggle = 0.0
        self.bombs: list = []                        # 날아가는 눈보라 [남은 초, x, y, 둥지 동물 종류]
        self.raid_wait = 0                           # 겨울 습격까지 남은 겨울 수 (처음 겨울에 정한다)
        self.raid_free = False                       # 개발 명령으로 낸 습격: 겨울이 끝나도 계속
        self._winter = False
        for k, a in R.WILDLIFE.items():
            if a.get('hostile'):                         # 둥지마다 하나
                self.lairs += [Lair(k, y, x) for y, x in lairs_for(world.map, a['cap'])]
                continue
            m = HABITATS[a['habitat']](world.map)
            ys, xs = np.nonzero(m)
            self.home[k] = (ys, xs)
            self.cap[k] = int(min(a['cap'], len(ys) // a['per_area']))
            self.timer[k] = a['regrow']
            while self.count(k) < self.cap[k]:           # 처음엔 가득
                if not self._spawn_group(k):
                    break
        for lr in self.lairs:
            self._spawn_lair(lr)

    def _spawn_lair(self, lr: Lair) -> None:
        """둥지에 사나운 동물 하나 (잠든 채로)."""
        info = R.WILDLIFE[lr.kind]
        st = R.UNIT_STATS[info['unit']]
        i = self.w.units.add(R.NEUTRAL, info['unit'], lr.x + 0.5, lr.y + 0.5, st['hp'])
        if i < 0:
            return
        self.w.units.state[i] = TAME                     # 움직이지도 덤비지도 않는다 (이 파일이 움직인다)
        an = Animal(self._next, lr.kind, lr.x + 0.5, lr.y + 0.5, self.rng)
        an.mode, an.unit, an.lasthp = SLEEP, i, st['hp']
        an.hx, an.hy = lr.x + 0.5, lr.y + 0.5
        self.animals[an.id] = an
        lr.aid = an.id
        self._next += 1

    def hostile(self, a: Animal) -> bool:
        return bool(R.WILDLIFE[a.kind].get('hostile'))

    def riders(self, nid: int, kind: int) -> int:
        """이 나라가 이 동물을 탄 병사 수 (길들이러 가는 중 포함)."""
        u, mounted = self.w.units, set(R.WILDLIFE[kind]['mounts'].values())
        n = sum(1 for i in np.flatnonzero(u.alive[:u.n] & (u.own[:u.n] == nid)) if int(u.kind[i]) in mounted)
        return n + sum(1 for i, t in self.tamers.items() if u.own[i] == nid and t.aid in self.animals
                       and self.animals[t.aid].kind == kind)

    def count(self, kind) -> int:
        return sum(1 for a in self.animals.values() if a.kind == kind)

    # ------------------------------------------------------------- 태어나기
    def _spawn_group(self, kind) -> bool:
        ys, xs = self.home[kind]
        if not len(ys):
            return False
        w, rng = self.w, self.rng
        b, u = w.builds, w.units
        bl = np.flatnonzero(b.alive[:b.n])
        ul = np.flatnonzero(u.alive[:u.n])
        here = np.array([(a.y, a.x) for a in self.animals.values()]) if self.animals else np.zeros((0, 2))
        best, bs = None, -1e9
        for k in rng.integers(0, len(ys), 40):              # 후보 몇 곳 중 다른 동물과 가장 먼 곳 (넓게 흩어지게)
            y, x = float(ys[k]) + 0.5, float(xs[k]) + 0.5
            if len(bl) and np.min(np.hypot(b.x[bl] - x, b.y[bl] - y)) < SPAWN_CLEAR_B:
                continue
            if len(ul) and np.min(np.hypot(u.x[ul] - x, u.y[ul] - y)) < SPAWN_CLEAR_U:
                continue
            pens = getattr(w, 'pastures', None)
            if pens is not None and pens.covers(x, y, 6.0)[0]:      # 목장 울타리 안·곁에는 새 무리가 생기지 않는다
                continue
            s = min(np.min(np.hypot(here[:, 0] - y, here[:, 1] - x)), 80.0) if len(here) else 80.0
            s += rng.uniform(0, 8)
            if s > bs:
                best, bs = (y, x), s
        if best is None:
            return False
        info = R.WILDLIFE[kind]
        lo, hi = info['group']
        spread = info.get('spread', 3.0)                    # 무리가 흩어져 생기는 반지름 (말은 넓게)
        room = self.cap[kind] - self.count(kind)
        walk, comp = w.map.walk, w.map.comp
        c0 = comp[int(best[0]), int(best[1])]
        for _ in range(min(int(rng.integers(lo, hi + 1)), room)):
            for _ in range(20):                             # 같은 땅의, 건물에서 떨어진 칸 (원 안에 고르게)
                a, r = rng.uniform(0, 2 * np.pi), spread * np.sqrt(rng.uniform(0, 1))
                y, x = best[0] + np.sin(a) * r, best[1] + np.cos(a) * r
                if not (0 <= y < walk.shape[0] and 0 <= x < walk.shape[1] and walk[int(y), int(x)] and comp[int(y), int(x)] == c0):
                    continue
                if len(bl) and np.min(np.hypot(b.x[bl] - x, b.y[bl] - y)) < SPAWN_CLEAR_B:
                    continue
                break
            else:
                y, x = best
            an = Animal(self._next, kind, float(x), float(y), rng)
            an.hy, an.hx = (y, x) if spread > 3.0 else best       # 넓은 무리는 저마다 제 자리 둘레를 거닌다 (흩어진 채로)
            self.animals[an.id] = an
            self._next += 1
        return True

    # ------------------------------------------------------------- 명령
    def order_tame(self, nid, ids, aid, quiet=False) -> int:
        """ids 병사들로 aid 동물과 그 둘레 무리를 길들인다 (동물마다 가까운 병사 하나씩). 반환: 보낸 병사 수."""
        w, u = self.w, self.w.units
        a0 = self.animals.get(aid)
        if a0 is None:
            return 0
        info = R.WILDLIFE[a0.kind]
        if not R.tamers_of(info):                            # 길들이지 않는 동물 (순록)
            if not quiet:
                w.say(f'{R.josa(info["name"], "은", "는")} 길들일 수 없습니다', to=nid)
            return 0
        hostile = self.hostile(a0)
        if hostile and a0.mode not in (SUBDUED, HELD, TAMING):
            if not quiet:
                w.say(f'{R.josa(info["name"], "은", "는")} 체력을 깎아 쓰러뜨려야 길들일 수 있습니다', to=nid)
            return 0
        if hostile and self.riders(nid, a0.kind) >= info['limit']:
            if not quiet:
                w.say(f'{R.UNIT_NAMES[next(iter(info["mounts"].values()))]}는 나라마다 {info["limit"]}기까지입니다', to=nid)
            return 0
        comp = w.map.comp
        ids = np.asarray(ids, np.int64)
        ids = ids[u.alive[ids] & ~u.aboard[ids] & (u.own[ids] == nid)] if len(ids) else ids
        dst = comp[int(a0.y), int(a0.x)]
        can = R.tamers_of(info)
        ok = [int(i) for i in ids if int(u.kind[i]) in can and comp[int(u.y[i]), int(u.x[i])] == dst]
        if not ok:
            if not quiet and len(ids):
                names = ', '.join(R.UNIT_NAMES[k] for k in sorted(can))
                far = any(int(u.kind[i]) in can for i in ids)
                w.say(f'{R.josa(info["name"], "은", "는")} 같은 땅에 있는 병사만 길들일 수 있습니다' if far
                      else f'{R.josa(info["name"], "은", "는")} {names}만 길들일 수 있습니다', to=nid)
            return 0
        self.release(ok)                                     # 다른 동물을 길들이러 가던 병사도 새로 맡긴다
        busy = {t.aid for k, t in self.tamers.items() if u.own[k] == nid}   # 내 나라가 길들이는 중인 동물만 (다른 나라와는 겨룬다)
        herd = [a0] if hostile and a0.id not in busy else [] if hostile else \
            [a for a in self.animals.values() if a.kind == a0.kind and a.id not in busy
             and np.hypot(a.x - a0.x, a.y - a0.y) < info.get('herd_r', 10.0) and comp[int(a.y), int(a.x)] == dst]
        herd.sort(key=lambda a: (a.id != aid, np.hypot(a.x - a0.x, a.y - a0.y)))
        if not herd:
            if not quiet:
                w.say(f'이미 길들이는 중인 {info["name"]}입니다', to=nid)
            return 0
        free = list(ok)
        pairs = []
        food = info.get('food', 0)
        if food:                                         # 먹이: 줄 수 있는 만큼만 (식량은 다 길들였을 때 낸다)
            afford = int(w.nations[nid].res[R.FOOD] // food) - sum(
                1 for k, t in self.tamers.items() if u.own[k] == nid and t.aid in self.animals and self.animals[t.aid].kind == a0.kind)
            if afford <= 0:
                if not quiet:
                    w.say(f'{R.josa(info["name"], "을", "를")} 길들일 먹이가 모자랍니다 (식량 {food})', to=nid)
                return 0
            herd = herd[:afford]
        for a in herd:
            if not free:
                break
            d = [np.hypot(u.x[i] - a.x, u.y[i] - a.y) for i in free]
            pairs.append((free.pop(int(np.argmin(d))), a))
        group = np.array([i for i, _ in pairs], np.int64)
        s = w._route(group, a0.y, a0.x)
        for i, a in pairs:
            near = np.hypot(u.x[i] - a.x, u.y[i] - a.y) <= TAKEOVER
            u.state[i] = TAME if near or s < 0 else MOVE
            u.slot[i] = -1 if near or s < 0 else s
            u.tgt[i] = u.tgb[i] = u.bld[i] = -1
            self.tamers[i] = Tamer(a.id, int(u.gen[i]), int(u.slot[i]), float(u.hp[i]))
            if a.mode != TAMING:
                a.mode, a.t = HELD, 0.0
            if hostile:
                break                                    # 사나운 동물은 한 명만
        if not quiet:
            w.say(f'{R.josa(info["name"], "을", "를")} 길들이러 갑니다 ({info["tame"]:.0f}초, 쓰러져 있는 동안 끝내야 합니다)'
                  if hostile else f'{info["name"]} {len(pairs)}마리를 길들이러 갑니다 ({info["tame"]:.0f}초'
                  + (f', 먹이 식량 {food * len(pairs)})' if food else ')'), to=nid)
        return 1 if hostile else len(pairs)

    def release(self, ids, scare=False) -> None:
        """이 병사들의 길들이기를 그만둔다 (다른 명령, 맞음, 죽음)."""
        u = self.w.units
        for i in [int(i) for i in np.atleast_1d(ids)]:
            t = self.tamers.pop(i, None)
            if t is None:
                continue
            if u.alive[i] and u.state[i] == TAME and u.gen[i] == t.gen:
                u.state[i] = IDLE
            a = self.animals.get(t.aid)
            if a is not None:
                if self.taming(a.id):                        # 다른 병사(다른 나라)가 아직 길들이는 중
                    continue
                a.prog = 0.0
                if self.hostile(a):
                    if a.mode in (HELD, TAMING):
                        a.mode = SUBDUED
                    continue
                a.mode, a.t = GRAZE, 1.0
                if scare:
                    self._flee(a, float(u.x[i]), float(u.y[i]))

    def taming(self, aid, nid=None) -> bool:
        """aid 동물을 길들이는 병사가 있나 (nid를 주면 그 나라 병사만)."""
        u = self.w.units
        return any(t.aid == aid and (nid is None or u.own[k] == nid) for k, t in self.tamers.items())

    # ------------------------------------------------------------- 진행
    def update(self, dt: float) -> None:
        w = self.w
        winter = float(w.season_w[3])
        for k, info in R.WILDLIFE.items():                  # 새 무리 (겨울엔 거의 안 생긴다)
            if info.get('hostile'):
                continue
            if self.count(k) >= self.cap[k]:
                self.timer[k] = info['regrow']
                continue
            self.timer[k] -= dt * (1.0 - 0.9 * winter)
            if self.timer[k] <= 0:
                self.timer[k] = info['regrow']
                self._spawn_group(k)
        self._bombs(dt)
        self._raids()
        self._lairs(dt)
        self._tame(dt)
        self._fear_t -= dt
        if self._fear_t <= 0:
            self._fear_t = 0.25
            self._scare()
        for a in self.animals.values():
            if a.unit < 0:
                self._move(a, dt)

    def _tame(self, dt) -> None:
        w, u, m = self.w, self.w.units, self.w.map
        for i, t in list(self.tamers.items()):
            if i not in self.tamers:                         # 다른 나라가 먼저 길들여 풀렸다
                continue
            a = self.animals.get(t.aid)
            if a is None or not u.alive[i] or u.gen[i] != t.gen or u.aboard[i]:
                self.release([i])
                continue
            if u.hp[i] < t.hp - 1e-3:                       # 맞았다
                w.say('공격을 받아 길들이기를 멈췄습니다', to=int(u.own[i]))
                self.release([i], scare=True)
                continue
            t.hp = float(u.hp[i])
            d = float(np.hypot(u.x[i] - a.x, u.y[i] - a.y))
            st = int(u.state[i])
            if st == MOVE and u.slot[i] == t.slot:
                if d <= TAKEOVER:                            # 다 왔다: 곧장 다가간다
                    u.state[i], u.slot[i] = TAME, -1
                continue
            if st == IDLE and d <= TAKEOVER * 2:            # 길 끝에 닿았다 (동물이 조금 옆에)
                u.state[i] = TAME
                st = TAME
            if st != TAME:                                   # 길이 막혔거나 다른 일을 맡았다
                self.release([i])
                continue
            reach = DRAGON_REACH if a.unit >= 0 else REACH
            if d > reach:
                k = int(u.kind[i])
                sp = R.UNIT_STATS[k]['speed'] * float(m.speed_mul[int(u.y[i]), int(u.x[i])]) ** R.UNIT_STATS[k]['terrain'] * float(u.fx_speed[i])
                step = min(sp * dt, d - reach * 0.8)
                nx, ny = u.x[i] + (a.x - u.x[i]) / d * step, u.y[i] + (a.y - u.y[i]) / d * step
                if m.walk[int(ny), int(nx)]:
                    u.x[i], u.y[i] = nx, ny
                    u.moving[i] = True
                    u.anim[i] += dt * sp * 1.2
                    t.stuck = 0.0
                else:
                    t.stuck += dt
                    if t.stuck > STUCK:
                        self.release([i])
                continue
            a.mode = TAMING
            a.dir = 1 if u.x[i] > a.x else -1                # 병사 쪽을 본다
            t.prog += dt / (R.WILDLIFE[a.kind]['tame'] * climate.tame_mul(w, int(u.own[i]), a.kind))   # 부족: 설원은 거북, 사막은 드래곤이 더디다
            a.prog = max(t.prog, max((o.prog for o in self.tamers.values() if o.aid == a.id), default=0.0))
            if t.prog >= 1.0:
                self._mount(i, a)

    def _mount(self, i, a) -> None:
        """병사와 동물이 합쳐진다 (함께 싸우는 동물이면 동물이 그 나라의 병사가 되고 병사는 그대로)."""
        w, u = self.w, self.w.units
        info = R.WILDLIFE[a.kind]
        if 'companion' in info and w.nations[int(u.own[i])].res[R.FOOD] < info.get('food', 0):
            pass                                             # (먹이가 모자라면 아래에서 이 병사만 그만둔다)
        else:
            for k in [k for k, t in self.tamers.items() if t.aid == a.id and k != i]:   # 먼저 끝냈다: 다른 병사(다른 나라)는 그만
                t = self.tamers.pop(k)
                if u.alive[k] and u.state[k] == TAME and u.gen[k] == t.gen:
                    u.state[k] = IDLE
                w.say(f'다른 나라가 먼저 {R.josa(info["name"], "을", "를")} 길들였습니다', to=int(u.own[k]))
        if 'companion' in info:
            nid = int(u.own[i])
            if w.nations[nid].res[R.FOOD] < info.get('food', 0):
                w.say(f'{R.josa(info["name"], "을", "를")} 길들일 먹이가 모자랍니다 (식량 {info.get("food", 0)})', to=nid)
                self.release([i])
                return
            w.nations[nid].res[R.FOOD] -= info.get('food', 0)
            k = info['companion']
            j = u.add(nid, k, a.x, a.y, R.UNIT_STATS[k]['hp'])
            if j >= 0:
                u.tx[j], u.ty[j] = a.x, a.y
            u.state[i], u.slot[i] = IDLE, -1
            del self.tamers[i]
            del self.animals[a.id]
            w.say(f'{R.josa(info["name"], "을", "를")} 길들였습니다: 함께 싸웁니다', to=nid)
            return
        old = int(u.kind[i])
        new = R.WILDLIFE[a.kind]['mounts'][old]
        ratio = float(u.hp[i]) / R.UNIT_STATS[old]['hp']
        if a.unit >= 0:                                  # 사나운 동물: 싸우던 몸은 사라지고 둥지는 비었다가 다시 난다
            u.alive[a.unit] = False
            ratio = 1.0
            for lr in self.lairs:
                if lr.aid == a.id:
                    lr.aid, lr.timer = 0, R.WILDLIFE[a.kind]['regrow']
        u.kind[i] = new
        u.hp[i] = ratio * R.UNIT_STATS[new]['hp']
        u.x[i], u.y[i] = a.x, a.y
        u.tx[i], u.ty[i] = a.x, a.y
        u.state[i], u.slot[i] = IDLE, -1
        u.cd[i] = 0.0
        del self.tamers[i]
        del self.animals[a.id]
        w.say(f'{R.josa(R.WILDLIFE[a.kind]["name"], "을", "를")} 길들였습니다: '
              f'{R.josa(R.UNIT_NAMES[old], "이", "가")} {R.josa(R.UNIT_NAMES[new], "이", "가")} 되었습니다', to=int(u.own[i]))

    def _flee(self, a, fx, fy) -> None:
        d = max(float(np.hypot(a.x - fx, a.y - fy)), 0.1)
        a.mode, a.t = FLEE, 1.6
        a.tx, a.ty = a.x + (a.x - fx) / d * 9, a.y + (a.y - fy) / d * 9

    def _scare(self) -> None:
        """길들이는 중이 아닌 동물: 가까운 병사나 싸움에서 달아난다."""
        free = [a for a in self.animals.values() if a.mode not in (HELD, TAMING) and a.unit < 0
                and not R.WILDLIFE[a.kind].get('calm')]                 # 느긋한 동물(바위거북)은 달아나지 않는다
        if not free:
            return
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        if len(ids):
            ids = ids[[int(i) not in self.tamers for i in ids]]
        ax = np.array([a.x for a in free], np.float32)
        ay = np.array([a.y for a in free], np.float32)
        if len(ids):
            d = np.hypot(u.x[ids][None] - ax[:, None], u.y[ids][None] - ay[:, None])
            pens = getattr(w, 'pastures', None)
            if pens is not None:                             # 목장 몫인 동물은 짓는 나라 병사를 보고는 놀라지 않는다
                own = u.own[ids]
                for j, a in enumerate(free):
                    o = pens.owner_calm(a)
                    if o >= 0:
                        d[j, own == o] = np.inf
            near = d.argmin(1)
            for j, a in enumerate(free):
                if d[j, near[j]] < FEAR:
                    k = ids[near[j]]
                    self._flee(a, float(u.x[k]), float(u.y[k]))
        hits = [(r[1], r[2]) for r in w.recent if w.time - r[0] < 0.3 and r[5] < 8]   # 8·9 더위·동상은 공격이 아니다
        if hits:
            hx = np.array(hits, np.float32)
            for a in free:
                if a.mode == FLEE:
                    continue
                dd = np.hypot(hx[:, 0] - a.x, hx[:, 1] - a.y)
                if dd.min() < SHOT_FEAR:
                    k = int(dd.argmin())
                    self._flee(a, float(hx[k, 0]), float(hx[k, 1]))

    def _move(self, a, dt) -> None:
        if a.mode in (HELD, TAMING):
            return
        rng, walk = self.rng, self.w.map.walk
        a.t -= dt
        if a.t <= 0:
            pens = getattr(self.w, 'pastures', None)
            inpen = pens.roam(a, rng) if (pens is not None and a.pen >= 0) else None   # 목장 몫: 울타리 안 자리로
            if a.mode == FLEE and inpen is None:            # 다 달아났다: 여기가 새 무리 자리
                a.hx, a.hy = a.x, a.y
            if inpen is not None and (a.mode != GRAZE or rng.random() < 0.6):
                a.tx, a.ty = inpen
                a.mode, a.t = WALK, float(rng.uniform(4, 8))
            elif a.mode == GRAZE or a.mode == FLEE or rng.random() < 0.3:
                ang, r = rng.uniform(0, 2 * np.pi), rng.uniform(0, ROAM)
                a.tx, a.ty = a.hx + np.cos(ang) * r, a.hy + np.sin(ang) * r
                a.mode, a.t = WALK, float(rng.uniform(3, 6))
            else:
                a.mode, a.t = GRAZE, float(rng.uniform(2, 6))
        if a.mode == GRAZE:
            return
        dx, dy = a.tx - a.x, a.ty - a.y
        d = float(np.hypot(dx, dy))
        if d < 0.2:
            a.mode, a.t = GRAZE, float(rng.uniform(2, 5))
            return
        step = min((RUN_SPEED if a.mode == FLEE else PEN_WALK if a.pen >= 0 else WALK_SPEED) * dt, d)
        nx, ny = a.x + dx / d * step, a.y + dy / d * step
        if 0 <= nx < walk.shape[1] and 0 <= ny < walk.shape[0] and walk[int(ny), int(nx)]:
            a.x, a.y = float(nx), float(ny)
        else:                                               # 물가: 무리 자리 쪽으로 돌아선다
            a.tx, a.ty = a.hx, a.hy
            if a.mode == FLEE:
                a.mode = WALK
        if abs(dx) > 0.05:
            a.dir = -1 if dx < 0 else 1

    def drown(self) -> None:
        """얼음이 녹아 물 위에 남은 동물은 사라진다."""
        walk = self.w.map.walk
        for aid in [a.id for a in self.animals.values() if a.unit < 0 and not walk[int(a.y), int(a.x)]]:
            for i, t in list(self.tamers.items()):
                if t.aid == aid:
                    self.release([i])
            del self.animals[aid]

    # ------------------------------------------------------------- 사나운 동물 (둥지)
    def _lairs(self, dt: float) -> None:
        w, u = self.w, self.w.units
        for lr in self.lairs:
            info = R.WILDLIFE[lr.kind]
            a = self.animals.get(lr.aid) if lr.aid else None
            if a is None:                                # 빈 둥지: 때가 되면 (둘레에 병사가 없을 때) 새로 난다
                lr.timer -= dt
                if lr.timer <= 0:
                    ids = w.unit_ids()
                    if not len(ids) or np.min(np.hypot(u.x[ids] - lr.x, u.y[ids] - lr.y)) > info['wake'] + 4:
                        self._spawn_lair(lr)
                    else:
                        lr.timer = 5.0
                continue
            i = a.unit
            if not u.alive[i]:                           # (혹시) 쓰러졌다
                del self.animals[a.id]
                lr.aid, lr.timer = 0, info['regrow']
                continue
            maxhp = R.UNIT_STATS[info['unit']]['hp']
            a.x, a.y = float(u.x[i]), float(u.y[i])
            a.hp = float(u.hp[i]) / maxhp
            if a.mode in (SUBDUED, HELD, TAMING):        # 쓰러져 있다: 몸부림, 시간이 다 되면 일어난다
                a.sub -= dt
                self._writhe(a, dt)
                if a.sub <= 0:
                    for k, t in list(self.tamers.items()):
                        if t.aid == a.id:
                            self.release([k])
                    u.aboard[i] = False
                    u.hp[i] = maxhp * 0.5
                    a.mode, a.prog = FIGHT, 0.0
                    u.own[i], u.state[i] = WILD, TAME
                    for o in self._near_nations(lr, info['guard']):
                        w.say(f'{R.josa(info["name"], "이", "가")} 다시 일어났습니다!', to=o)
                a.lasthp = float(u.hp[i])
                continue
            if a.raid:                                   # 겨울 습격 중: 쓰러지지 않는다 (길들일 수 없다)
                self._raid(lr, a, i, dt)
                a.lasthp = float(u.hp[i])
                continue
            if u.hp[i] <= maxhp * info['subdue']:        # 쓰러진다 (날고 있었으면 떨어진다)
                a.mode, a.sub = SUBDUED, info['subdue_time']
                u.air[i] = False
                self._land_spot(lr, i)
                u.aboard[i] = True
                u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1
                for o in self._near_nations(lr, info['guard'] + 6):
                    w.say(f'{R.josa(info["name"], "이", "가")} 쓰러졌습니다! {info["subdue_time"]:.0f}초 안에 병사를 보내 길들이세요', to=o)
                continue
            hit = u.hp[i] < a.lasthp - 1e-3
            if a.mode == SLEEP:
                if hit or self._intruder(lr, info['wake'], a) >= 0:
                    a.mode = FIGHT
                    u.own[i] = WILD
                    a.nova_cd = 6.0                               # 깨자마자 쓰지는 않는다
                else:
                    u.hp[i] = min(maxhp, u.hp[i] + maxhp * 0.01 * dt)     # 자면서 낫는다
                    u.state[i] = TAME
            if a.mode in (NOVA, FLY, AIR_NOVA):          # 기술을 쓰는 중
                self._skill(lr, a, i, dt)
                a.lasthp = float(u.hp[i])
                continue
            if a.mode == FIGHT and self._start_skill(lr, a, i, dt):
                a.lasthp = float(u.hp[i])
                continue
            if a.mode == FIGHT:
                tgt = self._intruder(lr, info['guard'], a)
                if tgt >= 0:
                    u.state[i], u.tgt[i], u.tgb[i], u.slot[i] = 3, tgt, -1, -1       # ATTACK
                    a.dir = 1 if u.x[tgt] >= u.x[i] else -1
                else:                                    # 둘레에 아무도 없다: 둥지로 걸어 돌아가 잔다
                    u.state[i], u.tgt[i] = TAME, -1
                    d = float(np.hypot(lr.x + 0.5 - u.x[i], lr.y + 0.5 - u.y[i]))
                    if d < 1.2:
                        a.mode = SLEEP
                        u.own[i] = R.NEUTRAL
                    else:
                        sp = R.UNIT_STATS[info['unit']]['speed'] * dt
                        nx, ny = u.x[i] + (lr.x + 0.5 - u.x[i]) / d * sp, u.y[i] + (lr.y + 0.5 - u.y[i]) / d * sp
                        u.x[i], u.y[i] = nx, ny
                        u.moving[i] = True
                        a.dir = 1 if lr.x + 0.5 >= u.x[i] else -1
            a.lasthp = float(u.hp[i])

    # ------------------------------------------------------------- 드래곤 기술 (체력에 따라: rules.WILDLIFE[DRAGON] nova, flight)
    def _foes_near(self, x: float, y: float, r: float, air: bool = False) -> np.ndarray:
        """(x, y)에서 r칸 안의 나라 병사들 (배에 탄 병사는 빼고, 나는 병사는 air일 때만)."""
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        if not len(ids):
            return ids
        ids = ids[(u.own[ids] < R.NEUTRAL) & (air | ~u.air[ids]) & ~u.aboard[ids]]
        return ids[np.hypot(u.x[ids] - x, u.y[ids] - y) <= r] if len(ids) else ids

    def _hurt(self, ids, dmg: float) -> None:
        """드래곤 기술 피해 (배신자 배율, 기후 받는 피해 배율까지)."""
        w, u = self.w, self.w.units
        for j in np.atleast_1d(ids):
            u.hp[j] -= dmg * w.diplo.hurt[u.own[j]] * u.fx_take[j]
            if u.hp[j] <= 0:
                u.alive[j] = False

    def _start_skill(self, lr: Lair, a: Animal, i: int, dt: float) -> bool:
        """싸우는 중: 체력이 깎일수록 기술이 는다. 3단계는 날아오르기, 2단계부터 눈보라 폭발. 시작했으면 True."""
        w, u = self.w, self.w.units
        info = R.WILDLIFE[lr.kind]
        nova, fl = info.get('nova'), info.get('flight')
        if not nova:
            return False
        a.nova_cd -= dt
        ratio = float(u.hp[i]) / R.UNIT_STATS[info['unit']]['hp']
        if fl and ratio <= fl['phase'] and self._intruder(lr, info['guard'], a) >= 0:   # 날아올라 쓰러질 때까지 치고 빠진다
            a.mode, a.tm, a.bcd = FLY, fl['idle'], 0.0
            foes = self._air_foes(lr, info)
            u.air[i] = True
            self._air_flee(lr, a, i, foes)
            u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1
            return True
        if ratio <= nova['phase'] and a.nova_cd <= 0:
            aim = self._nova_aim(a, nova)
            if aim is not None:                                          # 병사가 가장 많이 몰린 곳을 겨눈다 (땅에 원)
                a.mode, a.tm, a.prog = NOVA, nova['wind'], 0.0
                a.tx, a.ty = aim
                a.dir = 1 if aim[0] >= a.x else -1
                w.recent.append((w.time, a.x, a.y, aim[0], aim[1], AIM_SHOT))
                u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1
                return True
        return False

    def _nova_aim(self, a: Animal, nova):
        """눈보라를 던질 곳: 드래곤에서 reach칸 안의 병사들 자리 중, 반지름 r칸 안에 병사가 가장 많은 곳 (min명 넘어야,
        나는 용기사는 혼자서 min명 몫: 용기사만 있어도 던진다). (x, y) 또는 None."""
        u = self.w.units
        foes = self._foes_near(a.x, a.y, nova['reach'], air=True)
        if not len(foes):
            return None
        px, py = u.x[foes].astype(np.float64), u.y[foes].astype(np.float64)
        wt = np.where(u.air[foes], nova['min'], 1)
        cnt = ((np.hypot(px[:, None] - px[None], py[:, None] - py[None]) <= nova['r']) * wt[None]).sum(1)
        k = int(np.argmax(cnt))
        if cnt[k] < nova['min']:
            return None
        near = np.hypot(px - px[k], py - py[k]) <= nova['r']          # 그 무리의 가운데로
        return float(px[near].mean()), float(py[near].mean())

    def _bombs(self, dt: float) -> None:
        """날아가는 눈보라: 닿으면 원 안의 병사 (나는 용기사도)마다 그 자리에서 얼음이 터지고 얼어붙는다."""
        if not self.bombs:
            return
        w, u = self.w, self.w.units
        left = []
        for b in self.bombs:
            b[0] -= dt
            if b[0] > 0:
                left.append(b)
                continue
            nova = R.WILDLIFE[b[3]]['nova']
            w.recent.append((w.time, b[1], b[2], b[1], b[2], BLAST_SHOT))  # 떨어진 곳: 피해 범위만 한 큰 폭발
            hit = self._foes_near(b[1], b[2], nova['r'], air=True)
            for j in hit:
                w.recent.append((w.time, float(u.x[j]), float(u.y[j]), float(u.x[j]), float(u.y[j]), NOVA_SHOT))
                self._hurt([j], min(nova['dmg_frac'] * float(w.k_hp[u.kind[j]]), nova['dmg_max']))
            hit = hit[u.alive[hit]]
            u.freeze[hit] = nova['freeze']
            u.state[hit], u.tgt[hit], u.slot[hit] = IDLE, -1, -1
        self.bombs = left

    def _skill(self, lr: Lair, a: Animal, i: int, dt: float) -> None:
        """기술을 쓰는 중: 눈보라 모으기 → 던짐, 날기 (쓰러질 때까지 치고 빠진다, 아무도 없으면 내려앉는다)."""
        w, u = self.w, self.w.units
        info = R.WILDLIFE[lr.kind]
        u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1                  # 움직임·공격은 여기서 정한다
        u.moving[i] = False
        a.tm -= dt
        if a.mode in (NOVA, AIR_NOVA):
            nova = info['nova']
            a.prog = min(1.0, 1.0 - a.tm / nova['wind'])
            if a.tm <= 0:                                                # 던진다: fly초 뒤 겨눈 곳에서 터진다 (그동안 다시 싸운다 / 다시 난다)
                self.bombs.append([nova['fly'], a.tx, a.ty, lr.kind])
                w.recent.append((w.time, a.x, a.y, a.tx, a.ty, THROW_SHOT))
                a.prog, a.nova_cd = 0.0, nova['cd']
                if a.mode == AIR_NOVA and a.raid:                        # 습격 중이었다: 던지기를 마치고 다시 습격
                    a.mode = RAID
                    a.fph, a.ftm = HOLD_P, 0.0
                elif a.mode == AIR_NOVA:                                 # 날고 있었다: 던지기를 마치고 병사들 반대쪽으로 빠진다
                    a.mode, a.tm = FLY, info['flight']['idle']
                    a.fph, a.ftm = HOLD_P, 0.0
                else:
                    a.mode = FIGHT
            return
        if a.mode != FLY:
            return
        fl, st = info['flight'], R.UNIT_STATS[info['unit']]
        a.nova_cd -= dt
        a.bcd -= dt
        a.ftm += dt
        foes = self._air_foes(lr, info)
        if len(foes):
            a.tm = fl['idle']                                            # 병사가 있는 동안은 계속 난다
        if a.fph == FLEE_P:                                              # 사거리 밖으로 빠진다
            if self._fly_to(a, i, a.tx, a.ty, fl['speed'] * 1.4 * dt) < 0.6 or a.ftm > fl['flee']:
                a.fph, a.ftm = TURN_P, 0.0
        elif a.fph == HOLD_P:                                            # 공격 (숨결·던지기)을 마칠 때까지 그 자리에서: 그다음 빠진다
            if a.ftm >= fl['hold']:
                self._air_flee(lr, a, i, foes)
        elif a.fph == TURN_P:                                            # 돌아본다 (눈보라가 준비됐으면 공중에 멈춰 모은다)
            if len(foes):
                k = foes[np.argmin(np.hypot(u.x[foes] - a.x, u.y[foes] - a.y))]
                a.dir = 1 if u.x[k] >= a.x else -1
            if a.ftm >= fl['turn']:
                aim = self._nova_aim(a, info['nova']) if a.nova_cd <= 0 else None
                if aim is not None:
                    a.mode, a.tm, a.prog = AIR_NOVA, info['nova']['wind'], 0.0
                    a.tx, a.ty = aim
                    a.dir = 1 if aim[0] >= a.x else -1
                    w.recent.append((w.time, a.x, a.y, aim[0], aim[1], AIM_SHOT))
                else:
                    a.fph, a.ftm = STRIKE_P, 0.0
        else:                                                            # 가장 가까운 병사에게 날아가 숨결이 닿으면 뿜는다
            if not len(foes) or a.ftm > fl['flee']:
                self._air_flee(lr, a, i, foes)
            else:
                tgt = int(foes[np.argmin(np.hypot(u.x[foes] - a.x, u.y[foes] - a.y))])
                tx, ty = float(u.x[tgt]), float(u.y[tgt])
                if float(np.hypot(tx - a.x, ty - a.y)) > st['range'] * 0.85:
                    self._fly_to(a, i, tx, ty, fl['speed'] * 1.4 * dt)
                else:
                    a.dir = 1 if tx >= a.x else -1
                    if a.bcd <= 0:                                       # 서리 숨결 (드래곤 공격과 같은 피해·범위) → 다 뿜고 빠진다
                        splash = self._foes_near(tx, ty, st['splash'], air=True)
                        for j in splash:
                            self._hurt([j], st['dmg'] * (1.0 if j == tgt else 0.6))
                        u.slow[splash[u.alive[splash]]] = 2.5
                        w.recent.append((w.time, float(u.x[i]), float(u.y[i]), tx, ty, 3))
                        a.bcd = fl['breath']
                        a.fph, a.ftm = HOLD_P, 0.0
        if a.tm <= 0:                                                    # 둘레에 아무도 없다: 내려앉아 둥지로 (싸움으로 돌아가 걸어간다)
            u.air[i] = False
            self._land_spot(lr, i)
            a.mode = FIGHT

    def _air_foes(self, lr: Lair, info) -> np.ndarray:
        """날고 있는 드래곤이 상대할 병사들: 둥지에서 guard + leash칸 안의 나라 병사 (나는 용기사도, 배에 탄 병사는 빼고)."""
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        if not len(ids):
            return ids
        ids = ids[(u.own[ids] < R.NEUTRAL) & ~u.aboard[ids]]
        return ids[np.hypot(u.x[ids] - lr.x - 0.5, u.y[ids] - lr.y - 0.5) <= info['guard'] + info['flight']['leash']] if len(ids) else ids

    def _air_flee(self, lr: Lair, a: Animal, i: int, foes: np.ndarray, free: bool = False) -> None:
        """빠질 곳을 정한다 (FLEE_P로): 자기를 칠 수 있는 병사들 (활·용기사, 없으면 모두)의 반대쪽으로 곧장,
        그들 모두의 사거리 + margin칸 밖까지. 둥지에서 guard + leash칸이나 지도 끝에 막히면 조금씩 (90도까지) 틀고,
        그래도 막히면 둥지 둘레 안까지만. free (습격 중): 둥지 둘레에 묶이지 않는다 (지도 안이면 된다)."""
        w, u, m = self.w, self.w.units, self.w.map
        info = R.WILDLIFE[lr.kind]
        fl = info['flight']
        cx, cy = lr.x + 0.5, lr.y + 0.5
        leash = info['guard'] + fl['leash']
        if free:
            cx, cy, leash = a.x, a.y, 1e9
        a.fph, a.ftm = FLEE_P, 0.0
        if not len(foes):
            a.tx, a.ty = cx, cy
            return
        can = foes[w.k_ranged[u.kind[foes]] | (u.kind[foes] == R.DRAGON_RIDER)]
        src = can if len(can) else foes
        reach = float(w.k_range[u.kind[src]].max()) + fl['margin']
        px, py = u.x[src].astype(np.float64), u.y[src].astype(np.float64)
        mx, my = float(px.mean()), float(py.mean())
        dx, dy = a.x - mx, a.y - my                                      # 병사들 가운데에서 드래곤 쪽 = 도망갈 쪽
        if np.hypot(dx, dy) < 1e-3:
            dx, dy = cx - mx, cy - my
        if np.hypot(dx, dy) < 1e-3:
            dx, dy = float(a.dir), 0.0
        base = float(np.arctan2(dy, dx))

        def spot(ang):                                                   # ang 쪽으로, 모든 병사의 사거리 밖이 되는 곳
            ux, uy = np.cos(ang), np.sin(ang)
            far = float(((px - mx) * ux + (py - my) * uy).max())        # 그쪽으로 가장 나와 있는 병사
            return mx + ux * (far + reach), my + uy * (far + reach)

        for off in (0.0, 0.4, -0.4, 0.8, -0.8, 1.2, -1.2, 1.57, -1.57):
            tx, ty = spot(base + off)
            if np.hypot(tx - cx, ty - cy) <= leash and 1 <= tx <= m.W - 2 and 1 <= ty <= m.H - 2:
                break
        else:                                                            # 다 막혔다: 반대쪽으로, 둥지 둘레 안까지만
            tx, ty = spot(base)
            d = float(np.hypot(tx - cx, ty - cy))
            if d > leash:
                tx, ty = cx + (tx - cx) * leash / d, cy + (ty - cy) * leash / d
        a.tx, a.ty = float(np.clip(tx, 1, m.W - 2)), float(np.clip(ty, 1, m.H - 2))

    # ------------------------------------------------------------- 겨울 습격 (rules.WILDLIFE[DRAGON] raid)
    def _raids(self) -> None:
        """겨울이 올 때마다 하나씩 센다: every번째 겨울에 잠든 드래곤 하나가 습격에 나선다. 습격 중인데 겨울이 끝나면 돌아간다."""
        winter = float(self.w.season_w[3]) > 0.5
        if winter and not self._winter:
            rd = next((info['raid'] for info in R.WILDLIFE.values() if info.get('raid')), None)
            if rd is not None:
                if self.raid_wait <= 0:                                  # 처음 겨울: 언제 올지 정한다
                    self.raid_wait = int(self.rng.integers(rd['every'][0], rd['every'][1] + 1))
                self.raid_wait -= 1
                if self.raid_wait <= 0:
                    self.start_raid()
                    self.raid_wait = int(self.rng.integers(rd['every'][0], rd['every'][1] + 1))
        if not winter and self._winter and not self.raid_free:          # 겨울이 끝났다: 습격하던 드래곤은 돌아간다
            for a in self.animals.values():
                if a.raid and a.mode != HOMEWARD:
                    self._go_home(a)
        self._winter = winter

    def start_raid(self, free: bool = False) -> bool:
        """잠든 드래곤 하나를 습격에 내보낸다: 제 몫의 설원에 칠 것이 가장 많은 드래곤. 나갔으면 True."""
        w, u = self.w, self.w.units
        best, most = None, 0
        for lr in self.lairs:
            info = R.WILDLIFE[lr.kind]
            a = self.animals.get(lr.aid) if lr.aid else None
            if a is None or not info.get('raid') or a.mode != SLEEP or a.raid:
                continue
            us, bs = self._raid_targets(lr)
            if len(us) + len(bs) > most:
                best, most = (lr, a), len(us) + len(bs)
        if best is None:
            return False
        lr, a = best
        i = a.unit
        a.mode, a.raid, a.bcd, a.nova_cd = RAID, True, 0.0, 4.0
        a.fph, a.ftm = STRIKE_P, 0.0
        self.raid_free = free
        u.own[i], u.air[i] = WILD, True
        u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1
        name = R.WILDLIFE[lr.kind]['name']
        for o in range(len(w.nations)):
            w.say(f'겨울 {R.josa(name, "이", "가")} 둥지에서 깨어나 설원을 습격합니다! (거점은 치지 않는다, 체력이 깎이면 돌아간다)', to=o)
        return True

    def raid_land(self) -> np.ndarray:
        """설원 지역을 둥지마다 나눈 몫: 칸마다 같은 (이어진) 설원에 있는 둥지 중 가장 가까운 둥지의 번호 (self.lairs 차례).
        설원이 아니거나, 둥지가 없는 (따로 떨어진) 설원이면 -1. 처음 한 번 잰다."""
        got = self.__dict__.get('_raid_land')
        if got is not None and got[1] == len(self.lairs):
            return got[0]
        from scipy import ndimage
        from sim import tribes
        m = self.w.map
        snow, _ = tribes.zones(m)
        land = np.full((m.H, m.W), -1, np.int16)
        if self.lairs and snow.any():
            comp, _ = ndimage.label(snow, structure=np.ones((3, 3), bool))   # 이어진 설원 (대각선도 이어진 것으로)
            _, (sy, sx) = ndimage.distance_transform_edt(~snow, return_indices=True)   # 칸마다 가장 가까운 설원 칸
            groups: dict[int, list[int]] = {}
            for k, lr in enumerate(self.lairs):                           # 둥지가 있는 설원 (둥지 칸이 설원이 아니면 가장 가까운 설원)
                y, x = min(max(int(lr.y), 0), m.H - 1), min(max(int(lr.x), 0), m.W - 1)
                groups.setdefault(int(comp[sy[y, x], sx[y, x]]), []).append(k)
            for c, ks in groups.items():                                  # 그 설원 안에서 가장 가까운 둥지의 몫
                seed = np.zeros((m.H, m.W), np.int16)
                for k in ks:
                    lr = self.lairs[k]
                    seed[min(max(int(lr.y), 0), m.H - 1), min(max(int(lr.x), 0), m.W - 1)] = k + 1
                _, (iy, ix) = ndimage.distance_transform_edt(seed == 0, return_indices=True)
                inside = comp == c
                land[inside] = seed[iy[inside], ix[inside]] - 1
        self.__dict__['_raid_land'] = (land, len(self.lairs))
        return land

    def _raid_targets(self, lr: Lair):
        """이 둥지 몫의 설원 (raid_land)에 있는 나라 병사 (배에 탄 병사는 빼고)와 건물 (거점은 빼고). (병사 번호, 건물 번호)."""
        w, u, b, m = self.w, self.w.units, self.w.builds, self.w.map
        land, k = self.raid_land(), self.lairs.index(lr)
        nn = len(w.nations)
        us = w.unit_ids()
        if len(us):
            us = us[(u.own[us] < nn) & ~u.aboard[us]]
            us = us[land[np.clip(u.y[us].astype(int), 0, m.H - 1), np.clip(u.x[us].astype(int), 0, m.W - 1)] == k]
        bs = np.flatnonzero(b.alive[:b.n])
        if len(bs):
            bs = bs[(b.own[bs] < nn) & (b.kind[bs] != R.HALL)]
            bs = bs[land[np.clip(b.y[bs].astype(int), 0, m.H - 1), np.clip(b.x[bs].astype(int), 0, m.W - 1)] == k]
        return us, bs

    def _raid_foes(self, a: Animal) -> np.ndarray:
        """습격하는 드래곤이 피할 병사들: 둘레 sight칸 안의 나라 병사 (나는 용기사도)."""
        info = R.WILDLIFE[a.kind]
        return self._foes_near(a.x, a.y, info['raid']['sight'], air=True)

    def _go_home(self, a: Animal) -> None:
        a.mode, a.prog = HOMEWARD, 0.0
        name = R.WILDLIFE[a.kind]['name']
        for o in range(len(self.w.nations)):
            self.w.say(f'{R.josa(name, "이", "가")} 둥지로 돌아갑니다', to=o)

    def _raid(self, lr: Lair, a: Animal, i: int, dt: float) -> None:
        """습격: 가장 가까운 칠 것 (제 몫 설원의 병사·건물, 거점 빼고)으로 날아가 숨결 → 병사들 반대쪽으로 빠진다 → 돌아본다 (눈보라).
        체력이 subdue 아래, 칠 것이 없으면 둥지로 날아 돌아가 잔다 (체력 heal까지)."""
        w, u, b = self.w, self.w.units, self.w.builds
        info = R.WILDLIFE[lr.kind]
        fl, rd, st = info['flight'], info['raid'], R.UNIT_STATS[info['unit']]
        maxhp = st['hp']
        u.air[i] = True
        if a.mode == AIR_NOVA:                                           # 공중에서 눈보라를 모으는 중
            if u.hp[i] <= maxhp * info['subdue']:
                self._go_home(a)
            else:
                self._skill(lr, a, i, dt)
            return
        u.state[i], u.tgt[i], u.slot[i] = TAME, -1, -1
        u.moving[i] = False
        if a.mode == RAID and u.hp[i] <= maxhp * info['subdue']:
            self._go_home(a)
        if a.mode == HOMEWARD:                                           # 둥지로 날아간다 → 내려앉아 잔다
            cx, cy = lr.x + 0.5, lr.y + 0.5
            if self._fly_to(a, i, cx, cy, fl['speed'] * 1.4 * dt) < 0.3:
                u.air[i] = False
                u.x[i], u.y[i] = cx, cy
                u.hp[i] = max(float(u.hp[i]), maxhp * rd['heal'])
                a.mode, a.raid, a.prog = SLEEP, False, 0.0
                u.own[i] = R.NEUTRAL
                self.raid_free = False
            return
        a.nova_cd -= dt
        a.bcd -= dt
        a.ftm += dt
        us, bs = self._raid_targets(lr)
        if not len(us) and not len(bs):
            self._go_home(a)
            return
        if a.fph == FLEE_P:
            if self._fly_to(a, i, a.tx, a.ty, fl['speed'] * 1.4 * dt) < 0.6 or a.ftm > fl['flee']:
                a.fph, a.ftm = TURN_P, 0.0
            return
        if a.fph == HOLD_P:                                              # 공격을 마칠 때까지 그 자리에서: 칠 수 있는 병사가 있으면 빠졌다가 다시
            if a.ftm >= fl['hold']:
                foes = self._raid_foes(a)
                if len(foes):
                    self._air_flee(lr, a, i, foes, free=True)
                else:
                    a.fph, a.ftm = STRIKE_P, 0.0
            return
        if a.fph == TURN_P:
            if a.ftm >= fl['turn']:
                aim = self._nova_aim(a, info['nova']) if a.nova_cd <= 0 else None
                if aim is not None:
                    a.mode, a.tm, a.prog = AIR_NOVA, info['nova']['wind'], 0.0
                    a.tx, a.ty = aim
                    a.dir = 1 if aim[0] >= a.x else -1
                    w.recent.append((w.time, a.x, a.y, aim[0], aim[1], AIM_SHOT))
                else:
                    a.fph, a.ftm = STRIKE_P, 0.0
            return
        # 가장 가까운 칠 것으로 날아가 숨결이 닿으면 뿜는다
        du = np.hypot(u.x[us] - a.x, u.y[us] - a.y) if len(us) else np.zeros(0)
        db = np.hypot(b.x[bs] - a.x, b.y[bs] - a.y) - b.r[bs] if len(bs) else np.zeros(0)
        if len(du) and (not len(db) or du.min() <= db.min()):
            tgt, onb = int(us[np.argmin(du)]), False
            tx, ty, dist = float(u.x[tgt]), float(u.y[tgt]), float(du.min())
        else:
            tgt, onb = int(bs[np.argmin(db)]), True
            tx, ty, dist = float(b.x[tgt]), float(b.y[tgt]), float(db.min())
        if dist > st['range'] * 0.85:
            self._fly_to(a, i, tx, ty, fl['speed'] * 1.4 * dt)
            return
        a.dir = 1 if tx >= a.x else -1
        if a.bcd > 0:
            return
        splash = self._foes_near(tx, ty, st['splash'], air=True)          # 서리 숨결: 둘레 병사도 (덜) 맞고 느려진다
        for j in splash:
            self._hurt([j], st['dmg'] * (1.0 if (not onb and j == tgt) else 0.6))
        u.slow[splash[u.alive[splash]]] = 2.5
        if onb:
            b.hp[tgt] -= st['dmg'] * rd['bdmg'] * w.diplo.hurt[b.own[tgt]]
        w.recent.append((w.time, float(u.x[i]), float(u.y[i]), tx, ty, 3))
        a.bcd = fl['breath']
        a.fph, a.ftm = HOLD_P, 0.0                                       # 다 뿜을 때까지 그 자리에서

    def _fly_to(self, a: Animal, i: int, tx: float, ty: float, step: float) -> float:
        """날아서 (tx, ty) 쪽으로 step칸. 남은 거리."""
        u = self.w.units
        dx, dy = tx - float(u.x[i]), ty - float(u.y[i])
        d = float(np.hypot(dx, dy))
        if d > 1e-6:
            k = min(step, d) / d
            u.x[i] += dx * k
            u.y[i] += dy * k
            u.moving[i] = True
            a.dir = 1 if dx >= 0 else -1
        return d - min(step, d)

    def _land_spot(self, lr: Lair, i: int) -> None:
        """내려앉을 자리: 지금 칸을 걸을 수 없으면 둥지 쪽으로 걸을 수 있는 칸까지."""
        u, m = self.w.units, self.w.map
        x, y = float(u.x[i]), float(u.y[i])
        cx, cy = lr.x + 0.5, lr.y + 0.5
        for k in range(40):
            t = k / 40
            px, py = x + (cx - x) * t, y + (cy - y) * t
            if 0 <= int(py) < m.H and 0 <= int(px) < m.W and m.walk[int(py), int(px)]:
                u.x[i], u.y[i] = px, py
                return
        u.x[i], u.y[i] = cx, cy

    def _intruder(self, lr: Lair, r: float, a: Animal) -> int:
        """둥지에서 r 안의 (야생이 아닌) 병사 중 이 동물에 가장 가까운 것. 없으면 -1."""
        w, u = self.w, self.w.units
        ids = w.unit_ids()
        ids = ids[u.own[ids] < R.NEUTRAL]
        if not len(ids):
            return -1
        near = ids[np.hypot(u.x[ids] - lr.x - 0.5, u.y[ids] - lr.y - 0.5) <= r]
        if not len(near):
            return -1
        return int(near[np.argmin(np.hypot(u.x[near] - a.x, u.y[near] - a.y))])

    def _near_nations(self, lr: Lair, r: float) -> list[int]:
        """둥지에서 r 안에 병사가 있는 나라들."""
        u, w = self.w.units, self.w
        ids = w.unit_ids()
        ids = ids[(u.own[ids] < len(w.nations)) & (np.hypot(u.x[ids] - lr.x, u.y[ids] - lr.y) <= r)] if len(ids) else ids
        return [int(o) for o in np.unique(u.own[ids])]

    def _near(self, lr: Lair, r: float, nid: int) -> bool:
        u = self.w.units
        ids = self.w.unit_ids(nid)
        return bool(len(ids)) and bool((np.hypot(u.x[ids] - lr.x, u.y[ids] - lr.y) <= r).any())

    def _writhe(self, a: Animal, dt: float) -> None:
        """쓰러진 사나운 동물의 몸부림: 몇 초마다 둘레 병사에게 작은 피해. 길들이는(길들이러 가는) 병사는 다치지 않는다."""
        self._struggle -= dt
        if self._struggle > 0:
            return
        gap, dmg, r = STRUGGLE
        self._struggle = gap
        u = self.w.units
        ids = self.w.unit_ids()
        ids = ids[(u.own[ids] < R.NEUTRAL) & (np.hypot(u.x[ids] - a.x, u.y[ids] - a.y) <= r)]
        for i in ids:
            if int(i) in self.tamers:
                continue
            u.hp[i] -= dmg * u.fx_take[i]                       # 기후: 설원 부족은 사막 밖에서 덜 다친다
            if u.hp[i] <= 0:
                u.alive[i] = False
