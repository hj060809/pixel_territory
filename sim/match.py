"""한 판: 세계(World) + 나라마다 조종자. 게임은 나라만 알고, 누가 조종하는지는 여기서 정한다.

조종자
- 사람: humans에 든 나라. 명령은 바깥(서버의 자리 Seat)이 sim/commands.py로 넣는다. 여기서는 접속 상태만 안다.
- AI: 나머지 나라. sim/ai.py의 Bot이 돌아가며 생각한다 (0.5초를 AI 수로 나눠 걸음마다 하나씩: 길찾기 계산이 한 걸음에 몰리지 않게).
  AI 나라의 자원 수입에는 난이도 배율이 붙는다 (rules.DIFFICULTY).
- 조종자 없음: 접속이 끊겨 떠난 (또는 메뉴에서 나간) 사람의 나라 (gone). 병사·건물은 그대로, 새 명령은 없다 (AI가 맡지 않는다).
- 항복: 그 나라를 모두 허문다 (망한 나라 → 관전).

판 끝: 게임(World)이 정한다 — 나라가 하나만 남으면 (사람이든 AI든, 동맹이든 아니든. 조종자 없는 나라는 세지 않는다).
여기서는 사람 나라마다 결과만 매긴다: 남은 나라면 승리, 망했거나 남지 못했으면 패배.
진 사람은 판이 끝날 때까지 관전한다 (lost). 사람이 모두 나가면 판은 서버에서 지운다 (server/app.py).
"""
from __future__ import annotations

from sim import rules as R


class Match:
    def __init__(self, world, humans=(), difficulty: float = 1.0):
        from sim.ai import Bot
        self.w = world
        self.humans = set(int(h) for h in humans)          # 사람이 조종하는 나라
        self.gone: set[int] = set()                        # 떠난 사람 (조종자 없음)
        self.lost: set[int] = set()                        # 진 사람 (관전)
        self.n_humans = len(self.humans)
        self.bots = {}
        for nat in world.nations:
            if nat.id not in self.humans:
                nat.bonus = difficulty
                self.bots[nat.id] = Bot(nat.id, world.rng, difficulty)
        self._order = sorted(self.bots)
        from sim.ai import set_ai_nations
        set_ai_nations(world, self.bots)              # 드래곤·거북 부족은 AI 나라 중에서
        self._acc = 0.0
        self._turn = 0
        self.over = False
        self.result: dict[int, str] = {}                  # 사람 나라 → '승리' | '패배'
        world.on_tick = self._bots_turn

    # ------------------------------------------------------------- 조종자
    def _bots_turn(self, dt: float) -> None:
        if not self._order:
            return
        self._acc += dt
        gap = 0.5 / len(self._order)
        if self._acc >= gap - 1e-9:
            self._acc -= gap
            self.bots[self._order[self._turn % len(self._order)]].maybe_think(self.w, 0.5)
            self._turn += 1

    def leave(self, nid: int, chose: bool = False) -> None:
        """사람이 떠났다 (끊긴 뒤 오래 안 옴, chose: 메뉴에서 스스로 나감): 조종자 없음. 알림은 모두에게."""
        if nid in self.humans and nid not in self.gone and self.w.nations[nid].alive:
            self.gone.add(nid)
            self.w.nations[nid].idle = True
            name = self.w.nations[nid].name
            self.w.say(f'{R.josa(name, "이", "가")} 판을 떠났습니다 (남은 병사·건물은 그대로입니다)' if chose
                       else f'{name}의 접속이 끊겼습니다 (남은 병사·건물은 그대로입니다)')

    def surrender(self, nid: int) -> None:
        """항복: 그 나라의 병사·건물·배를 모두 허문다 (다음 걸음에 망한 나라 → 관전)."""
        nat = self.w.nations[nid]
        if nid in self.humans and nat.alive and not self.over:
            self.w.say(f'{R.josa(nat.name, "이", "가")} 항복했습니다', skip=(nid,))
            self.w.ruin(nid)

    def back(self, nid: int) -> None:
        """떠났던 사람이 돌아왔다 (판이 끝나기 전): 다시 조종한다."""
        if nid in self.gone:
            self.gone.discard(nid)
            self.w.nations[nid].idle = False
            self.w.say(f'{R.josa(self.w.nations[nid].name, "이", "가")} 돌아왔습니다')

    # ------------------------------------------------------------- 진행
    def update(self, dt: float, season_w=None) -> None:
        self.w.update(dt, season_w)
        if not self.over:
            self._check()

    def _check(self) -> None:
        w = self.w
        for h in self.humans:                              # 진 사람은 관전으로
            if h not in self.lost and not w.nations[h].alive:
                self.lost.add(h)
                self.result[h] = '패배'
        if w.phase != 'over':
            return
        self.over = True
        for h in self.humans:
            self.result.setdefault(h, '승리' if h == w.winner else '패배')
