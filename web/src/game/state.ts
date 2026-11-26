// 브라우저 쪽 게임 상태: 서버가 보낸 '바뀐 것만'을 쌓아 지금 세계를 맞춰 가고, 두 상태 사이를 보간해 부드럽게 그린다.
// 보간: 상태가 오면 '지금 화면에 그리고 있는 위치'에서 새 위치까지, 다음 상태가 올 때쯤 닿도록 섞는다.
// 도착 시각은 걸음 간격에 맞춰 부드럽게 따라가므로 (sched), 상태가 들쭉날쭉 와도 끊기거나 튀지 않는다.
// 순간 이동(배에서 내림, 새로 생김)은 섞지 않는다.

import type { AnimalRec, BoatRec, BuildRec, CaravanRec, NationRec, ShotRec, StateMsg, UnitRec } from './protocol.ts';
import type { DiploState } from './diplomacy.ts';

export interface Unit extends UnitRec { px: number; py: number }
export interface Boat extends BoatRec { px: number; py: number }
export interface Caravan extends CaravanRec { px: number; py: number }
export interface Animal extends AnimalRec { px: number; py: number }
export interface Shot extends ShotRec { t0: number }

export interface StartInfo {
  map: string; H: number; W: number; round: number; tick_hz: number; me: number;
  nations: { id: number; name: string; color: number[]; light: number[]; tribe?: number }[];   // tribe: sim/tribes.py (0 온대, 1 설원, 2 사막)
  sites: { id: number; kind: number; x: number; y: number; rich: number; cold?: number; snow?: boolean }[];
  lairs?: number[][];                  // 드래곤 둥지 [y, x]
  year_length: number; day_length: number;
  rules: any;
  sid?: string; token?: string; resumed?: boolean;   // 다시 접속할 때 쓰는 판 번호·내 자리 표, 다시 접속해서 받은 start인가
  humans?: number;                     // 사람 수 (2 이상: 멀티)
  room?: boolean;                      // 방에서 시작한 판 (끝나면 대기실로 돌아갈 수 있다)
  tutorial?: boolean;                  // 튜토리얼 판 (game/tutorial.ts가 단계 안내를 띄운다)
  dev?: boolean;                       // 서버가 --dev로 켜졌다 (개발용 콘솔)
}

const SNAP = 4;                 // 이보다 멀리 한 번에 움직이면 보간하지 않는다 (칸)

export class GameState {
  info: StartInfo;
  units = new Map<number, Unit>();
  builds = new Map<number, BuildRec>();
  boats = new Map<number, Boat>();
  caravans = new Map<number, Caravan>();   // 무역 행렬의 구성원 (행렬 번호 × 8 + 구성원 번호 → 구성원, 걸음마다 모두 온다)
  animals = new Map<number, Animal>();     // 야생 동물 (번호 → 동물)
  shots: Shot[] = [];
  nations: NationRec[] = [];
  messages: { text: string; t: number; from?: number }[] = [];   // 왼쪽 아래 알림 줄 (from: 대화를 보낸 나라)
  chatLog: { from: number; text: string }[] = [];              // 대화 기록 (모바일 대화창, 최근 CHAT_LOG줄)
  time = 0;
  hour = 12;
  year = 0;
  flags = 0;
  speed = 1;
  simMs = 0;
  tick = 0;
  lastAt = 0;                   // 마지막 상태가 도착한 시각 (performance.now)
  period: number;               // 걸음 간격 (ms)
  private sched = 0;            // 걸음 간격에 맞춰 부드럽게 따라가는 도착 시각
  private segStart = 0;         // 지금 보간 구간의 시작 시각
  private segSpan = 50;         // 지금 보간 구간의 길이 (다음 상태가 올 때쯤까지)
  over: string | null = null;
  diplo: DiploState | null = null;   // 외교 (서버가 바뀔 때마다 보낸다)
  seats: { away: number[]; gone: number[] } = { away: [], gone: [] };   // 사람 나라의 접속 상태 (끊겨 기다리는 중, 떠남)

  constructor(info: StartInfo) {
    this.info = info;
    this.period = 1000 / info.tick_hz;
  }

  get paused() { return (this.flags & 1) !== 0; }
  get ended() { return (this.flags & 2) !== 0; }

  apply(m: StateMsg, now: number) {
    const a = this.alpha(now);                          // 지금 그리고 있는 위치에서 이어서
    for (const u of this.units.values()) { u.px += (u.x - u.px) * a; u.py += (u.y - u.py) * a; }
    for (const b of this.boats.values()) { b.px += (b.x - b.px) * a; b.py += (b.y - b.py) * a; }
    for (const b of this.caravans.values()) { b.px += (b.x - b.px) * a; b.py += (b.y - b.py) * a; }
    for (const b of this.animals.values()) { b.px += (b.x - b.px) * a; b.py += (b.y - b.py) * a; }
    for (const r of m.units) {
      const old = this.units.get(r.slot);
      const keep = old && old.gen === r.gen && Math.hypot(old.px - r.x, old.py - r.y) < SNAP;
      this.units.set(r.slot, { ...r, px: keep ? old!.px : r.x, py: keep ? old!.py : r.y });
    }
    for (const s of m.unitsGone) this.units.delete(s);
    for (const r of m.builds) this.builds.set(r.slot, r);
    for (const s of m.buildsGone) this.builds.delete(s);
    const seen = new Set<number>();
    for (const r of m.boats) {
      seen.add(r.id);
      const old = this.boats.get(r.id);
      const keep = old && Math.hypot(old.px - r.x, old.py - r.y) < SNAP;
      this.boats.set(r.id, { ...r, px: keep ? old!.px : r.x, py: keep ? old!.py : r.y });
    }
    for (const id of [...this.boats.keys()]) if (!seen.has(id)) this.boats.delete(id);
    const cseen = new Set<number>();
    for (const r of m.caravans) {
      const key = r.id * 8 + r.idx;
      cseen.add(key);
      const old = this.caravans.get(key);
      const keep = old && old.sea === r.sea && Math.hypot(old.px - r.x, old.py - r.y) < SNAP;
      this.caravans.set(key, { ...r, px: keep ? old!.px : r.x, py: keep ? old!.py : r.y });
    }
    for (const id of [...this.caravans.keys()]) if (!cseen.has(id)) this.caravans.delete(id);
    for (const r of m.animals) {
      const old = this.animals.get(r.id);
      const keep = old && Math.hypot(old.px - r.x, old.py - r.y) < SNAP;
      this.animals.set(r.id, { ...r, px: keep ? old!.px : r.x, py: keep ? old!.py : r.y });
    }
    for (const id of m.animalsGone) this.animals.delete(id);
    for (const s of m.shots) this.shots.push({ ...s, t0: m.time });
    this.shots = this.shots.filter((s) => m.time - s.t0 <= 0.3);
    if (m.nations) this.nations = m.nations;
    this.time = m.time; this.hour = m.hour; this.year = m.year; this.flags = m.flags; this.speed = m.speed;
    this.simMs = m.simMs; this.tick = m.tick;
    this.lastAt = now;
    // 도착 시각: 걸음 간격대로 오면 그 일정을 따르고 (흔들림은 조금씩만 반영), 크게 어긋나면 새로 맞춘다
    const exp = this.sched + this.period;
    this.sched = this.sched && Math.abs(now - exp) < this.period ? exp + (now - exp) * 0.1 : now;
    this.segStart = now;
    this.segSpan = Math.min(Math.max(this.sched + this.period - now, this.period * 0.5), this.period * 1.5);
  }

  /** 보간 비율 (0 = 상태가 왔을 때 그리던 위치, 1 = 새 상태). */
  alpha(now: number) { return Math.min(Math.max((now - this.segStart) / this.segSpan, 0), 1); }

  /** 화면에 그릴 게임 시각 (상태 사이도 부드럽게). */
  smoothTime(now: number) { return this.time + (this.paused || this.ended ? 0 : (this.alpha(now) - 1) * this.period / 1000 * this.speed); }

  /** 내 거점 등 건물 하나의 site 점유: 자원지 번호 → 건물. */
  siteTaken(): Set<number> {
    const s = new Set<number>();
    for (const b of this.builds.values()) if (b.site >= 0) s.add(b.site);
    return s;
  }

  say(text: string) { this.messages.push({ text, t: this.time }); if (this.messages.length > 8) this.messages.shift(); }

  /** 대화 한 줄: 알림 줄에도, 기록에도. */
  chatSay(from: number, text: string) {
    this.messages.push({ text, t: this.time, from });
    if (this.messages.length > 8) this.messages.shift();
    this.chatLog.push({ from, text });
    if (this.chatLog.length > 60) this.chatLog.shift();
  }
}

export function lerp(a: number, b: number, t: number) { return a + (b - a) * t; }
