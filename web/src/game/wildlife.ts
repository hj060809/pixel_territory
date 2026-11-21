// 야생 동물 그리기 (규칙과 움직임은 서버 sim/wildlife.py, 위치는 상태 사이를 보간).
// 풀 뜯기·거닐기·달아나기 그림, 길들이는 중에는 앞발을 들었다 놓으며 흙먼지가 일고, 머리 위에 진행 막대.
// 길들이러 오는 병사를 기다리는 동물은 발밑에 작은 표시. 멀리서는 작은 그림으로만.

import type { Light, StackRenderer } from './stack.ts';
import { type Animal, type GameState, lerp } from './state.ts';

export const A_GRAZE = 0, A_WALK = 1, A_FLEE = 2, A_HELD = 3, A_TAMING = 4;     // 동물 상태 (서버와 같은 번호)
const NAMES = ['horse'] as const;                                               // 동물 종류 → 모델 (rules.WILDLIFE 순서)
const ang = new Map<number, number>();                                           // 동물이 보는 방향 (라디안)
const DIRS = 16, TAU = Math.PI * 2;

export interface AnimalSpot { an: Animal; x: number; y: number }

/** 화면 위치 (보간). */
export function animalSpots(st: GameState, a: number, sx: (x: number) => number, sy: (y: number) => number): AnimalSpot[] {
  return [...st.animals.values()].map((an) => ({ an, x: sx(lerp(an.px, an.x, a)), y: sy(lerp(an.py, an.y, a)) }));
}

/** 동물 그리기 (스프라이트 스태킹, 가는 쪽을 본다). k: 그림 한 점의 화면 크기. torch: 그 자리의 횃불 빛.
 *  반환: 진행 막대를 그릴 자리 (병사 위에 나중에 그리려고). */
export function drawAnimals(g: CanvasRenderingContext2D, stack: StackRenderer, L: Light, spots: AnimalSpot[], k: number,
                            t: number, W: number, H: number, dt: number, torch: (x: number, y: number) => number):
                            { x: number; y: number; w: number; prog: number }[] {
  const bars: { x: number; y: number; w: number; prog: number }[] = [];
  const list = spots.filter((p) => p.x > -30 && p.x < W + 30 && p.y > -30 && p.y < H + 30).sort((p, q) => p.y - q.y);
  for (const { an, x, y } of list) {
    const seed = (an.id * 0.618) % 1 * 10;
    let frame = 0, hop = 0;
    if (an.state === A_TAMING) {                              // 앞발을 들었다 놓는다 (점점 덜)
      const calm = an.prog;
      const ph = (t * (2.2 - calm) + seed) % 1;
      frame = ph < 0.45 - 0.3 * calm ? 3 : 0;
      hop = frame === 3 ? 1 : 0;
    } else if (an.state === A_GRAZE) frame = Math.sin(t * 0.8 + seed) > -0.2 ? 2 : 0;
    else if (an.state === A_FLEE) frame = Math.trunc(t * 8 + seed) % 2;
    else if (an.state === A_WALK) frame = Math.trunc(t * 3 + seed) % 2 ? 1 : 0;
    let a = ang.get(an.id) ?? (an.dir < 0 ? Math.PI : 0);    // 가는 쪽 (길들이는 중엔 병사 쪽)
    const mx = an.x - an.px, my = an.y - an.py;
    if (an.state === A_TAMING || an.state === A_HELD) a = turnTo(a, an.dir < 0 ? Math.PI : 0, dt * 6);
    else if (Math.hypot(mx, my) > 0.005) a = turnTo(a, Math.atan2(my, mx), dt * 6);
    ang.set(an.id, a);
    const dir = ((Math.round(a / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
    const rc = stack.draw(g, NAMES[an.kind] ?? 'horse', 0, L, x, y - hop * k, k, { frame, dir, torch: torch(an.x, an.y) });
    const img = { width: rc.w, height: rc.h }, rx = rc.x, ry = rc.y;
    if (an.state === A_HELD || an.state === A_TAMING) {      // 발밑 표시: 누군가 길들이는 동물
      g.fillStyle = 'rgba(255,236,170,0.75)';
      g.fillRect(rx + k, Math.round(y + 2 * k), img.width - 2 * k, Math.max(1, k >> 1));
    }
    if (an.state === A_TAMING) {
      if (frame === 0 && k > 1) {                              // 내려놓을 때 흙먼지
        g.fillStyle = 'rgba(214,196,150,0.85)';
        const fx = an.dir < 0 ? rx + k : rx + img.width - 2 * k;
        g.fillRect(fx - k, Math.round(y), k, k); g.fillRect(fx + k, Math.round(y) - k, k, k);
      }
      bars.push({ x: rx + img.width / 2, y: ry - 4, w: Math.max(img.width, 14), prog: an.prog });
    }
  }
  return bars;
}

function turnTo(a: number, b: number, f: number) {
  let d = (b - a) % TAU;
  if (d > Math.PI) d -= TAU;
  if (d < -Math.PI) d += TAU;
  return a + d * Math.min(f, 1);
}

/** 지도 (x, y) 가까이의 동물 (r칸 안, 그림 가운데 기준). */
export function animalAt(st: GameState, x: number, y: number, r: number): Animal | null {
  let best: Animal | null = null, bd = r;
  for (const an of st.animals.values()) {
    const d = Math.hypot(an.x - x, an.y - 0.4 - y);
    if (d < bd) { bd = d; best = an; }
  }
  return best;
}
