// 야생 동물 그리기 (규칙과 움직임은 서버 sim/wildlife.py, 위치는 상태 사이를 보간).
// 말·순록: 풀 뜯기·거닐기·달아나기 그림 (순록은 길들이지 않는다: 목장에 들인다), 길들이는 중에는 앞발을 들었다 놓으며 흙먼지가 일고, 머리 위에 진행 막대.
// 드래곤 (사나운 동물): 둥지에서 잠 → 깨어 싸움 (숨결을 뿜을 때 입을 벌린다, 체력 막대) → 쓰러짐 (남은 시간 막대,
// 길들이는 중이면 진행 막대). 길들이러 오는 병사를 기다리는 동물은 발밑에 작은 표시.
// 드래곤 기술 (sim/wildlife.py): 눈보라를 모으면 입을 벌리고 입 앞에 빛이 모인다 (겨눈 곳의 원과 던진 빛은 draw.ts),
// 날면 띄워 그리고 땅에 그림자.

import { type Light, type StackRenderer, modelPoint } from './stack.ts';
import { BREATH_REACH, DRAGON_MOUTH, DRAGON_SIZE } from './models.ts';
import { type Animal, type GameState, lerp } from './state.ts';

export const A_GRAZE = 0, A_WALK = 1, A_FLEE = 2, A_HELD = 3, A_TAMING = 4;     // 동물 상태 (서버와 같은 번호)
export const A_SLEEP = 5, A_FIGHT = 6, A_SUBDUED = 7;                           // 사나운 동물
export const A_NOVA = 8, A_FLY = 9, A_AIR_NOVA = 10;                             // 드래곤 기술: 눈보라 모으기, 날기, 날며 (공중에 멈춰) 눈보라 모으기
export const A_RAID = 11, A_HOMEWARD = 12;                                       // 드래곤 겨울 습격: 습격 중, 둥지로 돌아가는 중 (둘 다 날고 있다)
const LIFT = 18;                                                                 // 날 때 띄워 그리는 높이 (모델 점, draw.ts FLY_LIFT와 같다)
const NAMES = ['horse', 'dragon', 'tortoise', 'reindeer'] as const;                                      // 동물 종류 → 모델 (rules.WILDLIFE 순서)
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
                            breathing: (x: number, y: number, id: number) => boolean, R: any,
                            mouths?: Map<string, number[]>, aimOf?: (an: Animal) => number[] | null): AnimalBar[] {
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
      const breath = breathing(an.x, an.y, an.id);                   // 숨결을 뿜는 중이면 다 뿜을 때까지 숨결 자세 (그새 쓰러지거나 잠들어도: 숨결이 입에서 끝나게)
      frame = breath && an.state !== A_FLY && an.state !== A_RAID && an.state !== A_HOMEWARD ? 5 : an.state === A_SLEEP ? 3 : an.state === A_NOVA || an.state === A_AIR_NOVA ? 5   // 잠 / 눈보라를 모은다 (날개를 펴 들고)
        : an.state === A_FLY || an.state === A_RAID || an.state === A_HOMEWARD ? (breathing(an.x, an.y, an.id) ? 6 : 1 + (Math.trunc(t * 4 + seed) % 2))   // 날며 숨결 / 날갯짓
        : an.state !== A_FIGHT ? 4                                                       // 쓰러짐: 날개를 늘어뜨린다
        : breathing(an.x, an.y, an.id) ? 5 : moving ? (Math.trunc(t * 3.2 + seed) % 2 ? 7 : 8) : 0;   // 숨결 / 걷기 / 서기
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
    const aim = hostile && aimOf ? aimOf(an) : null;          // 눈보라를 겨눈 곳 / 숨결을 뿜는 상대를 바라본다
    if (aim) a = turnTo(a, Math.atan2(aim[1] - an.y, aim[0] - an.x), dt * 8);
    else if (an.state === A_TAMING || an.state === A_HELD || (hostile && (an.state === A_FIGHT || an.state === A_FLY || an.state === A_RAID) && Math.hypot(mx, my) < 0.005)) {   // 멈췄다: 상대 쪽 (날다가 돌아볼 때도)
      a = turnTo(a, an.dir < 0 ? Math.PI : 0, dt * 4);
    } else if (Math.hypot(mx, my) > 0.005) a = turnTo(a, Math.atan2(my, mx), dt * 6);
    ang.set(an.id, a);
    const dir = ((Math.round(a / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
    const nova = hostile && (an.state === A_NOVA || an.state === A_AIR_NOVA) ? R.wildlife[an.kind]?.nova : null;
    const lift = hostile && (an.state === A_FLY || an.state === A_AIR_NOVA || an.state === A_RAID || an.state === A_HOMEWARD) ? Math.round(LIFT * k) : 0;   // 날고 있다: 띄워 그리고 땅에 그림자
    if (lift) {
      const sh = stack.silhouette(NAMES[an.kind] ?? 'dragon', { frame, dir });
      g.globalAlpha = 0.28;
      g.drawImage(sh.cv, Math.round(x - sh.ax * k + 3 * k), Math.round(y - sh.ay * k * 0.45 + 2 * k), sh.cv.width * k, Math.round(sh.cv.height * k * 0.45));
      g.globalAlpha = 1;
    }
    g.imageSmoothingEnabled = k < 1;
    const rc = stack.draw(g, NAMES[an.kind] ?? 'horse', 0, L, x, y - hop * k - lift, k, { frame, dir, torch: torch(an.x, an.y), shadow: !lift });
    g.imageSmoothingEnabled = false;
    if (hostile && mouths && DRAGON_MOUTH[frame]) {                   // 숨결이 나올 입 자리 (화면)
      const [mx, my, mz] = DRAGON_MOUTH[frame], [dx, dy] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx, my, mz, dir, DIRS, k);
      const [ex, ey] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx + BREATH_REACH, my, 0, dir, DIRS, k);   // 입 앞쪽의 땅
      mouths.set(`a${an.id}`, [x + dx, y - hop * k - lift + dy, x + ex, y + ey]);
    }
    if (nova && DRAGON_MOUTH[frame]) {                              // 눈보라를 모은다: 벌린 입 앞에 빛이 모여 구체로 자란다 (픽셀 그림)
      const [mx, my, mz] = DRAGON_MOUTH[frame], [dx, dy] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx + 3, my, mz, dir, DIRS, k);
      pixelOrb(g, Math.round(x + dx), Math.round(y - hop * k - lift + dy), Math.max(1, Math.round(k)), Math.min(Math.max(an.prog, 0), 1), t, seed);
    }
    const img = { width: Math.round(rc.w), height: Math.round(rc.h) }, rx = Math.round(rc.x), ry = Math.round(rc.y);
    const kp = Math.max(1, Math.round(k));                   // 작은 표시(발밑·z·흙먼지)는 정수 점으로 (흐려지지 않게)
    if (an.state === A_HELD || an.state === A_TAMING) {      // 발밑 표시: 누군가 길들이는 동물
      g.fillStyle = 'rgba(255,236,170,0.75)';
      g.fillRect(rx + kp, Math.round(y + 2 * kp), img.width - 2 * kp, Math.max(1, kp >> 1));
    }
    if (hostile) {
      if (an.state === A_SLEEP && frame === 3 && Math.floor(t * 0.8 + seed) % 2 === 0) {   // (숨결을 다 뿜고 잠든 뒤에)     // 잠: 머리 위로 떠오르는 작은 z
        g.fillStyle = 'rgba(220,236,255,0.8)';
        const zx = Math.round(rx + img.width * 0.7), zy = Math.round(ry - 2 * kp - ((t * 6) % 6) * kp * 0.5);
        g.fillRect(zx, zy, 3 * kp, kp); g.fillRect(zx + kp, zy + kp, kp, kp); g.fillRect(zx, zy + 2 * kp, 3 * kp, kp);
      }
      const w = Math.max(img.width * 0.7, 30), cx = rx + img.width / 2;
      if (an.state === A_FIGHT || an.state === A_NOVA || an.state === A_FLY || an.state === A_AIR_NOVA || an.state === A_RAID || an.state === A_HOMEWARD || (an.state === A_SLEEP && an.hp < 0.99)) {
        bars.push({ x: cx, y: ry - 4, w, prog: an.hp, col: '' });
      }
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

/** 입 앞에 모이는 빛 (픽셀 그림, 점 하나 = P 화면 픽셀): 밝은 점 하나에서 시작해 둘레의 작은 빛들이 꼬리를 끌며 빨려 들어오고,
 *  빛 구체로 점점 커진다 (가운데 흰빛 → 하늘빛 → 파랑, 가장자리는 체크무늬로 섞고 바깥에 깜빡이는 빛무리). p: 모은 정도 0~1. */
export function pixelOrb(g: CanvasRenderingContext2D, ox: number, oy: number, P: number, p: number, t: number, seed: number) {
  const C = ['rgb(250,253,255)', 'rgb(200,236,255)', 'rgb(120,190,250)', 'rgb(60,120,220)'];
  const put = (bx: number, by: number, c: string, a = 1) => {
    g.globalAlpha = a; g.fillStyle = c;
    g.fillRect(ox + bx * P - (P >> 1), oy + by * P - (P >> 1), P, P);
  };
  const R = 0.5 + 4.2 * p;                                       // 구체 반지름 (점 단위)
  const tick = Math.floor(t * 8);
  // 1) 둘레에서 모여드는 작은 빛 (모을수록 많이): 바깥 원에서 소용돌이치며 입 앞으로, 꼬리 둘
  const n = 6 + Math.round(10 * p), D = 9 + R * 1.6;
  for (let i = 0; i < n; i++) {
    for (let tr = 2; tr >= 0; tr--) {
      const ph = ((t * 0.9 + i / n + seed * 0.13) % 1) - tr * 0.035;
      if (ph < 0) continue;
      const d = R + (1 - ph) ** 1.6 * D, an = i * 2.39996 + ph * 1.6 + seed;
      const bx = Math.round(Math.cos(an) * d), by = Math.round(Math.sin(an) * d * 0.8);
      put(bx, by, tr === 0 ? (i % 3 ? C[1] : C[0]) : C[2], tr === 0 ? 0.95 : 0.55 - tr * 0.15);
    }
  }
  // 2) 빛 구체: 점마다 가운데에서의 거리로 색 (가장자리는 체크무늬로 섞는다)
  const rr = Math.ceil(R + 1.5);
  for (let by = -rr; by <= rr; by++) {
    for (let bx = -rr; bx <= rr; bx++) {
      const d = Math.hypot(bx, by);
      if (d <= R) {
        const f = d / Math.max(R, 0.5);
        const c = f < 0.45 ? C[0] : f < 0.75 ? C[1] : ((bx + by) & 1 ? C[1] : C[2]);
        put(bx, by, c);
      } else if (d <= R + 1.5 && ((bx + by + tick) & 1) === 0) {     // 빛무리: 바깥에 깜빡이는 점
        put(bx, by, d <= R + 0.8 ? C[2] : C[3], 0.55);
      }
    }
  }
  // 3) 반짝임: 구체 둘레에 십자 모양 점이 번갈아 켜진다
  for (let q = 0; q < 3; q++) {
    if (((tick + q * 3) % 7) > 2) continue;
    const an = q * 2.1 + seed, d = R + 2.5;
    const sx = Math.round(Math.cos(an) * d), sy = Math.round(Math.sin(an) * d * 0.8);
    put(sx, sy, C[0]); put(sx - 1, sy, C[1], 0.7); put(sx + 1, sy, C[1], 0.7); put(sx, sy - 1, C[1], 0.7); put(sx, sy + 1, C[1], 0.7);
  }
  g.globalAlpha = 1;
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
