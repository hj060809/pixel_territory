// 스프라이트 스태킹: 복셀 모델을 방향만큼 돌려 바닥부터 한 층씩 한 점 위로 올려 쌓는다 (보이는 점 = 가장 위·앞 층).
// 칠하기는 지형 빛 단계(render/terrain.ts)와 같은 빛·색표를 쓴다:
//   1) 낮 그림: 면의 방향(위, 옆)과 고정된 해(왼쪽 위)로 재질의 5단계 색 중 하나 (점마다 조금씩 다른 결)
//   2) 지금 시각: 해/달이 그 면을 비추는 양만큼 지형의 빛 표와 그늘 표를 섞는다
//   3) 밤의 횃불: 가까운 횃불 빛만큼 따뜻한 색을 섞는다 (아래쪽일수록 밝게)
// 지형은 결이 거칠어 Bayer 디더가 묻히지만 물체의 고른 면에서는 체크무늬로 드러나서, 물체는 디더 대신 섞는다.
// 바깥에 어두운 테두리 한 점과 해 반대쪽으로 지는 그림자 (지형과 구분되게).
// 돌린 모양(투영)은 (모델, 프레임, 방향)마다 한 번, 칠한 그림은 (나라, 빛, 횃불)이 바뀔 때만 다시 만든다.

import { model } from './models.ts';
import { Mat, RAMPS, Vol, nationRamp, roofRamp } from './voxel.ts';

const OUTLINE = [22, 18, 26];
const WARM = [1.02, 0.78, 0.48];             // 횃불 빛 (낮 그림 × 이것, 너무 밝지 않게)
const SHADOW_MAX = 1.5;                     // 그림자 길이 한도 (높이 × 이것)
export const SQUASH = 0.7;                  // 바닥 깊이(화면 위아래)를 이만큼 눌러 비스듬히 내려다보는 느낌으로
const REF = (() => {                        // 낮 그림의 고정된 해 (왼쪽 위, 고도 40°)
  const a = (40 * Math.PI) / 180, l = Math.SQRT1_2;
  return [-l * Math.cos(a), -l * Math.cos(a), Math.sin(a)];
})();

/** 지금 빛: 지형 빛 단계와 같은 값들. */
export interface Light {
  key: number;                              // 바뀔 때마다 다른 값 (칠한 그림을 다시 만들지 정한다)
  table: Uint8Array;                        // 512×4: 그늘 표(0~255) + 빛 표(256~511)
  src: { x: number; y: number; z: number; w: number; div: number }[];
  shadow: { dx: number; dy: number; a: number } | null;   // 그림자 방향(점/높이)과 진하기
}

/** 정오의 빛 (화면 아이콘, 로비 그림). */
export function noonLight(): Light {
  const table = new Uint8Array(512 * 4);
  for (let v = 0; v < 256; v++) {
    for (let c = 0; c < 3; c++) { table[v * 4 + c] = Math.min(255, Math.trunc(v * 0.95)); table[(256 + v) * 4 + c] = v; }
    table[v * 4 + 2] = v;
  }
  const a = (50 * Math.PI) / 180, l = Math.SQRT1_2;
  return { key: -1, table, src: [{ x: -l * Math.cos(a), y: -l * Math.cos(a), z: Math.sin(a), w: 1, div: Math.sin(a) }], shadow: null };
}

interface Cycle { table(): Uint8Array; sources(): [number, number][] }

/** 지형 시계에서 빛 (light_xy: 해/달이 오는 화면 방향). */
export function lightFrom(cycle: Cycle, lxy: number[], key: number): Light {
  const [lx, ly] = lxy;
  const src: Light['src'] = [];
  let best: [number, number] | null = null;
  for (const [alt, w] of cycle.sources()) {
    if (!(w > 0 && alt > 0)) continue;
    const a = (alt * Math.PI) / 180;
    src.push({ x: lx * Math.cos(a), y: ly * Math.cos(a), z: Math.sin(a), w, div: Math.max(Math.sin(a), 0.2) });
    if (!best || w > best[1]) best = [alt, w];
  }
  let shadow: Light['shadow'] = null;
  if (best) {
    const cot = Math.min(1 / Math.tan((Math.max(best[0], 4) * Math.PI) / 180), SHADOW_MAX);
    shadow = { dx: -lx * cot, dy: -ly * cot * SQUASH, a: 0.34 * Math.min(best[1], 1) };
  }
  return { key, table: cycle.table(), src, shadow };
}

// ------------------------------------------------------------- 투영
interface Proj {
  w: number; h: number;                    // 그림 크기 (그림자 여백 포함)
  ax: number; ay: number;                  // 바닥 가운데 점
  mat: Uint8Array; bias: Int8Array; seed: Float32Array;
  nx: Float32Array; ny: Float32Array; nz: Float32Array;
  cols: Int16Array;                        // 그림자용: [u, v, 꼭대기 z]...
  bx: number; by: number; bw: number; bh: number;   // 물체가 차지한 상자 (그림자 빼고)
}

const projCache = new Map<string, Proj>();

function hash(a: number, b: number, c: number) {
  let h = (a * 73856093) ^ (b * 19349663) ^ (c * 83492791);
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** 모델을 angle(라디안, 앞 +x가 향할 방향)만큼 돌려 쌓은 모양. cut: 이 층까지만 (짓는 중). */
function project(v: Vol, angle: number, cut: number): Proj {
  const { W, D, H } = v;
  const S = Math.ceil(Math.hypot(W, D) / 2) * 2 + 2, SQ = Math.ceil((S * SQUASH) / 2) * 2;
  const c = S / 2, cq = SQ / 2, cs = Math.cos(angle), sn = Math.sin(angle);
  const top = Math.min(H, cut);
  const rot = new Uint8Array(S * SQ * H), rb = new Int8Array(S * SQ * H);
  const ri = (u: number, w: number, z: number) => (z * SQ + w) * S + u;
  for (let w = 0; w < SQ; w++) for (let u = 0; u < S; u++) {
    const px = u + 0.5 - c, py = (w + 0.5 - cq) / SQUASH;
    const mx = Math.floor(cs * px + sn * py + W / 2 + 1e-4), my = Math.floor(-sn * px + cs * py + D / 2 + 1e-4);
    if (mx < 0 || my < 0 || mx >= W || my >= D) continue;
    for (let z = 0; z < top; z++) {
      const m = v.get(mx, my, z);
      if (!m) continue;
      rot[ri(u, w, z)] = m;
      rb[ri(u, w, z)] = v.bias[(z * D + my) * W + mx];
    }
  }
  const at = (u: number, w: number, z: number) => (u < 0 || w < 0 || z < 0 || u >= S || w >= SQ || z >= H ? 0 : rot[ri(u, w, z)]);
  const margin = Math.ceil(H * SHADOW_MAX * Math.SQRT1_2) + 2;
  const iw = S + margin + 2, ih = SQ + H + margin + 1;
  const ox = 1, oy = H;                                                  // 그림 안의 (u, w, z=0) 자리 = (u+ox, w+oy)
  const n = iw * ih;
  const p: Proj = {
    w: iw, h: ih, ax: c + ox, ay: cq + oy, mat: new Uint8Array(n), bias: new Int8Array(n), seed: new Float32Array(n),
    nx: new Float32Array(n), ny: new Float32Array(n), nz: new Float32Array(n), cols: new Int16Array(0),
    bx: 0, by: 0, bw: 0, bh: 0,
  };
  let x0 = iw, y0 = ih, x1 = -1, y1 = -1;
  const cols: number[] = [];
  for (let z = 0; z < H; z++) for (let w = 0; w < SQ; w++) for (let u = 0; u < S; u++) {
    const m = at(u, w, z);
    if (!m) continue;
    const i = (w - z + oy) * iw + (u + ox);
    let nx = 0, ny = 0, nz = 0;
    if (!at(u, w, z + 1)) nz += 1;
    if (!at(u, w + 1, z)) ny += 0.8;
    if (!at(u - 1, w, z)) nx -= 0.6;
    if (!at(u + 1, w, z)) nx += 0.6;
    if (!nx && !ny && !nz) { ny = 0.7; nz = 0.7; }
    const L = Math.hypot(nx, ny, nz);
    p.mat[i] = m; p.bias[i] = rb[ri(u, w, z)];
    p.nx[i] = nx / L; p.ny[i] = ny / L; p.nz[i] = nz / L;
    p.seed[i] = hash(u, w, z) - 0.5;
    const yy = w - z + oy, xx = u + ox;
    x0 = Math.min(x0, xx); x1 = Math.max(x1, xx); y0 = Math.min(y0, yy); y1 = Math.max(y1, yy);
  }
  if (x1 >= 0) { p.bx = x0; p.by = y0; p.bw = x1 - x0 + 1; p.bh = y1 - y0 + 1; }
  for (let w = 0; w < SQ; w++) for (let u = 0; u < S; u++) {
    let t = -1;
    for (let z = H - 1; z >= 0; z--) if (at(u, w, z)) { t = z; break; }
    if (t >= 0) cols.push(u + ox, w + oy, t);
  }
  p.cols = Int16Array.from(cols);
  return p;
}

function getProj(name: string, frame: number, dir: number, dirs: number, cut: number): Proj {
  const key = `${name}:${frame}:${dir}/${dirs}:${cut}`;
  let p = projCache.get(key);
  if (!p) {
    const v = model(name, frame);
    p = project(v, (dir / dirs) * Math.PI * 2, cut >= 1 ? 99 : Math.max(1, Math.ceil(cut * v.H)));
    projCache.set(key, p);
  }
  return p;
}

/** 모델 한 점 (mx, my, mz)이 그려지는 화면 자리: 바닥 가운데에서 얼마나 떨어졌나 (점 크기 k, 방향 dir/dirs).
 *  project()와 같은 회전·누르기. */
export function modelPoint(W: number, D: number, mx: number, my: number, mz: number, dir: number, dirs: number, k: number): [number, number] {
  const a = (dir / dirs) * Math.PI * 2, cs = Math.cos(a), sn = Math.sin(a);
  const x = mx + 0.5 - W / 2, y = my + 0.5 - D / 2;
  return [(cs * x - sn * y) * k, ((sn * x + cs * y) * SQUASH - mz) * k];
}

// ------------------------------------------------------------- 칠하기
function shade(p: Proj, ramps: Record<number, number[][]>, L: Light, torch: number, shadowOn: boolean): ImageData {
  const img = new ImageData(p.w, p.h), d = img.data, T = L.table;
  // 그림자: 기둥마다 꼭대기까지의 점을 해 반대쪽 바닥에 (물체가 없는 곳에만)
  if (shadowOn && L.shadow) {
    const { dx, dy, a } = L.shadow, al = Math.round(a * 255);
    for (let k = 0; k < p.cols.length; k += 3) {
      const u = p.cols[k], w = p.cols[k + 1], t = p.cols[k + 2];
      for (let z = 0; z <= t; z++) {
        const x = Math.round(u + dx * (z + 0.5)), y = Math.round(w + dy * (z + 0.5));
        if (x < 0 || y < 0 || x >= p.w || y >= p.h) continue;
        const i = y * p.w + x;
        if (p.mat[i]) continue;
        d[i * 4] = 14; d[i * 4 + 1] = 12; d[i * 4 + 2] = 26; d[i * 4 + 3] = al;
      }
    }
  }
  for (let y = 0; y < p.h; y++) for (let x = 0; x < p.w; x++) {
    const i = y * p.w + x, m = p.mat[i];
    if (!m) continue;
    const nx = p.nx[i], ny = p.ny[i], nz = p.nz[i];
    // 1) 낮 그림: 면 방향으로 5단계 중 하나 (점마다 조금씩 다른 결, 고른 디더 무늬는 쓰지 않는다)
    const ref = nx * REF[0] + ny * REF[1] + nz * REF[2];
    const f = 2.05 + ref * 1.35 + p.bias[i] * 0.75 + p.seed[i] * 0.6;
    const step = Math.min(4, Math.max(0, Math.round(f)));
    const base = ramps[m][step];
    // 2) 지금 시각: 지형과 같은 빛 표·그늘 표를 비추는 양만큼 섞는다 (면이 고르게 칠해지게 디더 대신 섞기)
    let lit = 0;
    for (const s of L.src) lit += s.w * Math.min(Math.max((nx * s.x + ny * s.y + nz * s.z) / s.div, 0), 1);
    lit = Math.min(lit, 1);
    const tab = (c: number, k: number) => T[c * 4 + k] * (1 - lit) + T[1024 + c * 4 + k] * lit;
    let r = tab(base[0], 0), g = tab(base[1], 1), b = tab(base[2], 2);
    // 3) 횃불: 땅 가까이에 있다. 아래쪽 점일수록, 아래·앞을 보는 면일수록 밝게 (점마다 조금씩 다르게)
    if (torch > 0) {
      const low = p.bh > 1 ? (y - p.by) / (p.bh - 1) : 1;
      const tf = torch * (0.25 + 1.05 * low * low) * (0.5 + 0.5 * Math.max(ny, nz * 0.7)) * (1 + p.seed[i] * 0.9);
      const a = Math.min(Math.max(tf * 1.5 - 0.1, 0), 1);
      r = Math.max(r, r + (base[0] * WARM[0] - r) * a); g = Math.max(g, g + (base[1] * WARM[1] - g) * a); b = Math.max(b, b + (base[2] * WARM[2] - b) * a);
    }
    r = Math.round(r); g = Math.round(g); b = Math.round(b);
    d[i * 4] = r; d[i * 4 + 1] = g; d[i * 4 + 2] = b; d[i * 4 + 3] = 255;
  }
  // 테두리: 물체 바로 바깥 한 점 (그림자 위에도)
  const solid = (x: number, y: number) => x >= 0 && y >= 0 && x < p.w && y < p.h && p.mat[y * p.w + x] !== 0;
  for (let y = 0; y < p.h; y++) for (let x = 0; x < p.w; x++) {
    const i = y * p.w + x;
    if (p.mat[i] || !(solid(x - 1, y) || solid(x + 1, y) || solid(x, y - 1) || solid(x, y + 1))) continue;
    d[i * 4] = OUTLINE[0]; d[i * 4 + 1] = OUTLINE[1]; d[i * 4 + 2] = OUTLINE[2]; d[i * 4 + 3] = 235;
  }
  return img;
}

// ------------------------------------------------------------- 그리기
export interface StackOpts {
  frame?: number;
  dir?: number;              // 방향 번호 (0 = 앞이 +x)
  dirs?: number;             // 방향 수 (유닛 16, 건물 4)
  cut?: number;              // 0~1: 이 높이까지만 (짓는 중)
  torch?: number;            // 0~1 횃불 빛
  shadow?: boolean;
}

export class StackRenderer {
  private ramps = new Map<number, Record<number, number[][]>>();
  private shaded = new Map<string, { key: number; cv: HTMLCanvasElement; p: Proj }>();
  private scaled = new Map<string, HTMLCanvasElement>();

  constructor(private colors: number[][]) {}

  private rampsFor(nid: number) {
    let r = this.ramps.get(nid);
    if (!r) {
      const c = this.colors[nid] ?? [200, 200, 200];
      r = { ...RAMPS, [Mat.CLOTH]: nationRamp(c), [Mat.ROOF]: roofRamp(c) };
      this.ramps.set(nid, r);
    }
    return r;
  }

  /** 칠한 그림 (1배). 반환: 캔버스와 바닥 가운데 점. */
  sprite(name: string, nid: number, L: Light, o: StackOpts = {}): { cv: HTMLCanvasElement; ax: number; ay: number; p: Proj } {
    const frame = o.frame ?? 0, dirs = o.dirs ?? 16, dir = (((o.dir ?? 0) % dirs) + dirs) % dirs;
    const cut = o.cut === undefined || o.cut >= 1 ? 1 : Math.round(o.cut * 8) / 8;
    const torch = Math.round((o.torch ?? 0) * 4) / 4, sh = o.shadow ?? true;
    const key = `${name}:${frame}:${dir}/${dirs}:${cut}|${nid}|${torch}|${sh ? 1 : 0}`;
    let e = this.shaded.get(key);
    if (!e || e.key !== L.key) {
      const p = e?.p ?? getProj(name, frame, dir, dirs, cut);
      const cv = e?.cv ?? document.createElement('canvas');
      cv.width = p.w; cv.height = p.h;
      cv.getContext('2d')!.putImageData(shade(p, this.rampsFor(nid), L, torch, sh), 0, 0);
      if (this.shaded.size > 4000) this.shaded.clear();
      e = { key: L.key, cv, p };
      this.shaded.set(key, e);
    }
    return { cv: e.cv, ax: e.p.ax, ay: e.p.ay, p: e.p };
  }

  /** 화면에 그린다: (sx, sy) = 바닥 가운데의 화면 자리, k = 그림 한 점의 화면 크기. 반환: 물체가 차지한 화면 상자. */
  draw(g: CanvasRenderingContext2D, name: string, nid: number, L: Light, sx: number, sy: number, k: number,
       o: StackOpts = {}): { x: number; y: number; w: number; h: number } {
    const { cv, ax, ay, p } = this.sprite(name, nid, L, o);
    const x = Math.round(sx - ax * k), y = Math.round(sy - ay * k);
    g.drawImage(cv, x, y, cv.width * k, cv.height * k);
    return { x: x + p.bx * k, y: y + p.by * k, w: p.bw * k, h: p.bh * k };
  }

  /** 날고 있는 물체의 땅 그림자: 모양만 어둡게 (1배). 그릴 때 위아래로 눌러 쓴다. */
  silhouette(name: string, o: StackOpts = {}): { cv: HTMLCanvasElement; ax: number; ay: number } {
    const key = `${name}:${o.frame ?? 0}:${o.dir ?? 0}:${o.dirs ?? 16}`;
    let c = this.sil.get(key);
    if (!c) {
      const { cv, ax, ay } = this.sprite(name, 0, NOON, { ...o, shadow: false });
      const t = document.createElement('canvas');
      t.width = cv.width; t.height = cv.height;
      const g = t.getContext('2d')!;
      g.drawImage(cv, 0, 0);
      g.globalCompositeOperation = 'source-in';
      g.fillStyle = 'rgb(14,12,30)';
      g.fillRect(0, 0, t.width, t.height);
      c = { cv: t, ax, ay };
      this.sil.set(key, c);
    }
    return c;
  }
  private sil = new Map<string, { cv: HTMLCanvasElement; ax: number; ay: number }>();

  /** k배로 늘린 그림 (아이콘 등, 그림자 없이 정오 빛). */
  icon(name: string, nid: number, k: number, o: StackOpts = {}): HTMLCanvasElement {
    const key = `${name}:${o.frame ?? 0}:${o.dir ?? 0}:${o.dirs ?? 16}:${nid}:${k}:${o.cut ?? 1}`;
    let c = this.scaled.get(key);
    if (!c) {
      const { cv } = this.sprite(name, nid, NOON, { ...o, shadow: false });
      const b = bounds(cv);
      c = document.createElement('canvas');
      c.width = b.w * k; c.height = b.h * k;
      const g = c.getContext('2d')!;
      g.imageSmoothingEnabled = false;
      g.drawImage(cv, b.x, b.y, b.w, b.h, 0, 0, c.width, c.height);
      this.scaled.set(key, c);
    }
    return c;
  }
}

const NOON = noonLight();

/** 그림의 칠해진 부분 상자. */
function bounds(cv: HTMLCanvasElement) {
  const d = cv.getContext('2d')!.getImageData(0, 0, cv.width, cv.height).data;
  let x0 = cv.width, y0 = cv.height, x1 = -1, y1 = -1;
  for (let y = 0; y < cv.height; y++) for (let x = 0; x < cv.width; x++) {
    if (d[(y * cv.width + x) * 4 + 3] > 0) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  }
  return x1 < 0 ? { x: 0, y: 0, w: 1, h: 1 } : { x: x0, y: y0, w: x1 - x0 + 1, h: y1 - y0 + 1 };
}
