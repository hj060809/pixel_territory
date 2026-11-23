// 지도 위 물체 그리기 (Canvas 2D, 화면 픽셀). 위치는 상태 사이를 보간한 값.
// 유닛·건물·배·동물은 스프라이트 스태킹 (stack.ts): 지형과 같은 해 방향·낮밤 색표로 칠하고, 유닛과 배는 가는 쪽으로 돈다.
// 밤에는 건물 둘레에 횃불 (torches.ts): 빛은 지형 빛 단계와 유닛·건물 칠하기에 함께 들어간다.
// 그림 한 점의 화면 크기는 모두 같다 (spriteK): 유닛과 건물의 점 크기가 섞이지 않게.

import type { Camera } from '../sim/camera.ts';
import type { TerrainScene } from '../terrain/scene.ts';
import { type Controller, UNIT_ZOOM } from './controller.ts';
import { F_OCEAN } from './terrainRules.ts';
import type { BuildRec } from './protocol.ts';
import { animalSpots, drawAnimals } from './wildlife.ts';
import type { SpriteBank } from './sprites.ts';
import { type Light, lightFrom, modelPoint } from './stack.ts';
import { BREATH_REACH, DRAGON_MOUTH, DRAGON_SIZE } from './models.ts';
import { Torches, drawFlame, nightAmount } from './torches.ts';
import { type GameState, lerp } from './state.ts';

const DIRS = 16;
const TAU = Math.PI * 2;
/** 날고 있는 병종을 땅에서 띄워 그리는 높이 (모델 점). 지도 칸으로는 FLY_LIFT / 2.4. */
export const FLY_LIFT = 18;
/** 드래곤 입의 자리 (모델 점): 몸 가운데에서 앞으로, 바닥에서 위로 (숨결 그림). */
const MOUTH_FWD = 30, MOUTH_UP = 22;
const STOMP_MS = 500;                // 바위거북 발 구르기 그림 (앞발을 들었다 내리찍기)
const TORTOISE = 6;                  // 병종 번호 (sim/rules.py)
const SAND = ['rgb(236,214,170)', 'rgb(214,186,132)', 'rgb(184,150,98)'];
const ICE = ['rgb(236,248,255)', 'rgb(190,228,246)', 'rgb(150,196,232)'];
/** 그림 한 점의 화면 크기 (확대에 따라). 건물 모델 너비가 2r × 2.4 점이라 땅 넓이와 맞는다. */
export const spriteK = (z: number) => Math.max(1, Math.round(z / 2.4));
/** 큰 물체(드래곤, 둥지)의 점 크기: 멀리서도 땅 넓이에 맞게 1보다 작아질 수 있다 (너무 작아지지는 않게). */
export const bigK = (z: number) => (z >= 2.4 ? spriteK(z) : Math.max(z / 2.4, 0.3));
/** 각도 → 방향 번호 (16방향). */
export const dirOf = (a: number) => ((Math.round(a / (TAU / DIRS)) % DIRS) + DIRS) % DIRS;
/** a를 b 쪽으로 돌린다 (짧은 쪽으로, 비율 f). */
export function turn(a: number, b: number, f: number) {
  let d = (b - a) % TAU;
  if (d > Math.PI) d -= TAU;
  if (d < -Math.PI) d += TAU;
  return a + d * Math.min(f, 1);
}

const WAKE = 'rgb(236,244,248)';
const SEL = 'rgb(240,250,240)';
const MOVING_BOAT = new Set([1, 2, 3, 5, 6, 8]);     // move hunt pickup cross return ahead

export class Overlay {
  constructor(private g: CanvasRenderingContext2D, private bank: SpriteBank, private st: GameState,
              private ctl: Controller, private scene: TerrainScene) {
    this.torches = new Torches(ctl.rules);
  }
  private torches: Torches;
  private light: Light | null = null;
  private lightKey = 0;
  private hourKey = NaN;
  private lastNow = 0;
  private ang = new Map<number, number>();        // 병사가 보는 방향 (라디안)
  private breathAt = new Map<number, number>();   // 숨결을 뿜은 화면 시각 (용기사)
  private spinAt = new Map<number, number>();     // 발 구르기를 한 화면 시각 (바위거북)
  private roarAt = new Map<number, number>();     // 낮은 포효를 한 화면 시각 (바위거북)
  private rings: { x: number; y: number; at: number; kind: number }[] = [];   // 발 구르기·포효 표시
  private flames: { x0: number; y0: number; x1: number; y1: number; at: number; weak: boolean }[] = [];   // 화염탑 불

  /** 화염탑 불 (0.6초): 분사구에서 목표로 뻗는 불꽃 줄기 (안쪽은 노랗고 바깥은 붉다), 맞은 자리에 불길과 그을음.
   *  약한 불(유황이 없을 때)은 가늘고 짧다. */
  private drawFlames(sx: (x: number) => number, sy: (y: number) => number, K: number, z: number, now: number) {
    const g = this.g, LIFE = 600, P = Math.max(K, 2);
    this.flames = this.flames.filter((f) => now - f.at < LIFE);
    const dot = (x: number, y: number, s: number) => g.fillRect(Math.round(x / P) * P, Math.round(y / P) * P, s, s);
    const FIRE = ['rgb(255,236,150)', 'rgb(255,178,70)', 'rgb(232,96,40)', 'rgb(170,50,30)'];
    for (const f of this.flames) {
      const age = (now - f.at) / LIFE, grow = Math.min(age / 0.25, 1), fade = age < 0.5 ? 1 : 1 - (age - 0.5) / 0.5;
      const ox = sx(f.x0), oy = sy(f.y0) - 18 * K, bx = sx(f.x1), by = sy(f.y1);   // 분사구 (탑 꼭대기 앞)
      const len = Math.hypot(bx - ox, by - oy), ang = Math.atan2(by - oy, bx - ox), ca = Math.cos(ang), sa = Math.sin(ang);
      const n = f.weak ? 60 : 150, width = f.weak ? 0.12 : 0.22, seed = Math.floor(f.x0 * 7 + f.y0 * 13);
      for (let i = 0; i < n; i++) {
        const h = ((i * 37 + seed) % 97) / 97, r = h * len * grow;
        const sp = r * width * ((((i * 53 + seed) % 89) / 44.5) - 1) + Math.sin(now * 0.025 + i) * P;
        g.globalAlpha = fade * (0.95 - h * 0.25);
        g.fillStyle = FIRE[Math.min(3, Math.floor(h * 2.2 + (Math.abs(sp) / (r * width + 1)) * 1.5))];
        dot(ox + ca * r - sa * sp, oy + sa * r + ca * sp - h * (1 - h) * 3 * K, h > 0.5 && !f.weak ? 2 * P : P);
      }
      if (age > 0.2 && !f.weak) {                                       // 맞은 자리: 불길과 그을음
        const sp2 = Math.min((age - 0.2) / 0.25, 1), rr = 2.5 * z * sp2;
        for (let i = 0; i < 30; i++) {
          const an = (i / 30) * TAU + seed, d = (((i * 29 + seed) % 23) / 23) * rr;
          g.globalAlpha = fade * 0.8;
          g.fillStyle = FIRE[(i % 3) + 1];
          dot(bx + Math.cos(an) * d, by + Math.sin(an) * d * 0.7 - ((i * 7) % 4) * P * (1 - age), P);
        }
      }
    }
    g.globalAlpha = 1;
  }
  private breaths: { x: number; y: number; at: number }[] = [];   // 야생 드래곤이 숨결을 뿜은 자리
  private frost: { x0: number; y0: number; x1: number; y1: number; at: number; air: boolean; src: string }[] = [];   // 그리는 중인 숨결
  private mouths = new Map<string, number[]>();   // 이번 장면에서 숨결 자세로 그린 드래곤: [입 x, y, 숨결이 닿는 앞쪽 땅 x, y] (u칸 / a번호)
  private seenShots = new WeakSet<object>();       // 이미 본 공격 (처음 본 것만 효과를 시작한다: 화면이 느려도 놓치지 않게)

  /** 바위거북: 발 구르기는 내리찍는 순간 흙먼지와 땅이 갈라지는 고리 (짧게), 포효는 낮게 퍼지는 두 겹 고리. */
  private drawRings(sx: (x: number) => number, sy: (y: number) => number, K: number, z: number, now: number, R: any) {
    const g = this.g, P = Math.max(K, 2);
    this.rings = this.rings.filter((r) => now - r.at < (r.kind === 4 ? 650 : 800));
    const dot = (x: number, y: number, s: number) => g.fillRect(Math.round(x / P) * P, Math.round(y / P) * P, s, s);
    for (const r of this.rings) {
      const cx = sx(r.x), cy = sy(r.y);
      if (r.kind === 4) {
        const e = (now - r.at) / 650, f = Math.max(0, (e - 0.42) / 0.58);   // 앞발을 든 동안은 아직, 내리찍은 뒤 퍼진다
        if (f <= 0) continue;
        const rr = (R.stomp_r ?? 2.6) * z * Math.min(1, f * 2.4);
        g.globalAlpha = 0.9 * (1 - f);
        for (let i = 0; i < 44; i++) {                                  // 흙먼지
          const an = (i / 44) * TAU, d = rr * (0.7 + ((i * 37) % 10) / 33);
          g.fillStyle = SAND[i % 3];
          dot(cx + Math.cos(an) * d, cy + Math.sin(an) * d * 0.7 - (i % 5) * P * (1 - f), i % 3 === 0 ? 2 * P : P);
        }
        g.fillStyle = 'rgb(70,54,40)';                                  // 갈라진 땅: 바깥으로 뻗는 금
        for (let k = 0; k < 6; k++) {
          const an = k * 1.05 + 0.3;
          for (let q = 0.3; q < Math.min(1, f * 3); q += 0.12) dot(cx + Math.cos(an) * rr * q, cy + Math.sin(an) * rr * q * 0.7, P);
        }
      } else {                                                          // 낮은 포효: 두 겹 고리가 바깥으로
        const f = (now - r.at) / 800;
        for (const lag of [0, 0.22]) {
          const q = Math.min(Math.max((f - lag) / 0.78, 0), 1), rr = (R.taunt_r ?? 7) * z * q;
          if (q <= 0 || q >= 1) continue;
          g.globalAlpha = 0.75 * (1 - q);
          g.fillStyle = lag ? SAND[1] : 'rgb(236,214,170)';
          const n = Math.max(24, Math.round(rr / P));
          for (let i = 0; i < n; i++) { const an = (i / n) * TAU; dot(cx + Math.cos(an) * rr, cy + Math.sin(an) * rr * 0.7, P); }
        }
      }
    }
    g.globalAlpha = 1;
  }

  /** 서리 숨결 (0.9초): 입에서 굵은 얼음 줄기가 뻗어 나가 넓게 퍼지고, 맞은 자리에 서리 안개와 얼음 고리.
   *  얼음 알갱이는 점 크기(K)의 2배까지, 앞으로 갈수록 크게 흩어진다. */
  private drawFrost(sx: (x: number) => number, sy: (y: number) => number, K: number, z: number, now: number) {
    const g = this.g, LIFE = 900;
    this.frost = this.frost.filter((f) => now - f.at < LIFE);
    const P = Math.max(K, 2);
    const dot = (x: number, y: number, s: number) => g.fillRect(Math.round(x / P) * P, Math.round(y / P) * P, s, s);
    for (const f of this.frost) {
      const age = (now - f.at) / LIFE;                                  // 0~1
      const grow = Math.min(age / 0.28, 1), fade = age < 0.55 ? 1 : 1 - (age - 0.55) / 0.45;
      const fa = Math.atan2(f.y1 - f.y0, f.x1 - f.x0);
      const m = this.mouths.get(f.src);                                 // 그린 드래곤의 입과 그 앞쪽 땅 (움직이면 따라간다)
      const bx = m ? m[2] : sx(f.x1), by = m ? m[3] : sy(f.y1);
      const lift = ((f.air ? FLY_LIFT : 0) + MOUTH_UP) * K;
      const ox = m ? m[0] : sx(f.x0) + Math.cos(fa) * MOUTH_FWD * K, oy = m ? m[1] : sy(f.y0) + Math.sin(fa) * MOUTH_FWD * K * 0.7 - lift;
      const len = Math.hypot(bx - ox, by - oy), ang = Math.atan2(by - oy, bx - ox), ca = Math.cos(ang), sa = Math.sin(ang);
      const seed = Math.floor(f.x0 * 13 + f.y0 * 7);
      for (let i = 0; i < 190; i++) {                                   // 얼음 줄기
        const h = ((i * 37 + seed) % 97) / 97, r = h * len * grow;
        const wob = Math.sin(now * 0.018 + i * 1.7) * P;                 // 일렁임
        const sp = r * 0.26 * ((((i * 53 + seed) % 89) / 44.5) - 1) + wob;
        const px = ox + ca * r - sa * sp, py = oy + sa * r + ca * sp;
        g.globalAlpha = fade * (0.95 - h * 0.35);
        g.fillStyle = h < 0.25 ? 'rgb(250,254,255)' : ICE[i % 3];
        dot(px, py, h > 0.45 ? 2 * P : P);
      }
      if (age > 0.18) {                                                 // 맞은 자리: 서리 안개와 얼음 고리
        const spread = Math.min((age - 0.18) / 0.3, 1), rr = 2.4 * z * spread;
        for (let i = 0; i < 46; i++) {
          const an = (i / 46) * TAU + seed, d = (((i * 29 + seed) % 23) / 23) * rr;
          g.globalAlpha = fade * 0.55;
          g.fillStyle = ICE[(i + 1) % 3];
          dot(bx + Math.cos(an) * d, by + Math.sin(an) * d * 0.7, 2 * P);
        }
        g.globalAlpha = fade * 0.9;
        g.fillStyle = 'rgb(236,248,255)';
        for (let i = 0; i < 28; i++) { const an = (i / 28) * TAU; dot(bx + Math.cos(an) * rr, by + Math.sin(an) * rr * 0.7, P); }
      }
    }
    g.globalAlpha = 1;
  }
  private boatAng = new Map<number, number>();

  /** 지금 빛 (시각이 1/12시간 움직일 때마다 새로). */
  private lightNow(): Light {
    const c = this.scene.cycle, hk = Math.round(c.hour * 12);
    if (!this.light || hk !== this.hourKey) {
      this.hourKey = hk;
      this.light = lightFrom(c, this.scene.bundle.meta.light.light_xy, ++this.lightKey);
    }
    return this.light;
  }

  /** 건물이 서는 방향 (4방향): 항구는 부두가 바다 쪽, 나머지는 자리마다 (뒤를 보는 일은 드물게). */
  private bdir(b: BuildRec): number {
    const K = this.st.info.rules.kinds;
    if (b.kind === K.HARBOR || b.kind === K.FISHERY) {                // 잔교가 바다 쪽을 본다
      const d = this.dock(b);
      if (d) return ((Math.round(Math.atan2(-(d[1] + 0.5 - b.x), d[0] + 0.5 - b.y) / (Math.PI / 2)) % 4) + 4) % 4;
    }
    return [0, 0, 1, 3][(b.slot * 7 + b.gen * 3) % 4];
  }

  private text(s: string, x: number, y: number, size: number, col: string, bold = false,
               align: CanvasTextAlign = 'left', base: CanvasTextBaseline = 'middle') {
    const g = this.g;
    g.font = `${bold ? 'bold ' : ''}${size}px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif`;
    g.textAlign = align; g.textBaseline = base;
    g.lineWidth = 2; g.strokeStyle = 'black'; g.strokeText(s, x, y);
    g.fillStyle = col; g.fillText(s, x, y);
  }

  private bar(cx: number, y: number, w: number, frac: number, col?: string) {
    frac = Math.min(Math.max(frac, 0), 1);
    col ??= `rgb(${Math.trunc(230 - 150 * frac)},${Math.trunc(70 + 160 * frac)},60)`;
    const x0 = Math.trunc(cx - w / 2), g = this.g;
    g.fillStyle = 'rgb(20,20,24)'; g.fillRect(x0 - 1, y - 1, w + 2, 4);
    g.fillStyle = col; g.fillRect(x0, y, Math.trunc(w * frac), 2);
  }

  /** 픽셀 말풍선: 어두운 1칸 테두리, 밝은 바탕, 아래로 계단 꼬리. 안에 대기열 병사 아이콘 (최대 5). */
  private bubble(b: BuildRec, cx: number, top: number, z: number) {
    const g = this.g, R = this.st.info.rules;
    const items: number[] = [];
    for (let k = 0; k < 5; k++) { const c = (b.qbits >> (3 * k)) & 7; if (c) items.push(c - 1); }   // 대기열 번호: 0 보병, 1 궁수, 2 전함
    if (!items.length) return;
    const p = Math.max(1, Math.round(z / 2.6));                 // 말풍선 픽셀 한 칸
    const unitOf = (q: number) => (q === 2 ? 0 : q);                                 // 대기열 번호 → 병종 그림
    const icons = items.map((q) => this.bank.unit(unitOf(q), b.own, 0, p));
    const iw = icons[0].width, ih = icons[0].height, gap = p;
    const w = icons.length * iw + (icons.length - 1) * gap + 4 * p, h = ih + 6 * p;
    const x0 = Math.round(cx - w / 2), y0 = Math.round(top - h - 4 * p);
    const ink = 'rgb(26,24,30)', paper = 'rgb(244,238,222)';
    g.fillStyle = ink;                                           // 테두리 (모서리는 한 칸 깎는다)
    g.fillRect(x0 + p, y0, w - 2 * p, h);
    g.fillRect(x0, y0 + p, w, h - 2 * p);
    g.fillStyle = paper;
    g.fillRect(x0 + p, y0 + p, w - 2 * p, h - 2 * p);
    const tx = Math.round(cx - p);                               // 꼬리: 두 계단
    g.fillStyle = ink; g.fillRect(tx - p, y0 + h - p, 4 * p, p); g.fillRect(tx, y0 + h, 2 * p, p); g.fillRect(tx + p, y0 + h + p, p, p);
    g.fillStyle = paper; g.fillRect(tx, y0 + h - p, 2 * p, p); g.fillRect(tx + p, y0 + h, p, p);
    icons.forEach((img, i) => g.drawImage(img, x0 + 2 * p + i * (iw + gap), y0 + 2 * p));
    const total = items[0] === 2 ? R.warship_time : R.unit_time[unitOf(items[0])];   // 맨 앞: 훈련 진행 막대
    const f = Math.min(Math.max(1 - b.qtime / total, 0), 1);
    g.fillStyle = 'rgb(200,192,170)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, iw, p);
    g.fillStyle = 'rgb(90,170,90)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, Math.max(p, Math.round(iw * f)), p);
  }

  private docks = new Map<number, [number, number] | null>();

  /** 전함을 짓는 자리: 항구 앞 물 칸(서버 Fleet.dock_of와 같은 규칙: 9칸 안의 가장 가까운 바다)에서
   *  바다 쪽으로 몇 칸 더 나간 곳 (항구 그림과 겹치지 않게). */
  private dock(b: BuildRec): [number, number] | null {
    const key = b.slot * 65536 + b.gen;
    if (this.docks.has(key)) return this.docks.get(key)!;
    const m = this.ctl.rules, y = Math.floor(b.y), x = Math.floor(b.x), r = 9;
    let best: [number, number] | null = null, bd = Infinity;
    for (let yy = Math.max(y - r, 0); yy <= Math.min(y + r, m.H - 1); yy++) {
      for (let xx = Math.max(x - r, 0); xx <= Math.min(x + r, m.W - 1); xx++) {
        if (!(m.at(yy, xx) & F_OCEAN)) continue;
        const d = (yy - y) ** 2 + (xx - x) ** 2;
        if (d < bd) { bd = d; best = [yy, xx]; }
      }
    }
    if (best) {                                                  // 항구 → 물 칸 방향으로 더 나가 바다인 곳
      const r0 = this.st.info.rules.build[b.kind].r, dy = best[0] - y, dx = best[1] - x, n = Math.hypot(dy, dx) || 1;
      for (let t = r0 + 6; t >= Math.hypot(dy, dx); t--) {
        const yy = Math.round(y + (dy / n) * t), xx = Math.round(x + (dx / n) * t);
        if (yy >= 0 && yy < m.H && xx >= 0 && xx < m.W && m.at(yy, xx) & F_OCEAN) { best = [yy, xx]; break; }
      }
    }
    this.docks.set(key, best);
    return best;
  }

  /** 항구 앞 바다에서 전함을 짓는 중: 흐린 윤곽 위로 아래부터 차오르는 배, 비계, 반짝이는 망치질. */
  private shipyard(b: BuildRec, sx: (x: number) => number, sy: (y: number) => number, z: number, now: number) {
    const d = this.dock(b);
    if (!d) return;
    const g = this.g, R = this.st.info.rules;
    const f = Math.min(Math.max(1 - b.qtime / R.warship_time, 0), 1);
    const k = spriteK(z);
    const { cv, ax, ay, p } = this.bank.stack.sprite('warship', b.own, this.lightNow(), { dir: 0, shadow: false });
    const img = { width: p.bw * k, height: p.bh * k };
    const x = Math.round(sx(d[1] + 0.5) - ax * k) + p.bx * k, y = Math.round(sy(d[0] + 0.5) - ay * k) + p.by * k;
    g.globalAlpha = 0.28;                                        // 다 지은 모습의 흐린 윤곽
    g.drawImage(cv, p.bx, p.by, p.bw, p.bh, x, y, img.width, img.height);
    g.globalAlpha = 1;
    const fs = Math.max(1, Math.round(p.bh * (0.15 + 0.85 * f)));   // 아래(배 밑)부터 차오른다
    g.drawImage(cv, p.bx, p.by + p.bh - fs, p.bw, fs, x, y + (p.bh - fs) * k, img.width, fs * k);
    const fill = fs * k;
    g.fillStyle = 'rgb(150,112,70)';                             // 비계: 양옆 기둥과 짓는 높이의 가로대
    const line = y + img.height - fill;
    g.fillRect(x - k, line, k, img.height - (line - y));
    g.fillRect(x + img.width, line, k, img.height - (line - y));
    g.fillRect(x - k, line, img.width + 2 * k, k);
    if (Math.floor(now / 180) % 3 !== 0) {                       // 망치질 반짝임
      const sxp = x + ((Math.floor(now / 540) * 7) % Math.max(1, img.width - k));
      g.fillStyle = 'rgb(255,236,170)';
      g.fillRect(sxp, line - k, k, k);
    }
    if (b.qlen > 1) this.text(`+${b.qlen - 1}`, x + img.width + 2 * k, y + 2, 11, 'rgb(255,240,200)');
  }

  draw(cam: Camera, now: number, mouse: [number, number] | null, box: [number, number, number, number] | null) {
    const g = this.g, st = this.st, z = cam.zoom, R = st.info.rules, me = st.info.me;
    const W = cam.viewW, H = cam.viewH;
    const sx = (x: number) => (x - cam.x) * z, sy = (y: number) => (y - cam.y) * z;
    const vis = (x: number, y: number, pad = 40) => x >= -pad && x <= W + pad && y >= -pad && y <= H + pad;
    const a = st.alpha(now), t = st.smoothTime(now);
    const dt = this.lastNow ? Math.min((now - this.lastNow) / 1000, 0.1) : 0;
    this.lastNow = now;
    g.imageSmoothingEnabled = false;
    this.ctl.prune();
    const L = this.lightNow(), K = spriteK(z), stack = this.bank.stack;
    this.mouths.clear();
    const fresh = st.shots.filter((s) => !this.seenShots.has(s));      // 이번에 처음 본 공격
    for (const s of fresh) this.seenShots.add(s);
    // 밤의 횃불: 지형에 빛을 넘기고, 유닛·건물 칠하기에도 쓴다
    const night = nightAmount(this.scene.cycle.sunAlt());
    const torches = this.torches.update(st, night, now / 1000);
    this.scene.setTorches(this.torches.points());
    const tl = (x: number, y: number) => (torches.length ? this.torches.at(x, y) : 0);

    // 자원지 (확대할수록 커진다. 멀리서도 2배 아래로는 줄지 않는다)
    const taken = st.siteTaken(), ks = Math.max(2, Math.round(z * 0.6));
    for (const s of st.info.sites) {
      if (taken.has(s.id)) continue;
      const fs = s.kind === R.kinds.FISH ? this.ctl.fishSpot(s) : null;   // 물고기 떼: 앞바다 무리의 가운데에
      const x = sx(fs ? fs.x + 0.5 : s.x), y = sy(fs ? fs.y + 0.5 : s.y);
      if (!vis(x, y)) continue;
      const img = this.bank.site(s.kind, ks, !!s.snow);
      g.drawImage(img, Math.round(x - img.width / 2), Math.round(y - img.height / 2));
    }
    // 드래곤 둥지 (땅의 장식: 건물·병사 아래)
    for (const [ly, lx] of st.info.lairs ?? []) {
      const x = sx(lx + 0.5), y = sy(ly + 0.5);
      if (!vis(x, y, 200)) continue;
      const kb = bigK(z);
      g.imageSmoothingEnabled = kb < 1;                                // 줄여 그릴 때는 부드럽게 (점이 빠져 깨지지 않게)
      stack.draw(g, 'lair', 0, L, x, y, kb, { dirs: 1, torch: tl(lx, ly) });
      g.imageSmoothingEnabled = false;
    }
    // 건물
    const selB = this.ctl.selB;
    const bubbles: [BuildRec, number, number][] = [];       // 말풍선 (병사들 위에 그리려고 나중에)
    const yards: BuildRec[] = [];
    const items: { y: number; f: () => void }[] = [];      // 건물과 횃불: 아래(앞)에 있는 것을 나중에
    for (const b of st.builds.values()) {
      const x = sx(b.x), y = sy(b.y);
      if (!vis(x, y, 120)) continue;
      items.push({ y: b.y, f: () => {
        const done = b.prog >= 1, name = `b${b.kind}`, dir = this.bdir(b);
        let box;
        if (!done) {                                           // 짓는 중: 흐린 다 지은 모습 위로 아래부터 쌓여 올라간다
          g.globalAlpha = 0.3;
          box = stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, shadow: false });
          g.globalAlpha = 1;
          stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, cut: Math.max(b.prog, 0.06), shadow: false });
        } else box = stack.draw(g, name, b.own, L, x, y, K, { dir, dirs: 4, torch: Math.max(tl(b.x, b.y), night * 0.45) });   // 제 횃불이 비춘다
        if (selB && selB[0] === b.slot) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(box.x - 2.5, box.y - 2.5, box.w + 4, box.h + 4); }
        const bw = Math.max(box.w, 14);
        if (!done) this.bar(box.x + box.w / 2, box.y + box.h + 3, bw, b.prog, 'rgb(120,200,255)');
        else if (b.hp < 0.999) this.bar(box.x + box.w / 2, box.y - 4, bw, b.hp);
        if (done && b.kind === R.kinds.HALL && b.qlen && b.own === me) {
          if (z >= UNIT_ZOOM) bubbles.push([b, box.x + box.w / 2, box.y]);   // 가까이: 말풍선에 대기열 병사 아이콘
          else this.text(`${b.qlen}`, box.x + box.w + 2, box.y + 4, 12, 'rgb(255,240,200)');
        }
        if (done && b.kind === R.kinds.HARBOR && b.qlen && b.qkind === 2) yards.push(b);
      } });
    }
    for (const p of torches) {                                // 횃불: 횃대와 일렁이는 불꽃
      const x = sx(p.x), y = sy(p.y);
      if (!vis(x, y)) continue;
      items.push({ y: p.y, f: () => {
        const al = Math.min(1, night * 1.5);
        g.globalAlpha = al;
        stack.draw(g, 'torch', 0, L, x, y, K, { dirs: 1, torch: 1 });
        g.globalAlpha = 1;
        drawFlame(g, Math.round(x), Math.round(y - 5 * K), K, now / 1000, p.id, al);
      } });
    }
    items.sort((p, q) => p.y - q.y);
    for (const it of items) it.f();
    for (const b of yards) this.shipyard(b, sx, sy, z, now);    // 항구 앞바다의 전함 건조 (건물에 가리지 않게 나중에)
    // 공격 요청 (나와 내 동맹이 함께 치자고 한 나라): 그 나라의 거점들 위에 붉은 과녁
    const marked = new Set((st.diplo?.targets ?? []).map((t) => t[1]));
    if (marked.size) {
      const pulse = 0.6 + 0.4 * Math.sin(now / 250);
      for (const b of st.builds.values()) {
        if (b.kind !== R.kinds.HALL || !marked.has(b.own)) continue;
        const x = sx(b.x), y = sy(b.y);
        if (!vis(x, y, 80)) continue;
        const r = Math.max(10, (R.build[b.kind].r + 1.5) * z);
        g.strokeStyle = `rgba(255,90,70,${pulse.toFixed(2)})`; g.lineWidth = 2;
        g.beginPath(); g.arc(Math.round(x), Math.round(y), r, 0, 7); g.stroke();
        for (const [ax, ay] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
          g.beginPath(); g.moveTo(x + ax * r * 0.7, y + ay * r * 0.7); g.lineTo(x + ax * r * 1.25, y + ay * r * 1.25); g.stroke();
        }
        this.text('공격 요청', x, y - r - 8, 12, 'rgb(255,150,130)', true, 'center');
      }
    }
    // 배
    for (const b of st.boats.values()) {
      if (b.bits & 1) continue;                                     // 아직 항구에서 출발 전
      const bx = lerp(b.px, b.x, a), by = lerp(b.py, b.y, a), x = sx(bx), y = sy(by);
      if (!vis(x, y, 60)) continue;
      const ferry = b.kind === 0;
      const mx = b.x - b.px, my = b.y - b.py;                        // 가는 쪽으로 뱃머리를 돌린다
      let ang = this.boatAng.get(b.id) ?? (b.dir < 0 ? Math.PI : 0);
      if (Math.hypot(mx, my) > 0.01) ang = turn(ang, Math.atan2(my, mx), dt * 4);
      this.boatAng.set(b.id, ang);
      const bob = ferry && Math.trunc(t * 2 + bx) % 2 ? 1 : 0;      // 살짝 출렁인다
      if (MOVING_BOAT.has(b.state)) {                                // 지나간 물보라 (고물 쪽)
        g.fillStyle = WAKE;
        const c = Math.cos(ang), s = Math.sin(ang), back = (ferry ? 6 : 11) * K;
        for (const k of [1, 2]) g.fillRect(Math.round(x - c * (back + k * 3 * K)), Math.round(y - s * (back + k * 3 * K)), K, K);
      }
      const rc = stack.draw(g, ferry ? 'ferry' : 'warship', b.own, L, x, y + bob * K, K, { dir: dirOf(ang), torch: tl(bx, by) });
      if (this.ctl.selShips.has(b.id)) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(rc.x - 2.5, rc.y - 2.5, rc.w + 4, rc.h + 4); }
      if (b.hp < 0.999) this.bar(rc.x + rc.w / 2, rc.y - 4, Math.max(rc.w, 12), b.hp);
      if (ferry && b.cargo) this.text(`${b.cargo}`, rc.x + rc.w + 2, rc.y + rc.h / 2, 12, 'white', true);
    }
    // 야생 동물 (멀리서는 작게)
    this.breaths = this.breaths.filter((b) => now - b.at < 900);      // 숨결을 뿜은 자리 (그 뒤 0.9초 동안 숨결 자세)
    for (const s of fresh) if (s.kind === 3) this.breaths.push({ x: s.x0, y: s.y0, at: now });
    const breathing = (x: number, y: number) => this.breaths.some((b) => Math.hypot(b.x - x, b.y - y) < 2.5);
    const tameBars = z >= 1.2 ? drawAnimals(g, stack, L, animalSpots(st, a, sx, sy), K, bigK(z), t, W, H, dt, tl, breathing, R, this.mouths) : [];
    // 병사: 가까이서는 하나하나, 멀리서는 무리 배지
    const units = [...st.units.values()].filter((u) => !(u.bits & 2));
    if (z >= UNIT_ZOOM) {
      for (const s of st.shots) {                                 // 치는 병사는 맞는 쪽을 본다
        if (!fresh.includes(s)) continue;
        const u = this.ctl.unitAt(s.x0, s.y0, 0.7, undefined, true);
        if (!u) continue;
        if (s.kind === 4) { this.spinAt.set(u.slot, now); continue; }   // 바위거북 발 구르기
        if (s.kind === 5) { this.roarAt.set(u.slot, now); continue; }   // 바위거북 낮은 포효
        this.ang.set(u.slot, Math.atan2(s.y1 - s.y0, s.x1 - s.x0));
        if (s.kind === 3) this.breathAt.set(u.slot, now);
      }
      const list = units.map((u) => ({ u, x: sx(lerp(u.px, u.x, a)), y: sy(lerp(u.py, u.y, a)) }))
        .filter((p) => p.x > -80 && p.x < W + 80 && p.y > -120 && p.y < H + 80).sort((p, q) => p.y - q.y);
      const flying = (u: { bits: number }) => (u.bits & 4) !== 0;     // 날고 있다 (용기사)
      const shadowA = Math.max(0.12, L.shadow ? L.shadow.a * 0.9 : 0.12);
      for (const { u, x, y } of list) {                         // 날고 있는 병사의 땅 그림자 (모두 땅 위에 먼저)
        if (!flying(u)) continue;
        const sh = stack.silhouette(`u${u.kind}`, { frame: 1, dir: dirOf(this.ang.get(u.slot) ?? 0) });
        g.globalAlpha = shadowA;
        g.drawImage(sh.cv, Math.round(x - sh.ax * K + 3 * K), Math.round(y - sh.ay * K * 0.45 + 2 * K), sh.cv.width * K, Math.round(sh.cv.height * K * 0.45));
        g.globalAlpha = 1;
      }
      const air = list.filter((p) => flying(p.u));
      for (const { u, x, y: y0 } of [...list.filter((p) => !flying(p.u)), ...air]) {   // 걷는 병사, 그 위로 나는 병사
        const fly = flying(u), y = fly ? y0 - FLY_LIFT * K : y0;
        const breath = now - (this.breathAt.get(u.slot) ?? -1e9) < 900, dragon = !!R.unit_fly?.[u.kind];
        const pang = u.kind === TORTOISE, spun = now - (this.spinAt.get(u.slot) ?? -1e9), roared = now - (this.roarAt.get(u.slot) ?? -1e9);
        const frame = pang ? (u.state === 5 ? 2 : spun < STOMP_MS * 0.55 ? 3 : roared < 700 ? 4 : u.bits & 1 ? Math.trunc(t * 2.2 + u.slot * 0.3) % 2 : 0)   // 바위거북: 숨기, 발 구르기, 포효, 걷기
          : fly ? (breath ? 6 : 1 + (Math.trunc(t * 3 + u.slot * 0.3) % 2))                // 날갯짓, 날며 숨결
          : dragon ? (breath ? 5 : u.bits & 1 ? (Math.trunc(t * 3.2 + u.slot * 0.3) % 2 ? 7 : 8) : 0)   // 땅의 용기사: 숨결, 걷기, 서기
          : u.bits & 1 ? Math.trunc(t * 4.5 * 1.2 + u.slot * 0.37) % 2 : 0;   // 걸을 때 다리
        const mx = u.x - u.px, my = u.y - u.py;                    // 가는 쪽으로 몸을 돌린다
        let ang = this.ang.get(u.slot) ?? (u.slot % 2 ? Math.PI * 0.5 : Math.PI * 0.25);
        if (Math.hypot(mx, my) > 0.01) ang = turn(ang, Math.atan2(my, mx), dt * 10);
        this.ang.set(u.slot, ang);
        const shake = pang && spun > STOMP_MS * 0.55 && spun < STOMP_MS ? (Math.floor(spun / 40) % 2 ? K : -K) : 0;   // 내리찍을 때 흔들림
        const rc = stack.draw(g, `u${u.kind}`, u.own, L, x + shake, y, K, { frame, dir: dirOf(ang), torch: tl(lerp(u.px, u.x, a), lerp(u.py, u.y, a)), shadow: !fly });
        if (dragon && DRAGON_MOUTH[frame]) {                            // 숨결이 나올 입 자리
          const [mx, my, mz] = DRAGON_MOUTH[frame], d = dirOf(ang);
          const [dx, dy] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx, my, mz, d, 16, K);
          const [ex, ey] = modelPoint(DRAGON_SIZE[0], DRAGON_SIZE[1], mx + BREATH_REACH, my, 0, d, 16, K);   // 입 앞쪽의 땅
          this.mouths.set(`u${u.slot}`, [x + dx, y + dy, x + ex, y0 + ey]);
        }
        if (this.ctl.sel.has(u.slot)) { g.strokeStyle = 'rgb(235,250,235)'; g.lineWidth = 1; g.beginPath(); g.moveTo(rc.x, rc.y + rc.h + 1.5); g.lineTo(rc.x + rc.w, rc.y + rc.h + 1.5); g.stroke(); }
        if (u.hp < 0.99) this.bar(rc.x + rc.w / 2, rc.y - 3, Math.max(rc.w - 2, 8), u.hp);
      }
    } else {
      const cell = 34, groups = new Map<string, { own: number; n: number; x: number; y: number; sel: boolean }>();
      for (const u of units) {
        const x = sx(lerp(u.px, u.x, a)), y = sy(lerp(u.py, u.y, a));
        const key = `${u.own},${Math.floor(y / cell)},${Math.floor(x / cell)}`;
        const e = groups.get(key) ?? { own: u.own, n: 0, x: 0, y: 0, sel: false };
        e.n++; e.x += x; e.y += y; e.sel ||= this.ctl.sel.has(u.slot);
        groups.set(key, e);
      }
      const list = [...groups.values()].map((e) => ({ ...e, x: e.x / e.n, y: e.y / e.n })).sort((p, q) => p.y - q.y);
      for (const e of list) {
        if (!vis(e.x, e.y)) continue;
        g.font = `bold 12px 'Malgun Gothic', sans-serif`;
        const w = Math.max(g.measureText(`${e.n}`).width + 8, 16), h = 15;
        const x0 = e.x - w / 2, y0 = e.y - h / 2;
        g.fillStyle = 'rgb(20,18,24)'; roundRect(g, x0 - 1, y0 - 1, w + 2, h + 2, 4); g.fill();
        const c = st.info.nations[e.own].color;
        g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; roundRect(g, x0, y0, w, h, 4); g.fill();
        if (e.sel) { g.strokeStyle = 'rgb(240,255,240)'; g.lineWidth = 1; roundRect(g, x0 - 2.5, y0 - 2.5, w + 5, h + 5, 5); g.stroke(); }
        this.text(`${e.n}`, e.x, e.y + 1, 12, 'white', true, 'center');
      }
    }
    // 공격: 화살(날아가는 짧은 선), 포탄(검은 점 → 물보라), 칼부림(반짝)
    for (const s of st.shots) {
      const age = (t - s.t0) / 0.3;
      const ax = sx(s.x0), ay = sy(s.y0), bx = sx(s.x1), by = sy(s.y1);
      if (s.kind === 2) {                                         // 포탄
        const f = Math.min(age * 1.3, 1.0);
        if (f < 1) {
          g.fillStyle = 'rgb(30,28,34)'; g.beginPath();
          g.arc(ax + (bx - ax) * f, ay + (by - ay) * f - 6 * z * f * (1 - f), Math.max(1, Math.trunc(z * 0.45)), 0, 7); g.fill();
        } else { g.strokeStyle = WAKE; g.lineWidth = 1; g.beginPath(); g.arc(bx, by, Math.max(2, Math.trunc(z)), 0, 7); g.stroke(); }
      } else if (s.kind === 6 || s.kind === 7) {                 // 화염탑: 불 (아래 flames에서)
        if (fresh.includes(s)) this.flames.push({ x0: s.x0, y0: s.y0, x1: s.x1, y1: s.y1, at: now, weak: s.kind === 7 });
      } else if (s.kind === 4 || s.kind === 5) {                 // 바위거북: 발 구르기 / 포효 (아래 rings에서)
        if (fresh.includes(s)) this.rings.push({ x: s.x0, y: s.y0, at: now, kind: s.kind });
      } else if (s.kind === 3) {                                 // 서리 숨결: 아래 frost에서 (더 오래, 굵게)
        if (fresh.includes(s)) {
          const shooter = this.ctl.unitAt(s.x0, s.y0, 0.8, undefined, true);
          let src = shooter ? `u${shooter.slot}` : '';                  // 뿜은 것: 용기사 칸, 아니면 가장 가까운 드래곤
          if (!shooter) {
            let bd = 4;
            for (const an of st.animals.values()) { const d = Math.hypot(an.x - s.x0, an.y - s.y0); if (d < bd) { bd = d; src = `a${an.id}`; } }
          }
          this.frost.push({ x0: s.x0, y0: s.y0, x1: s.x1, y1: s.y1, at: now, air: !!(shooter && shooter.bits & 4), src });
        }
      } else if (s.kind === 1) {                                 // 화살·망루
        const f = Math.min(Math.max(age, 0) * 1.6, 1.0), h = Math.max(f - 0.15, 0.0);
        g.strokeStyle = 'rgb(236,226,196)'; g.lineWidth = 1; g.beginPath();
        g.moveTo(ax + (bx - ax) * h, ay + (by - ay) * h); g.lineTo(ax + (bx - ax) * f, ay + (by - ay) * f); g.stroke();
      } else if (age < 0.5) {                                    // 칼부림
        g.fillStyle = 'rgb(255,250,230)'; g.beginPath(); g.arc(bx, by - 2 * z, Math.max(1, Math.trunc(z * 0.5)), 0, 7); g.fill();
      }
    }
    this.drawFrost(sx, sy, K, z, now);
    this.drawRings(sx, sy, K, z, now, R);
    this.drawFlames(sx, sy, K, z, now);
    for (const p of tameBars) this.bar(p.x, p.y, p.w, p.prog, p.col || undefined);   // 길들이기 진행, 드래곤 체력 (병사에 가리지 않게 나중에)
    for (const p of tameBars) if (p.label) this.text(p.label, p.x, p.y - 8, 11, 'rgb(205,232,255)', true, 'center');
    // 거점 위 말풍선: 대기열에 있는 병사 아이콘 (맨 앞은 훈련 진행 막대)
    for (const [b, cx, top] of bubbles) this.bubble(b, cx, top, z);
    // 명령 표시
    this.ctl.pings = this.ctl.pings.filter((p) => now - p.t0 < 600);
    for (const p of this.ctl.pings) {
      const f = (now - p.t0) / 600;
      g.strokeStyle = p.col; g.lineWidth = 1; g.beginPath(); g.arc(Math.trunc(sx(p.x)), Math.trunc(sy(p.y)), Math.trunc(4 + 10 * f), 0, 7); g.stroke();
    }
    // 드래그 상자
    if (box) { g.strokeStyle = 'rgb(230,240,230)'; g.lineWidth = 1; g.strokeRect(Math.min(box[0], box[2]) + 0.5, Math.min(box[1], box[3]) + 0.5, Math.abs(box[2] - box[0]), Math.abs(box[3] - box[1])); }
    // 건물 자리 미리보기
    const mode = this.ctl.mode;
    if (mouse && typeof mode === 'number') {                     // 놓을 건물이 커서에 (자원지 건물은 빈 자원지에 붙는다)
      const kind = mode;
      const [mx, my] = cam.toMap(mouse[0], mouse[1]);
      const t = this.ctl.placeTarget(kind, mx, my, z);
      const ok = t.ok;
      const px = t.ok ? sx(t.x) : mouse[0], py = t.ok ? sy(t.y) : mouse[1];
      g.globalAlpha = 0.55;
      const rc = stack.draw(g, `b${kind}`, me, L, px, py, K, { dirs: 4, shadow: false });
      g.globalAlpha = 1;
      g.strokeStyle = ok ? 'rgb(120,230,120)' : 'rgb(230,90,80)'; g.lineWidth = 1; g.strokeRect(rc.x - 2.5, rc.y - 2.5, rc.w + 4, rc.h + 4);
    }
  }
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}
