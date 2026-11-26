"""AI 나라. 플레이어와 같은 명령만 쓴다. 나라마다 성향(공격성, 궁수 비율, 확장 욕심, 생각 간격)이 다르다.

생각할 때마다
1. 거점에서 병사를 훈련한다 (식량이 넉넉하면)
2. 가까운 빈 자원지에 병사 둘을 보내 건물을 짓는다 (모자란 자원 우선, 적이 가까운 곳은 피한다)
3. 다 못 지은 건물에 일손이 없으면 보낸다
4. 자원이 넉넉하면 먼 자원지 곁에 새 거점을, 석재가 모이면 망루를 세운다
5. 내 건물 근처에 적이 오면 쉬는 병사를 모두 보내 막는다
6. 쉬는 병사가 충분히 모이면 가장 가까운 적 건물을 치러 간다 (일부는 집에 남긴다)
7. 늘 무언가를 길들인다: 말·바위거북 중 거점이나 내 병사에서 가장 가까운 것 (먹이가 모자라면 다음 것).
   항구가 있으면 바다 건너 동물도 (배로 건너가 내리면 길들인다).
   드래곤은 따로: 병력이 되면 먼저 노린다. 집 병력에서 궁수 위주로 사냥대를 꾸려 둥지 앞에 모은 뒤 함께 친다.
   사냥대가 무너지면 잠시 쉬었다 더 크게 다시. 항구가 있으면 바다 건너 둥지도 노린다.
   동물 취향(나라마다 무작위)에 집 둘레 지형의 성향을 더한다 (_lean): 설원이면 드래곤, 사막이면 바위거북, 초원이면 말을
   더 좋아한다 (다른 동물도 그대로 노린다). 어느 나라든 적어도 한 동물은 좋아한다.
9. 자원 (_reserve): 꼭 지을 건물(본거지 땅의 항구, 새 거점)이 있으면 그 몫의 목재·석재는 남겨 둔다
   (궁수 훈련·망루가 먼저 써 버리지 않게). 식량이 남으면 거점을 늘려 훈련을 늘린다 (거점 하나로는 훈련이 느리다).
   남는 자원에 맞춰 쓴다: 목재가 남으면 궁수를 더, 석재가 남으면 망루를 더, 모자란 자원의 자원지를 먼저.
   병사가 몇 남지 않으면 식량 문턱을 낮춰 먼저 뽑고, 농장이 없으면 농장부터 다시.
10. 드래곤 의지 (_drive): 드래곤 부족(dragon_tribes: 시작 거점이 있는 섬에 드래곤이 있는 나라 중, 시작 거점이
   설원·툰드라인 나라와 둥지에 가장 가까운 나라 하나)이 어느 정도 자라면 (DRIVE_TIME초, 건물 DRIVE_BUILDS개)
   드래곤 사냥대를 꾸릴 만큼 병력을 뽑으려 한다 (궁수 먼저). 설원은 초반 자원이 모자라서 밀리기 쉬우니,
   그 병력에 드는 식량은 모자라도 채워 준다 (자원지·시간이 모자라도). 퍼 주는 양은 의지 한 번에 DRIVE_FUND까지,
   사냥이 끝나면 (성공이든 실패든) 다시 채운다. 채워 준 식량으로 뽑은 병사는 '드래곤 몫' (self.reserved):
   막기·쳐들어가기·짓기·길들이기에 쓰지 않고 집에서 기다리다 사냥대에 먼저 든다. 용을 하나 길들이면 풀린다.
12. 외교 (_diplomacy, sim/diplomacy.py): 몇 초마다
   - 동맹 요청에 답한다: 배신자는 거의 거절, 관계가 경계 아래면 거절, 우호면 받는다, 상대가 훨씬 강하면 (겁나서) 받기 쉽다,
     동맹이 이미 많으면 (성향에 따라 1~2) 거절. 동맹을 맺기 좋아하는 정도는 나라마다 (self.social).
   - 가끔 동맹을 청한다: 관계가 좋거나 (보통 이상), 같은 적과 싸우는 (둘 다 미워하는 나라가 있는) 나라에게. 사람에게도.
   - 기간이 끝나 가면 관계가 경계 이상일 때 연장한다.
   - 배신: 동맹이 같은 땅의 이웃이고 내 병력이 훨씬 많으면 (공격성에 따라) 가끔 깬다. 배신자인 동맹도 깬다.
   - 공격을 받으면 그 나라를 동맹들에게 공격 요청한다. 동맹이 공격을 요청하면 (관계가 경계 이상이면) 한동안 그 나라를 먼저 친다.
   - 넉넉하면 가끔 동맹에게 자원을 보낸다 (관계가 우호일 때).
   - 칠 곳을 고를 때 관계가 나쁜 나라를 먼저, 공격 요청받은 나라는 더 먼저.
11. 거북 의지 (_tort_drive): 거북 부족(tortoise_tribes: 시작 거점이 있는 섬에 사막(거북이 사는 땅)이 있는 나라 중,
   시작 거점이 사막인 나라와 그 사막에 가장 가까운 나라 하나)이 어느 정도 자라면 (TORT_TIME초, 건물 TORT_BUILDS개)
   거북을 TORT_MAX마리까지 길들이려 한다: TORT_EVERY초마다 하나, 같은 섬의 가장 가까운 거북을, 먹이가 모자라면
   채워 준다 (게임 내내 TORT_GIFT까지). 동물 비율 상한과 상관없이.
   먹이가 드는 동물(바위거북)은 식량이 모자라면 훈련을 줄여 모은다
8. 적을 살핀다 (_intel): 다른 나라의 용기사·바위거북, 내 땅 가까이의 적
   - 용기사가 있으면: 궁수를 더 뽑고, 유황 채취장을 서두르고, 거점 곁에 화염탑을 더 세운다.
     용기사가 다가오면 궁수만 골라 용기사를 직접 노린다 (근접 병사는 날고 있는 용기사를 못 친다)
   - 바위거북이 있으면: 화살이 덜 들어서 보병을 더 뽑고 망루를 하나 더. 막을 때는 바위거북보다 다른 적을 먼저 노린다
   - 적이 내 땅 가까이 보이면 망루를 하나 더, 적과 가까운 쪽 건물 곁에
   - 상대가 용기사나 바위거북을 가졌으면 나도 바위거북을 길들이러 더 멀리까지 간다
"""
from __future__ import annotations

import numpy as np

from sim import rules as R
from sim.entities import AMOVE, BUILD, IDLE, TAME
from sim.wildlife import FIGHT, HELD, SLEEP, SUBDUED, TAMING, _desert, _grass
from engine.render import materials as S


def dragon_tribes(w) -> set:
    """드래곤 의지를 갖는 AI 나라: 시작 거점이 있는 섬에 드래곤이 있어야 한다 (없으면 드래곤 부족이 아니다).
    그중 시작 거점이 설원·툰드라 위인 나라, 그리고 둥지에 가장 가까운 나라 하나는 꼭 (그런 섬이 있으면).
    처음 한 번 정한다 (시작 거점 자리로)."""
    got = w.__dict__.get('_dragon_tribes')
    if got is not None:
        return got
    m = w.map
    mat, _ = m.seasons.state(None)
    cold = np.isin(mat, (S.SNOW, S.SNOW_OLD, S.ICE, S.TUNDRA)) | (m.layers['pre'] == S.TUNDRA)
    starts = _starts(w)
    lairs = [(a.hy, a.hx) for a in w.wild.animals.values() if a.unit >= 0]
    lair_comps = {int(m.comp[int(ly), int(lx)]) for ly, lx in lairs}
    starts = {nid: p for nid, p in starts.items() if int(m.comp[p]) in lair_comps}   # 자기 섬에 드래곤이 있는 나라만
    out = {nid for nid, p in starts.items() if _share(m, cold, p) >= DRIVE_COLD}
    if starts:
        def far(nid):
            y, x = starts[nid]
            return min(np.hypot(ly - y, lx - x) for ly, lx in lairs if m.comp[int(ly), int(lx)] == m.comp[y, x])
        out.add(min(starts, key=far))
    w.__dict__['_dragon_tribes'] = out
    return out


def set_ai_nations(w, ids) -> None:
    """AI가 조종하는 나라들 (sim/match.py가 알려 준다). 드래곤·거북 부족을 고를 때 AI 나라 중에서만 고른다."""
    w.__dict__['_ai_nations'] = set(int(i) for i in ids)
    w.__dict__.pop('_dragon_tribes', None)
    w.__dict__.pop('_tortoise_tribes', None)


def _starts(w) -> dict:
    """AI 나라마다 시작 거점 자리 (첫 거점)."""
    b = w.builds
    out = {}
    ai = w.__dict__.get('_ai_nations')
    for nat in w.nations:
        if ai is not None and nat.id not in ai:
            continue
        halls = w.building_ids(nat.id, R.HALL)
        if len(halls):
            out[nat.id] = (int(b.y[halls[0]]), int(b.x[halls[0]]))
    return out


def _share(m, mask, p) -> float:
    """p 둘레 DRIVE_R칸의 땅 중 mask인 비율."""
    y, x = p
    y0, y1, x0, x1 = max(y - DRIVE_R, 0), y + DRIVE_R + 1, max(x - DRIVE_R, 0), x + DRIVE_R + 1
    land = m.land[y0:y1, x0:x1]
    return float((mask[y0:y1, x0:x1] & land).sum() / land.sum()) if land.any() else 0.0


def tortoise_tribes(w) -> set:
    """거북 의지를 갖는 AI 나라: 시작 거점이 있는 섬에 사막(거북이 사는 땅)이 있어야 한다.
    그중 시작 거점이 사막인 나라, 그리고 그 섬의 사막에 가장 가까운 나라 하나는 꼭. 처음 한 번 정한다."""
    got = w.__dict__.get('_tortoise_tribes')
    if got is not None:
        return got
    m = w.map
    hab = _lean_masks(m)[1]                                  # 거북이 사는 넓은 사막
    sandy = np.isin(m.layers['pre'], (S.DESERT, S.DUNE))
    starts = {nid: p for nid, p in _starts(w).items() if hab[m.comp == m.comp[p]].any()}   # 자기 섬에 사막이 있는 나라만
    out = {nid for nid, p in starts.items() if _share(m, sandy, p) >= DRIVE_COLD}
    if starts:
        def far(nid):
            y, x = starts[nid]
            ys, xs = np.nonzero(hab & (m.comp == m.comp[y, x]))
            return float(np.min(np.hypot(ys - y, xs - x)))
        out.add(min(starts, key=far))
    w.__dict__['_tortoise_tribes'] = out
    return out


def _lean_masks(gmap):
    """성향을 정하는 지형: 설원(봄·가을에도 눈), 사막, 초원 (지도마다 한 번)."""
    m = gmap.__dict__.get('_lean_masks')
    if m is None:
        from sim.terrain import _SNOWY_LUT
        mat, _ = gmap.seasons.state(None)
        snow = _SNOWY_LUT[mat] & gmap.land & gmap.walk_static
        m = gmap.__dict__['_lean_masks'] = (snow, _desert(gmap), _grass(gmap))
    return m

HUNT_PARTY = 22        # 드래곤 사냥대의 처음 크기 (설원 부족은 HUNT_MIN까지 작게)
HUNT_MIN = 20          # 드래곤 사냥대는 적어도 이만큼
HUNT_MAX = 36          # 실패할 때마다 6씩, 이만큼까지
HUNT_RETRY = 60.0      # 실패한 뒤 다시 노리기까지 (초)
LEAN_R = 40            # 집 둘레 이만큼 안의 지형으로 성향을 정한다
LEAN_MIN = 0.6         # 가장 좋아하는 동물의 성향은 적어도 이만큼
LEAN_KINDS = (R.DRAGON, R.TORTOISE_W, R.HORSE)
DRIVE_R = 8            # 시작 거점 둘레 이만큼 안의
DRIVE_COLD = 0.4       # 이만큼이 설원(봄·가을에도 눈)이나 툰드라면 드래곤 부족
DRIVE_TIME = 300.0     # 이만큼 지나고
DRIVE_BUILDS = 6       # 건물(거점 포함)이 이만큼 있으면 '자랐다'
RAID_CHANCE = 0.025     # 호위 없는 적대국 행렬을 약탈하러 가는 확률 (생각할 때마다, × 공격성). 약탈국이 아닐 때만
TRADE_PEACE = 1.8      # 무역하는 나라의 건물은 이만큼 멀리 있는 것처럼 친다 (덜 고른다)
ESCORT_WANT = 2        # 무역소마다 호위병 (병력이 넉넉할 때)
TRADE_TIME = 120.0     # 무역소: 이만큼 지난 뒤부터
TRADE_TIME2 = 600.0    # 이 뒤로는 TRADE_MAX개까지
TRADE_MAX = 2
TRADE_GAP = 0.45       # 자원의 채움 비율이 이만큼 벌어지면
TORT_TIME = 240.0      # 거북 의지: 이만큼 지나고
TORT_BUILDS = 5        # 건물이 이만큼 있으면
TORT_MAX = 3           # 거북을 이만큼까지
TORT_EVERY = 100.0     # 하나 길들이러 보낸 뒤 다음까지 (초)
TORT_GIFT = 1200.0     # 게임 내내 채워 주는 먹이의 최대
DRIVE_FUND = 1200.0    # 의지 한 번에 채워 주는 식량의 최대 (병력이 죽어 끝없이 퍼 주지 않게)
BEASTS = [R.LANCER, R.HORSE_ARCHER, R.TORTOISE, R.DRAGON_RIDER]   # 길들여 얻는 병력


class Bot:
    def __init__(self, nid: int, rng: np.random.Generator, difficulty: float = 1.0):
        self.id = nid
        self.rng = rng
        self.aggression = float(np.clip(rng.uniform(0.25, 0.9) + (difficulty - 1.0) * 0.6, 0.1, 1.0))
        self.archers = rng.uniform(0.2, 0.6)
        self.greed = rng.uniform(0.5, 1.0)          # 확장 욕심
        self.beast = rng.uniform(0.4, 1.0)          # 동물 취향: 얼마나 자주 길들이고, 병력 중 동물을 얼마나 둘지
        self.interval = rng.uniform(1.5, 2.5)
        self.wait = rng.uniform(0, self.interval)
        self.raid_at = 0.0
        self.intel = {'riders': 0, 'tortoises': 0, 'near': np.zeros(0, np.int64)}
        self.hunt = 0                               # 사냥 중인 드래곤 (동물 번호)
        self.hunters = np.zeros(0, np.int64)
        self.saving = 0.0                           # 먹이(바위거북)를 위해 모으는 식량 (그동안 훈련을 줄인다)
        self.saving_until = 0.0
        self.hunt_phase = ''                        # 'muster' (둥지 앞에 모이는 중) / 'attack'
        self.hunt_until = 0.0                       # 모이기·사냥의 마감 시각
        self.hunt_rally = (0.0, 0.0)
        self.hunt_need = HUNT_PARTY                 # 사냥대 크기 (실패할 때마다 커진다)
        self.hunt_retry = 0.0                       # 실패한 뒤 다시 노릴 수 있는 시각
        self.trip = None                            # 바다 건너 길들이러 가는 중: (동물 번호, 병사들, 마감 시각)
        self.trip_at = 0.0                          # 다음 바다 건너 길들이기를 할 수 있는 시각
        self.lean = {k: 0.0 for k in LEAN_KINDS}    # 지형 성향: 동물 종류 → 0..1 (집이 옮겨 가면 다시)
        self.lean_at = None
        self.reserve = np.zeros(3)                  # 꼭 지을 건물 몫으로 남겨 둔 자원 (식량, 목재, 석재)
        self.drive = 0                              # 드래곤 의지: 모으려는 병력 수 (0이면 없음)
        self.drive_fund = DRIVE_FUND                # 남은 채워 줄 식량
        self.drive_given = 0.0                      # 지금까지 채워 준 식량 (확인용)
        self.reserved = np.zeros(0, np.int64)       # 드래곤 몫 병사 (채워 준 식량으로 뽑았다)
        self.reserved_gen = np.zeros(0, np.int64)
        self.owed = 0                               # 대기열에 든, 드래곤 몫이 될 병사 수
        self.seen = set()                           # 지난번에 본 내 병사 (칸, 세대): 새로 나온 병사를 가린다
        self.riders_had = 0
        self.tort_next = 0.0                        # 거북 의지: 다음 거북을 길들이러 보낼 수 있는 시각
        self.tort_given = 0.0                       # 거북 먹이로 채워 준 식량 (게임 내내)
        self.social = rng.uniform(0.2, 1.0)         # 동맹을 맺기 좋아하는 정도
        self.diplo_at = rng.uniform(5, 15)          # 다음 외교 판단 시각
        self.ask_at = rng.uniform(60, 150)          # 다음 동맹 요청 시각
        self.focus = None                           # 동맹이 요청한 공격: (칠 나라, 끝나는 시각)

    def maybe_think(self, w, dt: float) -> None:
        self.wait -= dt
        if self.wait > 0:
            return
        self.wait = self.interval * self.rng.uniform(0.8, 1.2)
        nat = w.nations[self.id]
        if nat.alive:
            self.think(w, nat)

    def think(self, w, nat) -> None:
        u, b = w.units, w.builds
        mine = w.unit_ids(self.id)
        esc = w.trade.escort_ids(self.id)
        if esc:
            mine = np.setdiff1d(mine, esc)                           # 호위병은 무역소가 쓴다 (sim/trade.py)
        idle = mine[u.state[mine] == IDLE]
        halls = w.building_ids(self.id, R.HALL, done=True)
        intel = self.intel = self._intel(w)
        if w.time >= self.diplo_at:
            self.diplo_at = w.time + self.rng.uniform(3, 6)
            self._diplomacy(w, nat, mine)
        idle = self._track_reserved(w, mine, idle)
        if self.hunt:
            self._prune_hunters(w)
            if self.hunt_phase == 'muster' and self._threat(w, halls_only=True) is not None:
                self._end_hunt(w, failed=False)            # 모이는 중에 거점이 공격받으면 그만두고 막는다
            else:
                idle = np.setdiff1d(idle, self.hunters)
        if self.trip is not None:
            idle = self._tame_trip(w, idle)
        home = self._home(w)
        if self.lean_at is None and len(halls):                 # 부족의 바탕: 시작 거점 둘레의 지형
            self._lean(w, (float(b.y[halls[0]]), float(b.x[halls[0]])))
        self.reserve = self._reserve(w, nat, home, halls)
        self.drive = self._drive(w, home, halls, mine)
        # 1. 훈련 (적의 용기사엔 궁수를, 바위거북엔 보병을 더, 목재가 남으면 궁수를 더, 모자라면 덜)
        wood = nat.res[R.WOOD] - self.reserve[R.WOOD]
        arch = self.archers + (0.25 if intel['riders'] else 0) - (0.2 if intel['tortoises'] else 0)
        arch += 0.2 if wood > nat.caps[R.WOOD] * 0.6 else -0.2 if wood < 60 and not intel['riders'] else 0.0
        arch = float(np.clip(arch, 0.1, 0.9))
        want_q = 5 if nat.res[R.FOOD] > nat.caps[R.FOOD] * 0.8 or self.drive else 2   # 넉넉하거나 드래곤 병력을 모을 때는 더 많이
        floor = 40 if len(mine) < 4 else 45                     # 병사가 몇 남지 않았으면 먼저 뽑는다
        a_cost = R.UNIT_STATS[R.ARCHER]['cost'][R.WOOD]
        ranged = int(w.k_ranged[u.kind[mine]].sum()) if len(mine) else 0
        queued = sum(len(b.queue[h]) for h in halls)
        for h in halls:
            while len(b.queue[h]) < want_q:
                boost = self.drive and len(mine) + queued < self.drive and self.drive_fund > 0
                p_arch = 0.85 if boost and ranged < self.drive // 3 + 2 else arch    # 드래곤 사냥대는 궁수가 먼저
                kind = R.ARCHER if self.rng.random() < p_arch and wood >= a_cost else R.INFANTRY   # 남겨 둘 목재는 쓰지 않는다
                if self.saving and w.time > self.saving_until:
                    self.saving = 0.0                       # 너무 오래 못 모았다: 그만 모은다
                if boost:                                   # 드래곤 병력: 식량이 모자라면 채워 준다
                    give = max(0.0, R.UNIT_STATS[kind]['cost'][R.FOOD] - nat.res[R.FOOD])
                    nat.res[R.FOOD] += give
                    self.drive_fund -= give
                    self.drive_given += give
                elif nat.res[R.FOOD] < floor + self.saving or (nat.rate[R.FOOD] < 0 and nat.res[R.FOOD] < 150 and len(mine) >= 4):
                    break
                if not (w.train(self.id, h, kind, quiet=True) or w.train(self.id, h, R.INFANTRY, quiet=True)):
                    break
                queued += 1
                if boost:
                    self.owed += 1                          # 나오면 드래곤 몫
                if kind == R.ARCHER:
                    wood -= a_cost
                    ranged += 1
        if (self.drive or self.hunt) and nat.res[R.FOOD] < 10 and self.drive_fund > 0:   # 모은 병력이 굶지 않게
            give = min(20.0, self.drive_fund)
            nat.res[R.FOOD] += give
            self.drive_fund -= give
            self.drive_given += give
        if home is None:
            if len(idle):
                self._attack(w, idle)
            return
        # 4. 방어 건물: 망루·화염탑·유황 채취장 (공격받는 중에도 먼저)
        if len(idle) >= 2:
            idle = self._defenses(w, idle, intel, halls, home)
        # 5. 방어: 날고 있는 용기사는 궁수가 직접 노리고, 바위거북보다 다른 적을 먼저
        threat = self._threat(w)
        if threat is not None and len(idle):
            near = intel['near']
            air = near[u.air[near]] if len(near) else near
            if len(air):
                ranged = idle[w.k_ranged[u.kind[idle]]]
                if len(ranged):
                    tgt = int(air[np.argmin(np.hypot(u.x[air] - u.x[ranged].mean(), u.y[air] - u.y[ranged].mean()))])
                    w.order_attack(ranged, unit=tgt)
                    idle = np.setdiff1d(idle, ranged)
                if len(idle):                                         # 근접 병사: 땅의 적이 있으면 그쪽으로
                    ground = near[~u.air[near]]
                    if len(ground):
                        w.order_move(idle, float(u.y[ground[0]]), float(u.x[ground[0]]), attack=True)
                return
            other = near[u.kind[near] != R.TORTOISE] if len(near) else near
            pick = other if len(other) else near
            if len(pick):
                threat = (float(u.y[pick[0]]), float(u.x[pick[0]]))
            w.order_move(idle, threat[0], threat[1], attack=True)
            return
        builders = mine[u.state[mine] == BUILD]
        # 3. 일손 없는 공사장
        for f in w.building_ids(self.id, done=False):
            if not (u.bld[builders] == f).any() and len(idle) >= 1:
                pick = self._nearest(w, idle, b.y[f], b.x[f], 2)
                w.order_build(pick, f)
                idle = np.setdiff1d(idle, pick)
        # 4-1. 새 거점: 자원이 넉넉하면 거점에서 먼 내 자원지 곁에
        any_hall = len(w.building_ids(self.id, R.HALL)) > 0                     # 짓는 중인 것까지
        if (len(idle) >= (1 if not any_hall else 2) and self._want_hall(w, nat, halls)
                and w.can_afford(self.id, R.BUILD_STATS[R.HALL]['cost']) and (not any_hall or self.rng.random() < 0.6)):
            spot = self._hall_spot(w, halls)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 3)
                if w.place_building(self.id, R.HALL, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 7. 드래곤 사냥: 사냥 중이면 이어 가고, 아니면 여건이 될 때 사냥대를 꾸린다
        lean = self._lean(w, home)
        if self.hunt:
            self._dragon_hunt(w, home)
        elif threat is None and w.time >= self.hunt_retry and self.rng.random() < 0.3 + 0.4 * self.beast + 0.3 * lean[R.DRAGON]:
            idle = self._start_hunt(w, idle, home)
        # 7-0. 거북 의지: 거북 부족은 같은 섬의 거북을 (먹이가 모자라면 채워 받아서)
        if threat is None and len(idle) and self._tort_drive(w):
            idle = self._tame_tortoise(w, idle, home, nat)
        # 7-1. 길들이기: 쉬는 병사가 둘만 있어도 가장 가까운 말·바위거북을
        #      동물은 여러 수단 중 하나: 취향만큼만, 병력 중 동물(기병·바위거북·용기사)이 너무 많으면 그만
        beasts = np.isin(u.kind[mine], BEASTS).mean() if len(mine) else 1.0
        top = max(lean.values())
        if (len(idle) >= 2 and threat is None and len(mine) >= 5
                and beasts < 0.25 + 0.2 * self.beast + 0.1 * lean[R.HORSE]      # 초원 부족은 기병을 조금 더 둔다
                and self.rng.random() < 0.35 + 0.35 * self.beast + 0.2 * top):
            idle = self._tame(w, idle, home, nat)
        # 2. 확장
        if len(builders) < 4 and len(idle) >= (1 if len(mine) < 6 else 3) and self.rng.random() < max(self.greed, 0.8 if len(mine) < 6 else 0):
            site = self._pick_site(w, nat, home)
            if site is not None:
                kind = R.SITE_BUILDING[site.kind]
                pick = self._nearest(w, idle, site.y, site.x, 2)
                if w.place_building(self.id, kind, site.y, site.x, pick, site=site.id, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-1-1. 나룻배를 못 띄운 해안이 있으면 그 곁에 항구 (다른 바다로 가려면 그 바다의 항구가 필요하다)
        want = w.fleet.want_harbor.get(self.id)
        if (want is not None and len(idle) >= 2 and len(w.building_ids(self.id, R.HARBOR)) < 3
                and w.can_afford(self.id, R.BUILD_STATS[R.HARBOR]['cost'])):
            spot = self._harbor_near(w, want)
            w.fleet.want_harbor.pop(self.id, None)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.HARBOR, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-2. 항구: 바다 건너에 노릴 것(빈 자원지, 적)이 있는데 본거지 땅에 항구가 없으면 (배는 병사들이 있는 땅의 항구에서 탄다)
        if (not self._harbors_home(w, home) and len(idle) >= 2 and self.rng.random() < 0.35
                and w.can_afford(self.id, R.BUILD_STATS[R.HARBOR]['cost']) and self._overseas(w, home)):
            spot = self._harbor_spot(w, home)
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.HARBOR, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 4-3. 전함: 항구가 있으면 몇 척, 쉬는 전함은 가까운 적 배를 쫓는다
        harbors = w.building_ids(self.id, R.HARBOR, done=True)
        ships = w.fleet.warships(self.id)
        if len(harbors) and len(ships) + sum(len(b.queue[h]) for h in harbors) < 1 + int(self.aggression * 2.5)                 and w.can_afford(self.id, R.WARSHIP_COST) and self.rng.random() < 0.3:
            w.train(self.id, int(harbors[0]), R.WARSHIP, quiet=True)
        for sh in ships:
            if sh.state == 'idle':
                foes = [o for o in w.fleet.boats if w.diplo.foe(self.id, o.own) and np.hypot(o.y - sh.y, o.x - sh.x) < 45]
                if foes:
                    w.fleet.hunt([sh], min(foes, key=lambda o: np.hypot(o.y - sh.y, o.x - sh.x)))
        # 6. 공격
        need = 8 + (1 - self.aggression) * 14 + w.time / 90
        hold = self.drive and not self.hunt and len(mine) < self.drive + 8    # 드래곤 병력을 모으는 중엔 쳐들어가지 않는다
        if len(idle) >= need and w.time >= self.raid_at and not hold:
            keep = int(len(idle) * 0.25)
            self._attack(w, idle[keep:])
            self.raid_at = w.time + 25

    # ------------------------------------------------------------- 도움
    def _defenses(self, w, idle, intel, halls, home):
        """망루와 화염탑 (공격받는 중에도 먼저 짓는다)."""
        u = w.units
        b = w.builds
        # 망루 (적이 가까이 보이거나 바위거북이 있으면 더, 적과 가까운 쪽에)
        towers = len(w.building_ids(self.id, R.TOWER))
        camps = len(w.building_ids(self.id)) - len(halls) - towers
        stone = w.nations[self.id].res[R.STONE] - self.reserve[R.STONE]
        want_t = (1 + camps // 3 + (1 if len(intel['near']) else 0) + (1 if intel['tortoises'] else 0)
                  + min(3, int(stone // 250)))                                 # 석재가 남으면 더
        tcost = R.BUILD_STATS[R.TOWER]['cost']
        if (len(idle) >= 3 and towers < want_t and (self._spare(w, tcost) or (towers < 2 and len(intel['near']) and w.can_afford(self.id, tcost)))
                and self.rng.random() < (0.7 if len(intel['near']) else 0.5)):
            c = self._guard_site(w, front=True)
            spot = w._open_spot(b.y[c], b.x[c], self.rng.uniform(7, 11), 2) if c >= 0 else None
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.TOWER, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 무역소: 자원이 한쪽으로 쏠렸고 (채움 비율 차이 TRADE_GAP 이상), 무역할 만한 나라가 있으면 (TRADE_MAX개까지, sim/trade.py)
        posts = w.building_ids(self.id, R.TRADE_POST)
        tcost = R.BUILD_STATS[R.TRADE_POST]['cost']
        nat = w.nations[self.id]
        f = [v / max(nat.caps[k], 1.0) for k, v in enumerate(nat.res)]
        first = len(posts) == 0                                     # 첫 무역소는 무역할 나라만 있으면 (상대도 지어야 오가니 일찍)
        if (w.time > TRADE_TIME and len(posts) < (1 if w.time < TRADE_TIME2 else TRADE_MAX) and (first or max(f) - min(f) >= TRADE_GAP)
                and len(idle) >= 2 and w.can_afford(self.id, tcost) and self.rng.random() < (0.6 if first else 0.3)
                and any(w.trade.wants(self.id, o.id) for o in w.nations if o.id != self.id and o.alive)):
            c = self._guard_site(w, front=False)
            spot = w._open_spot(b.y[c], b.x[c], self.rng.uniform(9, 13), R.BUILD_STATS[R.TRADE_POST]['r']) if c >= 0 else None
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.TRADE_POST, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 호위: 무역소마다 ESCORT_WANT명 (쉬는 병사가 넉넉할 때). 약탈: 적대국 행렬이 가깝고 호위가 없으면 (약탈 단계 2 아래일 때)
        if len(posts) and len(idle) >= 8 and self.rng.random() < 0.2:
            for p in w.trade.posts(self.id):
                have = len(w.trade.escorts.get(int(p), [])) + sum(len(c.escort) for c in w.trade.caravans if c.home == int(p))
                if have < ESCORT_WANT:
                    pick = self._nearest(w, idle, b.y[p], b.x[p], ESCORT_WANT - have)
                    if w.trade.assign(pick, int(p)):
                        idle = np.setdiff1d(idle, pick)
        if len(idle) >= 3 and w.trade.raid_lv[self.id] < 1 and self.rng.random() < RAID_CHANCE * self.aggression:
            for c in w.trade.caravans:
                if c.at_sea or c.escort or not w.trade.hostile(self.id, c.own):
                    continue
                x, y, _ = c.at()
                near = idle[np.hypot(u.x[idle] - x, u.y[idle] - y) < 30]
                if len(near) >= 2:
                    w.trade.raid(near[:4], c)
                    idle = np.setdiff1d(idle, near[:4])
                    break
        # 유황 채취장 (4-1-2): 유황 채취장: 아직 없으면 같은 땅(또는 항구로 갈 수 있는)의 가장 가까운 빈 유황 웅덩이에 곧장 일꾼을 보낸다
        if (len(idle) >= 2 and not len(w.building_ids(self.id, R.SULFUR_PIT)) and w.time > 60
                and w.can_afford(self.id, R.BUILD_STATS[R.SULFUR_PIT]['cost']) and self.rng.random() < 0.5):
            comp = w.map.comp
            hc = comp[int(home[0]), int(home[1])]
            harbor = bool(w.fleet.harbors_on(self.id, hc))
            free = [s for s in w.sites if s.kind == R.SULFUR and s.building < 0 and (comp[s.y, s.x] == hc or harbor)]
            if free:
                s = min(free, key=lambda s: np.hypot(s.y - home[0], s.x - home[1]))
                pick = self._nearest(w, idle, s.y, s.x, 2)
                if w.place_building(self.id, R.SULFUR_PIT, s.y, s.x, pick, site=s.id, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        # 화염탑: 유황과 석재가 모이면 (적에게 용기사가 있으면 더 많이, 서둘러, 거점 곁에)
        fst = R.BUILD_STATS[R.FIRE_TOWER]
        want_f = 1 + camps // 4 + min(3, intel['riders'])
        if (len(idle) >= 2 and len(w.building_ids(self.id, R.FIRE_TOWER)) < want_f
                and w.can_afford(self.id, fst['cost'], fst['sulfur']) and (intel['riders'] or self._spare(w, fst['cost']))
                and self.rng.random() < (0.85 if intel['riders'] else 0.6)):
            c = self._guard_site(w, front=not intel['riders'])
            spot = w._open_spot(b.y[c], b.x[c], self.rng.uniform(7, 11), 2) if c >= 0 else None
            if spot is not None:
                pick = self._nearest(w, idle, spot[0], spot[1], 2)
                if w.place_building(self.id, R.FIRE_TOWER, spot[0], spot[1], pick, quiet=True) >= 0:
                    idle = np.setdiff1d(idle, pick)
        return idle

    def _track_reserved(self, w, mine, idle):
        """드래곤 몫 병사: 새로 나온 병사를 빚진 만큼 드래곤 몫으로, 죽은 병사는 빼고, 용을 길들였거나 의지가 끝났으면 푼다.
        반환: 드래곤 몫을 뺀 쉬는 병사."""
        u = w.units
        cur = {(int(i), int(u.gen[i])) for i in mine}
        if self.owed > 0:
            new = sorted(i for i, _ in cur - self.seen)[:self.owed]
            if new:
                new = np.array(new, np.int64)
                self.reserved = np.concatenate([self.reserved, new])
                self.reserved_gen = np.concatenate([self.reserved_gen, u.gen[new].astype(np.int64)])
                self.owed -= len(new)
        self.seen = cur
        r = self.reserved
        if len(r):
            ok = u.alive[r] & (u.own[r] == self.id) & (u.gen[r] == self.reserved_gen)
            self.reserved, self.reserved_gen = r[ok], self.reserved_gen[ok]
        riders = w.wild.riders(self.id, R.DRAGON)
        if riders > self.riders_had or (not self.drive and not self.hunt):   # 용을 잡았다 (또는 의지가 끝났다): 풀어 준다
            self.reserved = self.reserved[:0]
            self.reserved_gen = self.reserved_gen[:0]
            self.owed = 0
        self.riders_had = riders
        return np.setdiff1d(idle, self.reserved) if len(self.reserved) else idle

    def _drive(self, w, home, halls, mine) -> int:
        """드래곤 의지: 설원 부족이 자랐고, 용기사가 모자라고, 노릴 둥지가 있으면 모으려는 병력 수 (사냥대 + 집 지킬 몫)."""
        if home is None or not len(halls) or w.time < DRIVE_TIME:
            return 0
        if self.id not in dragon_tribes(w) or len(w.building_ids(self.id)) < DRIVE_BUILDS:
            return 0
        wild = w.wild
        if wild.riders(self.id, R.DRAGON) >= R.WILDLIFE[R.DRAGON]['limit']:
            return 0
        if not any(a.unit >= 0 for a in wild.animals.values()):
            return 0
        return max(HUNT_MIN, self.hunt_need - round(3 * self.lean[R.DRAGON])) + 8   # 사냥대 + 집 지킬 몫과 일꾼

    def _reserve(self, w, nat, home, halls) -> np.ndarray:
        """꼭 지을 건물 몫으로 남겨 둘 자원: 본거지 땅에 항구가 없는데 바다 건너 노릴 것이 있으면 항구,
        거점을 늘리고 싶으면 거점."""
        r = np.zeros(3)
        if home is None:
            return r
        if w.time > 90 and not self._harbors_home(w, home) and self._overseas(w, home):
            r += R.BUILD_STATS[R.HARBOR]['cost']
        if self._want_hall(w, nat, halls):
            r += R.BUILD_STATS[R.HALL]['cost']
        return r

    def _spare(self, w, cost) -> bool:
        """남겨 둘 몫을 빼고도 낼 수 있나."""
        res = w.nations[self.id].res
        return all(res[k] >= cost[k] + self.reserve[k] for k in range(3))

    def _want_hall(self, w, nat, halls) -> bool:
        """거점을 늘리고 싶나: 거점이 없거나, (3개 미만이고) 식량이 남거나 수입이 거점들의 훈련보다 빠를 때."""
        n = len(w.building_ids(self.id, R.HALL))                             # 짓는 중인 것까지
        if n == 0:
            return True
        if n > len(halls) or n >= 3 or w.time < 150:
            return False
        per_hall = R.UNIT_STATS[R.INFANTRY]['cost'][R.FOOD] / R.UNIT_STATS[R.INFANTRY]['time']   # 거점 하나가 쓰는 식량 (초당)
        return nat.res[R.FOOD] > nat.caps[R.FOOD] * 0.7 or nat.rate[R.FOOD] > per_hall * n * 0.8

    def _hall_spot(self, w, halls):
        """새 거점 자리: 거점에서 가장 먼 내 자원지 곁 (20칸 넘게 떨어졌으면), 아니면 거점에서 16~24칸 떨어진 빈 땅."""
        b = w.builds
        camps = [c for c in w.building_ids(self.id, done=True) if b.kind[c] in (R.FARM, R.LUMBER, R.QUARRY, R.SULFUR_PIT)]
        if not len(halls):
            src = camps or list(w.building_ids(self.id, done=True))
            if not src:
                return None
            c = src[0]
            return w._open_spot(b.y[c], b.x[c], self.rng.uniform(10, 14), 5)
        if camps:
            far = max(camps, key=lambda c: np.min(np.hypot(b.x[halls] - b.x[c], b.y[halls] - b.y[c])))
            if np.min(np.hypot(b.x[halls] - b.x[far], b.y[halls] - b.y[far])) > 20:
                spot = w._open_spot(b.y[far], b.x[far], self.rng.uniform(10, 14), 5)
                if spot is not None:
                    return spot
        h = int(self.rng.choice(halls))
        for _ in range(4):
            spot = w._open_spot(b.y[h], b.x[h], self.rng.uniform(16, 24), 5)
            if spot is not None and np.min(np.hypot(b.y[halls] - spot[0], b.x[halls] - spot[1])) > 14:
                return spot
        return None

    def _home(self, w):
        own = w.building_ids(self.id)
        if len(own) == 0:
            return None
        b = w.builds
        y, x = float(b.y[own].mean()), float(b.x[own].mean())
        m = w.map
        halls = own[b.kind[own] == R.HALL]
        ref = halls if len(halls) else own
        hcs = m.comp[b.y[ref].astype(int), b.x[ref].astype(int)]
        if m.comp[int(y), int(x)] not in hcs:            # 섬 여럿에 건물이 있어 가운데가 바다(또는 다른 땅)면: 가운데에서 가장 가까운 거점
            k = int(np.argmin(np.hypot(b.y[ref] - y, b.x[ref] - x)))
            return float(b.y[ref[k]]), float(b.x[ref[k]])
        return y, x

    def _nearest(self, w, ids, y, x, k):
        d = np.hypot(w.units.x[ids] - x, w.units.y[ids] - y)
        return ids[np.argsort(d)[:k]]

    def _threat(self, w, halls_only: bool = False):
        u, b = w.units, w.builds
        own = w.building_ids(self.id, R.HALL) if halls_only else w.building_ids(self.id)
        foes = np.flatnonzero(u.alive[:u.n] & (w.diplo.friend[self.id, u.own[:u.n]] == 0))
        if len(own) == 0 or len(foes) == 0:
            return None
        d = np.hypot(u.x[foes][:, None] - b.x[own][None], u.y[foes][:, None] - b.y[own][None])
        close = d.min(1) < 22
        if not close.any():
            return None
        j = foes[close][0]
        return float(u.y[j]), float(u.x[j])

    def _intel(self, w) -> dict:
        """다른 나라의 용기사·바위거북 수와 내 건물 가까이(30칸)의 적 병사."""
        u, b = w.units, w.builds
        foes = np.flatnonzero(u.alive[:u.n] & ~u.aboard[:u.n] & (w.diplo.friend[self.id, u.own[:u.n]] == 0) & (u.own[:u.n] < R.NEUTRAL))
        riders = int((u.kind[foes] == R.DRAGON_RIDER).sum()) if len(foes) else 0
        torts = int((u.kind[foes] == R.TORTOISE).sum()) if len(foes) else 0
        own = w.building_ids(self.id)
        near = foes[:0]
        if len(foes) and len(own):
            d = np.hypot(u.x[foes][:, None] - b.x[own][None], u.y[foes][:, None] - b.y[own][None]).min(1)
            near = foes[d < 30]
            near = near[np.argsort(d[d < 30])]
        return {'riders': riders, 'tortoises': torts, 'near': near}

    def _guard_site(self, w, front: bool) -> int:
        """방어 건물을 세울 곁: front면 적과 가장 가까운 내 건물, 아니면 거점 (없으면 아무 내 건물)."""
        b, u = w.builds, w.units
        own = w.building_ids(self.id, done=True)
        if not len(own):
            return -1
        if not front:
            halls = own[b.kind[own] == R.HALL]
            return int(self.rng.choice(halls if len(halls) else own))
        foes = np.flatnonzero(u.alive[:u.n] & (w.diplo.friend[self.id, u.own[:u.n]] == 0) & (u.own[:u.n] < R.NEUTRAL))
        fb = np.flatnonzero(b.alive[:b.n] & (w.diplo.friend[self.id, b.own[:b.n]] == 0))
        pts = np.concatenate([np.stack([u.x[foes], u.y[foes]], 1), np.stack([b.x[fb], b.y[fb]], 1)]) if len(foes) + len(fb) else None
        if pts is None or self.rng.random() < 0.3:                   # 가끔은 아무 곳에나 (한쪽만 두껍지 않게)
            return int(self.rng.choice(own))
        d = np.hypot(b.x[own][:, None] - pts[None, :, 0], b.y[own][:, None] - pts[None, :, 1]).min(1)
        return int(own[np.argmin(d)])

    def _prune_hunters(self, w):
        u = w.units
        h = self.hunters
        self.hunters = h[u.alive[h] & (u.own[h] == self.id)] if len(h) else h

    def _end_hunt(self, w, failed: bool, home=None):
        """사냥을 그만둔다. 실패면 잠시 쉬고 다음엔 더 큰 사냥대로. 남은 사냥꾼은 집으로."""
        if failed or self.hunt_phase == 'attack':
            self.drive_fund = DRIVE_FUND                     # 사냥을 치렀다: 다음 사냥대 몫의 식량을 다시
        if failed:
            self.hunt_retry = w.time + HUNT_RETRY
            self.hunt_need = min(self.hunt_need + 6, HUNT_MAX)
        if home is not None and len(self.hunters):
            w.order_move(self.hunters, home[0], home[1])
        self.hunt, self.hunt_phase = 0, ''
        self.hunters = self.hunters[:0]

    def _start_hunt(self, w, idle, home):
        """같은 땅(항구가 있으면 바다 건너도)의 드래곤을 노린다: 집 가까이의 병사에서 궁수 위주로 사냥대를 꾸려
        둥지 앞(바다 건너면 집)에 모은다. 사냥대가 모자라면 그만둔다 (병력이 늘면 다시)."""
        u, comp, wild = w.units, w.map.comp, w.wild
        info = R.WILDLIFE[R.DRAGON]
        if w.time < 120 or wild.riders(self.id, R.DRAGON) >= info['limit']:
            return idle
        hc = comp[int(home[0]), int(home[1])]
        harbor = bool(w.fleet.harbors_on(self.id, hc))
        lairs = [a for a in wild.animals.values() if a.unit >= 0 and not wild.taming(a.id, self.id)
                 and (comp[int(a.hy), int(a.hx)] == hc or harbor)]
        if not lairs:
            return idle
        mine = w.unit_ids(self.id)
        need = max(HUNT_MIN, self.hunt_need - round(3 * self.lean[R.DRAGON]))   # 설원 부족은 조금 작은 사냥대로도 나선다
        if len(mine) < need + 4:                              # 집을 지킬 병사는 남긴다
            return idle
        here = comp[u.y[mine].astype(int), u.x[mine].astype(int)] == hc
        if self.drive and harbor:                             # 드래곤 의지: 다른 땅의 병력도 배로 불러 모은다
            here = here | ~u.aboard[mine]
        pool = mine[here & (u.state[mine] != BUILD) & (u.state[mine] != TAME) & ~w.k_fly[u.kind[mine]]]
        d_home = np.hypot(u.y[pool] - home[0], u.x[pool] - home[1])
        if not self.drive:                                    # 드래곤 의지가 있으면 나가 있는 병력도 불러 모은다
            pool = pool[(d_home < 50) | (u.state[pool] == IDLE)]
        ranged = w.k_ranged[u.kind[pool]]
        if len(pool) < need or ranged.sum() < (0 if self.drive else max(4, need // 3)):   # 드래곤 의지면 궁수가 없어도 (목재는 채워 주지 않는다)
            return idle
        d_home = np.hypot(u.y[pool] - home[0], u.x[pool] - home[1])
        mine_r = np.isin(pool, self.reserved)
        order = np.lexsort((d_home, ~ranged, ~mine_r))        # 드래곤 몫 먼저, 그다음 궁수, 그다음 집에서 가까운 순
        party = pool[order[:need]]
        a = min(lairs, key=lambda a: np.hypot(a.hy - home[0], a.hx - home[1]) * (1.0 if comp[int(a.hy), int(a.hx)] == hc else 1.6))
        if comp[int(a.hy), int(a.hx)] == hc:                  # 둥지 앞 (둥지에서 집 쪽으로 26칸)
            dy, dx = home[0] - a.hy, home[1] - a.hx
            n = max(np.hypot(dy, dx), 1e-6)
            r = min(26.0, n)
            ry, rx = a.hy + dy / n * r, a.hx + dx / n * r
            spot = w.fields.snap(ry, rx, 10)
            if spot is None or comp[spot] != hc:
                ry, rx = home
        else:                                                 # 바다 건너: 집에 모여서 함께 배를 탄다
            ry, rx = float(u.y[party].mean()), float(u.x[party].mean())
        self.hunt, self.hunters, self.hunt_phase = a.id, party, 'muster'
        self.hunt_rally = (float(ry), float(rx))
        self.hunt_until = w.time + 45
        w.order_move(party, ry, rx)
        return np.setdiff1d(idle, party)

    def _dragon_hunt(self, w, home):
        """사냥 중인 드래곤: 모이기 → 함께 친다 → 쓰러지면 한 명이 길들인다.
        사냥대가 무너지거나 너무 오래 걸리면 그만두고 (실패) 잠시 뒤 더 크게 다시."""
        u, wild = w.units, w.wild
        a = wild.animals.get(self.hunt)
        hunters = self.hunters
        if a is None:                                        # 길들였거나 (다른 나라가) 가져갔다
            self._end_hunt(w, failed=False)
            return
        if self.hunt_phase == 'muster':
            if len(hunters) < max(4, self.hunt_need // 2):
                self._end_hunt(w, failed=False, home=home)
                return
            ry, rx = self.hunt_rally
            near = np.hypot(u.y[hunters] - ry, u.x[hunters] - rx) < 10
            if near.mean() >= 0.75 or w.time > self.hunt_until:
                self.hunt_phase, self.hunt_until = 'attack', w.time + 150
                if a.mode in (SLEEP, FIGHT):
                    w.order_attack(hunters, unit=a.unit)
            return
        if len(hunters) < max(4, int(self.hunt_need * 0.35)) or w.time > self.hunt_until:
            self._end_hunt(w, failed=True, home=home)
            return
        if a.mode in (SLEEP, FIGHT):                        # 잠들었거나 싸우는 중: 친다 (쉬고 있는 사냥꾼만 다시)
            lazy = hunters[u.state[hunters] == IDLE]
            if len(lazy):
                w.order_attack(lazy, unit=a.unit)
        elif a.mode in (SUBDUED, HELD, TAMING) and not wild.taming(a.id, self.id):   # 쓰러졌다: 한 명이 길들인다 (다른 나라가 길들이는 중이어도)
            self.hunt_until = max(self.hunt_until, w.time + 30)
            if wild.order_tame(self.id, hunters, a.id, quiet=True):
                self.hunt_need = HUNT_PARTY                  # 해냈다: 다음엔 처음 크기로

    def _near_own(self, w, x, y) -> float:
        """(x, y)에서 내 거점이나 내 병사까지 가장 가까운 거리."""
        u, b = w.units, w.builds
        halls = w.building_ids(self.id, R.HALL)
        mine = w.unit_ids(self.id)
        d = 1e9
        if len(halls):
            d = min(d, float(np.min(np.hypot(b.x[halls] - x, b.y[halls] - y))))
        if len(mine):
            d = min(d, float(np.min(np.hypot(u.x[mine] - x, u.y[mine] - y))))
        return d

    def _lean(self, w, home) -> dict:
        """시작 거점 둘레(LEAN_R)의 지형 성향: 설원 → 드래곤, 사막 → 바위거북, 초원 → 말 (0..1).
        부족의 바탕이라 처음 한 번만 정한다 (넓혀 가도 바뀌지 않는다).
        가장 큰 성향은 적어도 LEAN_MIN (어느 지형도 아니면 나라마다 정해진 하나)."""
        if self.lean_at is not None:
            return self.lean
        m = w.map
        y0, y1 = max(int(home[0]) - LEAN_R, 0), min(int(home[0]) + LEAN_R + 1, m.H)
        x0, x1 = max(int(home[1]) - LEAN_R, 0), min(int(home[1]) + LEAN_R + 1, m.W)
        land = max(int(m.land[y0:y1, x0:x1].sum()), 1)
        snow, desert, grass = (int(k[y0:y1, x0:x1].sum()) / land for k in _lean_masks(m))
        lean = {R.DRAGON: min(1.0, snow / 0.25), R.TORTOISE_W: min(1.0, desert / 0.25), R.HORSE: min(1.0, grass / 0.3)}
        top = max(lean, key=lean.get) if max(lean.values()) > 0 else LEAN_KINDS[self.id % len(LEAN_KINDS)]
        lean[top] = max(lean[top], LEAN_MIN)
        if self.id in dragon_tribes(w):                      # 드래곤 부족: 드래곤을 좋아한다
            lean[R.DRAGON] = max(lean[R.DRAGON], 0.8)
        if self.id in tortoise_tribes(w):                    # 거북 부족: 바위거북을 좋아한다
            lean[R.TORTOISE_W] = max(lean[R.TORTOISE_W], 0.8)
        self.lean, self.lean_at = lean, home
        return lean

    def _tame_trip(self, w, idle):
        """바다 건너 길들이러 가는 병사들: 동물이 있는 땅에 내리면 길들이게 한다. 동물이 사라지거나 늦으면 그만."""
        u, wild, comp = w.units, w.wild, w.map.comp
        aid, ids, until = self.trip
        ids = ids[u.alive[ids] & (u.own[ids] == self.id)]
        a = wild.animals.get(aid)
        if a is None or not len(ids) or w.time > until or wild.taming(aid, self.id):
            self.trip, self.trip_at = None, w.time + 50
            return idle
        landed = ids[~u.aboard[ids] & (comp[u.y[ids].astype(int), u.x[ids].astype(int)] == comp[int(a.y), int(a.x)])]
        if len(landed) and wild.order_tame(self.id, landed, aid, quiet=True):
            self.trip, self.trip_at = None, w.time + 50
            return idle
        self.trip = (aid, ids, until)
        return np.setdiff1d(idle, ids)

    def _tame(self, w, idle, home, nat):
        """말·바위거북 중 거점이나 내 병사에서 가장 가까운 것을 길들인다 (바다 건너는 항구가 있을 때, 조금 멀게 친다).
        먹이가 드는 동물(바위거북)이 가장 가까운데 식량이 모자라면 훈련을 줄여 모으면서, 그동안은 그다음 것을."""
        if self.trip is not None:
            return idle
        u, comp, wild = w.units, w.map.comp, w.wild
        hc = comp[int(home[0]), int(home[1])]
        harbor = bool(w.fleet.harbors_on(self.id, hc))
        cands = []
        for a in wild.animals.values():
            if a.unit >= 0 or wild.taming(a.id, self.id):
                continue
            far = comp[int(a.y), int(a.x)] != hc
            if far and (not harbor or w.time < self.trip_at):
                continue
            pref = 1.0 - 0.5 * self.lean.get(a.kind, 0.0)   # 좋아하는 동물은 조금 멀어도 고른다
            cands.append((self._near_own(w, a.x, a.y) * (1.6 if far else 1.0) * pref + (40 if far else 0), far, a))
        if not cands:
            return idle
        cands.sort(key=lambda c: c[0])
        for k, (_, far, a) in enumerate(cands):
            food = R.WILDLIFE[a.kind].get('food', 0)
            if food and nat.res[R.FOOD] < food:              # 먹이가 모자라다: 모으기 시작하고 (최대 120초) 다음 것을
                if k == 0 and not self.saving and nat.rate[R.FOOD] >= 2.0:   # 곧 모일 때만 (훈련을 오래 막지 않게)
                    self.saving, self.saving_until = float(food), w.time + 60 + 60 * self.lean.get(a.kind, 0.0)
                continue
            ok = idle[np.isin(u.kind[idle], list(R.tamers_of(R.WILDLIFE[a.kind])))]
            ok = ok[comp[u.y[ok].astype(int), u.x[ok].astype(int)] == hc] if far else ok
            pick = self._nearest(w, ok, a.y, a.x, 3) if len(ok) else ok
            if not len(pick):
                break
            if far:                                           # 바다 건너: 배로 보내고, 내리면 길들인다
                if w.order_move(pick, float(a.y), float(a.x)):
                    self.trip = (a.id, pick, w.time + 150)
                    idle = np.setdiff1d(idle, pick)
            else:
                n = wild.order_tame(self.id, pick, a.id, quiet=True)
                if n:
                    idle = np.setdiff1d(idle, pick)
                    if food:                                  # 먹이는 다 길들였을 때 낸다: 그때까지 훈련이 써 버리지 않게
                        self.saving, self.saving_until = float(food * n), w.time + 60
            break
        return idle

    def _tort_drive(self, w) -> bool:
        """거북 의지: 거북 부족이 자랐고 거북이 TORT_MAX마리보다 적고 다음 차례가 됐나."""
        if w.time < max(TORT_TIME, self.tort_next) or self.id not in tortoise_tribes(w):
            return False
        if len(w.building_ids(self.id)) < TORT_BUILDS:
            return False
        mine = w.unit_ids(self.id)
        return int((w.units.kind[mine] == R.TORTOISE).sum()) < TORT_MAX

    def _tame_tortoise(self, w, idle, home, nat):
        """같은 섬의 가장 가까운 거북을 하나 길들이러 보낸다. 먹이가 모자라면 채워 준다 (TORT_GIFT까지)."""
        u, comp, wild = w.units, w.map.comp, w.wild
        hc = comp[int(home[0]), int(home[1])]
        cands = [a for a in wild.animals.values() if a.kind == R.TORTOISE_W and comp[int(a.y), int(a.x)] == hc
                 and not wild.taming(a.id, self.id)]
        ok = idle[comp[u.y[idle].astype(int), u.x[idle].astype(int)] == hc]
        if not cands or not len(ok):
            return idle
        a = min(cands, key=lambda a: self._near_own(w, a.x, a.y))
        food = float(R.WILDLIFE[R.TORTOISE_W]['food'])
        give = max(0.0, food - nat.res[R.FOOD])
        if give > TORT_GIFT - self.tort_given:
            return idle
        nat.res[R.FOOD] += give
        pick = self._nearest(w, ok, a.y, a.x, 1)
        if wild.order_tame(self.id, pick, a.id, quiet=True):
            self.tort_given += give
            self.tort_next = w.time + TORT_EVERY
            self.saving, self.saving_until = food, w.time + 60   # 길들일 때까지 먹이를 남겨 둔다
            return np.setdiff1d(idle, pick)
        nat.res[R.FOOD] -= give                                  # 못 보냈다: 도로 거둔다
        return idle

    def _pick_site(self, w, nat, home):
        u = w.units
        foes = np.flatnonzero(u.alive[:u.n] & (w.diplo.friend[self.id, u.own[:u.n]] == 0))
        pits = len(w.building_ids(self.id, R.SULFUR_PIT))
        fires = len(w.building_ids(self.id, R.FIRE_TOWER))
        sul = (1.2 if self.intel['riders'] else 0.8) if pits == 0 else (0.4 if self.intel['riders'] else 0.0)   # 화염탑 연료: 채취장 하나는 꼭
        res = nat.res
        need = np.array([nat.rate[R.FOOD] < 0.5, res[R.WOOD] < 120 + self.reserve[R.WOOD],
                         res[R.STONE] < 60 + self.reserve[R.STONE] or ((self.intel['riders'] or fires == 0) and res[R.STONE] < 120), sul], float)
        for k, o in ((R.WOOD, R.STONE), (R.STONE, R.WOOD)):        # 하나만 쌓이고 다른 하나가 모자라면
            if res[o] > nat.caps[o] * 0.6 and res[k] < res[o] * 0.3:
                need[k] += 1.0
            if res[k] > nat.caps[k] * 0.9:
                need[k] -= 0.75                                      # 쌓여 있으면 그 자원지는 훨씬 덜 (거리 4배로 친다)
        if res[R.FOOD] > nat.caps[R.FOOD] * 0.9:
            need[R.FOOD] -= 0.75
        elif res[R.FOOD] < 150 and nat.rate[R.FOOD] < 3.0 and (res[R.WOOD] > nat.caps[R.WOOD] * 0.6 or res[R.STONE] > nat.caps[R.STONE] * 0.6):
            need[R.FOOD] += 1.0                                      # 목재·석재는 남는데 식량이 모자라다
        if not len(w.building_ids(self.id, R.FARM)):                # 농장이 없으면 농장부터
            need[R.FOOD] += 2.0
        best, bs = None, 1e9
        comp = w.map.comp
        hy, hx = int(home[0]), int(home[1])
        harbor = bool(w.fleet.harbors_on(self.id, comp[hy, hx]))      # 바다 건너는 이 땅에 항구가 있어야
        for s in w.sites:
            if s.building >= 0:
                continue
            far = comp[s.y, s.x] != comp[hy, hx]
            if far and not harbor:                   # 바다 건너는 항구가 있어야
                continue
            cost = R.BUILD_STATS[R.SITE_BUILDING[s.kind]]['cost']      # (유황 채취장도 목재만)
            if not (self._spare(w, cost) or (need[R.SITE_RES[s.kind]] >= 1 and w.can_afford(self.id, cost))):   # 남겨 둔 몫은 모자란 자원지에만
                continue
            if len(foes) and np.min(np.hypot(u.x[foes] - s.x, u.y[foes] - s.y)) < 18:
                continue
            d = np.hypot(s.y - home[0], s.x - home[1]) / (s.rich * (1 + need[R.SITE_RES[s.kind]])) * (1.8 if far else 1.0)
            if d < bs:
                best, bs = s, d
        return best

    def _overseas(self, w, home) -> bool:
        """바다 건너에 노릴 것이 있나 (빈 자원지, 또는 걸어서 갈 수 있는 적 건물이 없을 때 다른 땅의 적)."""
        comp = w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        if any(s.building < 0 and comp[s.y, s.x] != hc for s in w.sites):
            return True
        b = w.builds
        foes = np.flatnonzero(b.alive[:b.n] & (w.diplo.friend[self.id, b.own[:b.n]] == 0))
        wild = w.wild                                # 드래곤을 좋아하는 나라: 바다 건너 둥지도
        if self.lean[R.DRAGON] >= 0.5 and wild.riders(self.id, R.DRAGON) < R.WILDLIFE[R.DRAGON]['limit'] and any(
                a.unit >= 0 and comp[int(a.hy), int(a.hx)] != hc for a in wild.animals.values()):
            return True
        if len(foes) == 0:
            return False
        same = comp[b.y[foes].astype(int), b.x[foes].astype(int)] == hc
        return not same.any()

    def _harbor_near(self, w, p):
        for r in range(2, 26, 2):
            for a in self.rng.permutation(np.linspace(0, 2 * np.pi, 24, endpoint=False)):
                y, x = int(p[0] + np.sin(a) * r), int(p[1] + np.cos(a) * r)
                if w.fleet.can_place_harbor(y, x) and w.map.comp[y, x] == w.map.comp[p[0], p[1]]:
                    return y, x
        return None

    def _harbors_home(self, w, home) -> list:
        """본거지 땅 위의 내 항구 (짓는 중 포함)."""
        b, comp = w.builds, w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        return [h for h in w.building_ids(self.id, R.HARBOR) if comp[int(b.y[h]), int(b.x[h])] == hc]

    def _harbor_spot(self, w, home):
        """본거지 땅의 내 건물 둘레 해안."""
        b, comp = w.builds, w.map.comp
        hc = comp[int(home[0]), int(home[1])]
        own = [i for i in w.building_ids(self.id, done=True) if comp[int(b.y[i]), int(b.x[i])] == hc]
        if not own:
            return None
        for _ in range(4):
            c = int(self.rng.choice(own))
            for _ in range(80):
                a, r = self.rng.uniform(0, 2 * np.pi), self.rng.uniform(6, 30)
                y, x = int(b.y[c] + np.sin(a) * r), int(b.x[c] + np.cos(a) * r)
                if w.fleet.can_place_harbor(y, x) and comp[y, x] == hc:
                    return y, x
        return None

    # ------------------------------------------------------------- 외교
    def _strength(self, w, nid) -> float:
        u = w.units
        m = u.alive[:u.n] & (u.own[:u.n] == nid)
        return float(m.sum()) + 1.0

    def _accepts(self, w, other) -> bool:
        """other의 동맹 요청을 받을까."""
        d, me = w.diplo, self.id
        if d.traitor(other) and self.rng.random() < 0.9:                  # 배신자는 거의 거절
            return False
        if d.level(me, other) <= 1:                                        # 경계·적대
            return self.rng.random() < 0.05
        if len(d.allies_of(me)) >= (1 if self.social < 0.5 else 2):
            return False
        if d.level(me, other) == 3:                                        # 우호
            return self.rng.random() < 0.9
        afraid = self._strength(w, other) > self._strength(w, me) * 1.8    # 훨씬 강한 나라: 겁나서 받기 쉽다
        return self.rng.random() < (0.35 + 0.4 * self.social + (0.3 if afraid else 0.0))

    def _diplomacy(self, w, nat, mine) -> None:
        d, me, rng = w.diplo, self.id, self.rng
        # 1. 들어온 요청에 답한다
        for (a, b) in list(d.requests):
            if b == me and w.time - d.requests[(a, b)] > 2.0:
                d.reply(me, a, self._accepts(w, a))
        allies = d.allies_of(me)
        # 2. 연장 · 배신
        for o in allies:
            al = d.allies[d.key(me, o)]
            near_end = al['until'] - w.time <= 40.0
            if d.traitor(o) and rng.random() < 0.5:                           # 배신자인 동맹은 깬다
                d.end(me, o, betray=True)
                continue
            if near_end and me not in al['ext'] and d.level(me, o) >= 1:
                d.extend(me, o)
            home, oh = self._home(w), self._home_of(w, o)
            same = home is not None and oh is not None and w.map.comp[int(home[0]), int(home[1])] == w.map.comp[int(oh[0]), int(oh[1])]
            if same and self._strength(w, me) > self._strength(w, o) * 3.0 and rng.random() < 0.02 * self.aggression:
                d.end(me, o, betray=True)                                       # 이웃 동맹이 훨씬 약하다: 가끔 배신
        allies = d.allies_of(me)
        # 3. 공격 받으면 그 나라를 동맹들에게 공격 요청한다
        if allies and me not in d.targets and d.target_cd[me] <= w.time:
            worst = int(np.argmin(d.rel[me]))
            if worst != me and d.rel[me, worst] < -60 and not d.allied(me, worst) and w.nations[worst].alive and rng.random() < 0.3:
                d.target(me, worst)
        # 동맹이 공격을 요청했다: 관계가 경계 이상이면 한동안 그 나라를 먼저 친다
        for o in allies:
            tg = d.targets.get(o)
            if tg and tg[0] != me and d.level(me, o) >= 1 and (self.focus is None or self.focus[1] <= w.time):
                self.focus = (tg[0], tg[1])
        # 4. 넉넉하면 우호인 동맹에게 자원을 조금
        rich = [0.15 if nat.res[k] > nat.caps[k] * 0.9 else 0.0 for k in range(3)]               # 넉넉한 자원만 15%
        if allies and any(rich) and d.donate_cd[me] <= w.time and rng.random() < 0.15:
            o = max(allies, key=lambda o: d.rel[me, o])
            if d.level(me, o) == 3:
                d.give_res(me, o, rich)
        # 5. 가끔 동맹을 청한다: 관계가 좋거나 같은 적과 싸우는 나라에게 (사람에게도)
        if w.time >= self.ask_at:
            self.ask_at = w.time + rng.uniform(60, 140) / (0.5 + self.social)
            if len(allies) < (1 if self.social < 0.5 else 2):
                cands = []
                for o in range(d.n):
                    if o == me or not w.nations[o].alive or d.can_request(me, o) is not None:
                        continue
                    if d.level(me, o) <= 1 or d.traitor(o):
                        continue
                    common = bool(((d.rel[me] < -40) & (d.rel[o] < -40)).any())   # 둘 다 미워하는 나라가 있다
                    score = d.rel[me, o] + (40 if common else 0) + rng.uniform(0, 30)
                    cands.append((score, o))
                if cands:
                    score, o = max(cands)
                    if score > 20 or rng.random() < 0.3 * self.social:
                        d.request(me, o)

    def _home_of(self, w, nid):
        own = w.building_ids(nid)
        if not len(own):
            return None
        b = w.builds
        return float(b.y[own].mean()), float(b.x[own].mean())

    def _attack(self, w, ids) -> None:
        b = w.builds
        foes = np.flatnonzero(b.alive[:b.n] & (w.diplo.friend[self.id, b.own[:b.n]] == 0))
        if len(foes) == 0:
            return
        cy, cx = w.units.y[ids].mean(), w.units.x[ids].mean()
        comp = w.map.comp
        same = comp[b.y[foes].astype(int), b.x[foes].astype(int)] == comp[int(cy), int(cx)]
        if same.any():
            foes = foes[same]
        d = np.hypot(b.x[foes] - cx, b.y[foes] - cy) * np.where(b.kind[foes] == R.HALL, 0.75, 1.0)   # 거점을 잃으면 멸망: 조금 멀어도 거점을
        dp, own = w.diplo, b.own[foes]
        real = own < dp.n
        rel = np.where(real, dp.rel[self.id, np.minimum(own, dp.n - 1)], 0.0)
        d = d * np.where(rel < -50, 0.6, np.where(rel < 0, 0.85, 1.0))                  # 적대하는 나라를 먼저
        trading = np.array([w.trade.status(self.id, int(o)) == 'on' if o < dp.n else False for o in own])
        d = d * np.where(trading, TRADE_PEACE, 1.0)                                     # 무역하는 나라는 덜 친다
        if self.focus is not None and self.focus[1] > w.time:
            d = d * np.where(own == self.focus[0], 0.4, 1.0)                           # 동맹이 공격을 요청한 나라는 더 먼저
        t = foes[int(np.argmin(d))]
        w.order_move(ids, float(b.y[t]), float(b.x[t]), attack=True)
