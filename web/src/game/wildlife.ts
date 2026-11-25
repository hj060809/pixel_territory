// 야생 동물 그리기 (규칙과 움직임은 서버 sim/wildlife.py, 위치는 상태 사이를 보간).
// 말: 풀 뜯기·거닐기·달아나기 그림, 길들이는 중에는 앞발을 들었다 놓으며 흙먼지가 일고, 머리 위에 진행 막대.
// 드래곤 (사나운 동물): 둥지에서 잠 → 깨어 싸움 (숨결을 뿜을 때 입을 벌린다, 체력 막대) → 쓰러짐 (남은 시간 막대,
// 길들이는 중이면 진행 막대). 길들이러 오는 병사를 기다리는 동물은 발밑에 작은 표시.

import { type Light, type StackRenderer, modelPoint } from './stack.ts';
import { BREATH_REACH, DRAGON_MOUTH, DRAGON_SIZE } from './models.ts';
import { type Animal, type GameState, lerp } from './state.ts';

export const A_GRAZE = 0, A_WALK = 1, A_FLEE = 2, A_HELD = 3, A_TAMING = 4;     // 동물 상태 (서버와 같은 번호)
export const A_SLEEP = 5, A_FIGHT = 6, A_SUBDUED = 7;                           // 사나운 동물
const NAMES = ['horse', 'dragon', 'tortoise'] as const;                                      // 동물 종류 → 모델 (rules.WILDLIFE 순서)
const ang = new Map<number, number>();                                           // 동물이 보는 방향 (라디안)
const DIRS = 16, TAU = Math.PI * 2;

export interface AnimalSpot { an: Animal; x: number; y: number }
export interface AnimalBar { x: number; y: number; w: number; prog: number; col: string; label?: string }

/** 화면 위치 (보간). */
export function animalSpots(st: GameState, a: number, sx: (x: number) => number, sy: (y: number) => number): AnimalSpot[] {
  return [...st.animals.values()].map((an) => ({ an, x: sx(lerp(an.px, an.x, a)), y: sy(lerp(an.py, an.y, a)) }));
}

/** 사나운 동물인가 (드래곤). */
export const isHostile = (R: any, kind: number) => !!R.wildlife?.[kind]?.hostile;

/** 동물 그리기 (스프라이트 스태킹, 가는 쪽을 본다). k0: 그림 한 점의 화면 크기, kBig: 큰 동물(드래곤)의 점 크기 (멀리서 1보다 작게). torch: 그 자리의 횃불 빛.
 *  breathing: 그 자리에서 막 숨결을 뿜었나. 반환: 막대를 그릴 자리 (병사 위에 나중에 그리려고). */
export function drawAnimals(g: CanvasRenderingContext2D, stack: StackRenderer, L: Light, spots: AnimalSpot[], k0: number,
                            kBig: number, t: number, W: number, H: number, dt: number, torch: (x: number, y: number) => number,
                            breathing: (x: number, y: number) => boolean, R: any,
                            mouths?: Map<string, number[]>): AnimalBar[] {
  const bars: AnimalBar[] = [];
  const list = spots.filter((p) => p.x > -120 && p.x < W + 120 && p.y > -120 && p.y < H + 120).sort((p, q) => p.y - q.y);
  for (const { an, x, y } of list) {
    const seed = (an.id * 0.618) % 1 * 10, hostile = isHostile(R, an.kind);
    const k = hostile ? kBig : k0;                            // 큰 동물은 멀리서 땅 넓이에 맞게 줄인다
    let frame = 0, hop = 0;
    if (NAMES[an.kind] === 'tortoise') {                      // 바위거북: 느릿느릿 걷거나 서 있다
      frame = Math.hypot(an.x - an.px, an.y - an.py) > 0.004 ? Math.trunc(t * 2.4 + seed) % 2 : 0;
    } else if (hostile) {
      const moving = Math.hypot(an.x - an.px, an.y - an.py) > 0.01;
      frame = an.state === A_SLEEP ? 3 : an.state !== A_FIGHT ? 4
        : breathing(an.x, an.y) ? 5 : moving ? (Math.trunc(t * 3.2 + seed) % 2 ? 7 : 8) : 0;   // 숨결 / 걷기 / 서기
    } else if (an.state === A_TAMING) {                       // 앞발을 들었다 놓는다 (점점 덜)
      const calm = an.prog;
      const ph = (t * (2.2 - calm) + seed) % 1;
      frame = ph < 0.45 - 0.3 * calm ? 3 : 0;
      hop = frame === 3 ? 1 : 0;
    } else if (an.state === A_GRAZE) frame = Math.sin(t * 0.8 + seed) > -0.2 ? 2 : 0;
    else if (an.state === A_FLEE) frame = Math.trunc(t * 8 + seed) % 2;
    else if (an.state === A_WALK) frame = Math.trunc(t * 3 + seed) % 2 ? 1 : 0;
    let a = ang.get(an.id) ?? (an.dir < 0 ? Math.PI : 0);    // 가는 쪽 (길들이는 중·싸우는 중엔 상대 쪽)
    const mx = an.x - an.px, my = an.y - an.py;
    if (an.state === A_TAMING || an.state === A_HELD || (hostile && an.state === A_FIGHT && Math.hypot(mx, my) < 0.005)) {
      a = turnTo(a, an.dir < 0 ? Math.PI : 0, dt * 4);
    } else if (Math.hypot(mx, my) > 0.005) a = turnTo(a, Math.atan2(my, mx), dt * 6);
    ang.set(an.id, a);
    const dir = ((Math.round(a / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
    g.imageSmoothingEnabled = k < 1;
    const rc = stack.draw(g, NAMES[an.kind] ?? 'horse', 0, L, x, y - hop * k, k, { frame, dir, torch: torch(an.x, an.y) });
    g.imageSmoothingEnabled = false;
    if (hostile && mouths && DRAGON_MOUTH[frame]) {                   // 숨결이 나올 입 자리 (화면)
      const [mx, my, mz] = DRAGON_MOUTH[frame], [dx, dy] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx, my, mz, dir, DIRS, k);
      const [ex, ey] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx + BREATH_REACH, my, 0, dir, DIRS, k);   // 입 앞쪽의 땅
      mouths.set(`a${an.id}`, [x + dx, y - hop * k + dy, x + ex, y + ey]);
    }
    const img = { width: Math.round(rc.w), height: Math.round(rc.h) }, rx = Math.round(rc.x), ry = Math.round(rc.y);
    const kp = Math.max(1, Math.round(k));                   // 작은 표시(발밑·z·흙먼지)는 정수 점으로 (흐려지지 않게)
    if (an.state === A_HELD || an.state === A_TAMING) {      // 발밑 표시: 누군가 길들이는 동물
      g.fillStyle = 'rgba(255,236,170,0.75)';
      g.fillRect(rx + kp, Math.round(y + 2 * kp), img.width - 2 * kp, Math.max(1, kp >> 1));
    }
    if (hostile) {
      if (an.state === A_SLEEP && Math.floor(t * 0.8 + seed) % 2 === 0) {     // 잠: 머리 위로 떠오르는 작은 z
        g.fillStyle = 'rgba(220,236,255,0.8)';
        const zx = Math.round(rx + img.width * 0.7), zy = Math.round(ry - 2 * kp - ((t * 6) % 6) * kp * 0.5);
        g.fillRect(zx, zy, 3 * kp, kp); g.fillRect(zx + kp, zy + kp, kp, kp); g.fillRect(zx, zy + 2 * kp, 3 * kp, kp);
      }
      const w = Math.max(img.width * 0.7, 30), cx = rx + img.width / 2;
      if (an.state === A_FIGHT || (an.state === A_SLEEP && an.hp < 0.99)) bars.push({ x: cx, y: ry - 4, w, prog: an.hp, col: '' });
      else if (an.state !== A_SLEEP) {                        // 쓰러짐: 남은 시간, 길들이는 중이면 진행
        const total = R.wildlife[an.kind].subdue_time || 20;
        bars.push({ x: cx, y: ry - 4, w, prog: an.sub / total, col: 'rgb(150,200,255)', label: `쓰러짐 ${an.sub}초` });
        if (an.state === A_TAMING) bars.push({ x: cx, y: ry + 2, w, prog: an.prog, col: 'rgb(240,200,90)' });
      }
      continue;
    }
    if (an.state === A_TAMING) {
      if (frame === 0 && k > 1) {                              // 내려놓을 때 흙먼지
        g.fillStyle = 'rgba(214,196,150,0.85)';
        const fx = an.dir < 0 ? rx + kp : rx + img.width - 2 * kp;
        g.fillRect(fx - kp, Math.round(y), kp, kp); g.fillRect(fx + kp, Math.round(y) - kp, kp, kp);
      }
      bars.push({ x: rx + img.width / 2, y: ry - 4, w: Math.max(img.width, 14), prog: an.prog, col: 'rgb(240,200,90)' });
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

/** 지도 (x, y) 가까이의 동물 (r칸 안, 그림 가운데 기준. 드래곤은 몸이 커서 넓게). */
export function animalAt(st: GameState, x: number, y: number, r: number): Animal | null {
  let best: Animal | null = null, bd = r;
  const R = st.info.rules;
  for (const an of st.animals.values()) {
    const big = isHostile(R, an.kind) ? 2.5 : 0;
    const d = Math.hypot(an.x - x, an.y - 0.4 - big * 0.5 - y) - big;
    if (d < bd) { bd = d; best = an; }
  }
  return best;
}
