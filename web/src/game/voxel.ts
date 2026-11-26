// 스프라이트 스태킹용 복셀 모델: 바닥(z=0)부터 쌓은 층. 한 칸 = 그림 한 점.
// 재질마다 지형 팔레트(engine/render/shader.py DEFAULT_RAMPS)와 같은 방식의 5단계 색 (어두운 쪽은 푸른/보랏빛 그늘).
// 나라 색 재질은 그 나라 색에서 같은 방식으로 단계를 만든다.

export const Mat = {
  EMPTY: 0, WOOD: 1, WOOD_D: 2, THATCH: 3, STONE: 4, PLASTER: 5, TILE: 6, SKIN: 7, METAL: 8, LEATHER: 9, HORSE: 10, HORSE_D: 11, CROP: 12, LEAF: 13, SAIL: 14, DARK: 15, CLOTH: 16, ROOF: 17, GOLD: 18, DRAGON: 19, MEMBRANE: 20, GLOW: 21, WING: 22, BASALT: 23, STRAW: 24, SHELL: 25, HIDE: 26, SULFUR: 27, CAMEL: 28,
} as const;
export type Mat = number;

const hex = (s: string) => [parseInt(s.slice(1, 3), 16), parseInt(s.slice(3, 5), 16), parseInt(s.slice(5, 7), 16)];
const ramp = (...c: string[]) => c.map(hex);

/** 재질 → 5단계 색 (나라 색 재질 CLOTH, ROOF는 nationRamp로). */
export const RAMPS: Record<number, number[][]> = {
  [Mat.WOOD]: ramp('#3b2a2c', '#5e4235', '#835f40', '#a8814f', '#c9a66a'),
  [Mat.WOOD_D]: ramp('#251c24', '#3f2c2b', '#5b3f31', '#77553c', '#936d48'),
  [Mat.THATCH]: ramp('#3a3424', '#5f5a2f', '#8c8238', '#b5a64a', '#d6c978'),
  [Mat.STONE]: ramp('#3a3540', '#5c5458', '#827870', '#a69c8c', '#cbc2ae'),
  [Mat.PLASTER]: ramp('#3a3540', '#6b6468', '#a39b92', '#cfc6b0', '#ece5d2'),
  [Mat.TILE]: ramp('#2d2331', '#5a3537', '#87503f', '#ad6d4f', '#cf9468'),
  [Mat.SKIN]: ramp('#3b2a2c', '#77503f', '#ab7a5a', '#d4a27a', '#efc59b'),
  [Mat.METAL]: ramp('#2a2535', '#4e4859', '#77707e', '#a49ea6', '#d2ccc8'),
  [Mat.LEATHER]: ramp('#2c2026', '#4a3128', '#6b4630', '#8a5e3b', '#a87a4c'),
  [Mat.HORSE]: ramp('#2c2026', '#4e3328', '#734a32', '#98663f', '#b98552'),
  [Mat.HORSE_D]: ramp('#1a1520', '#2b2028', '#3f2e32', '#553d3c', '#6b4d46'),
  [Mat.CROP]: ramp('#322f24', '#565031', '#7f7542', '#a69b59', '#c5bd83'),
  [Mat.LEAF]: ramp('#13242a', '#1a3a32', '#255437', '#386f3b', '#5a8c42'),
  [Mat.SAIL]: ramp('#4a4550', '#7d7468', '#aea28a', '#d4c8a8', '#efe6cc'),
  [Mat.DARK]: ramp('#120e16', '#1a141c', '#221a22', '#2c2228', '#362a2e'),
  [Mat.GOLD]: ramp('#3a2f24', '#6b5530', '#a3843c', '#cfae52', '#eed585'),
  [Mat.DRAGON]: ramp('#161b2e', '#26304e', '#3a4c78', '#5a74a6', '#86a2cc'),     // 서리 드래곤 비늘
  [Mat.MEMBRANE]: ramp('#3a4460', '#5c6e94', '#8aa0c4', '#b4c8e2', '#dae6f2'),   // 배와 날개막
  [Mat.GLOW]: ramp('#9adcf0', '#b4ecfa', '#cff6ff', '#e6fbff', '#ffffff'),       // 눈, 얼음 기둥 (어두워도 밝게)
  [Mat.WING]: ramp('#24365e', '#3a5f96', '#6a9ccc', '#a4d0ee', '#dcf2fc'),       // 얼음빛 날개막, 가시
  [Mat.BASALT]: ramp('#0c0b12', '#1a1822', '#2a2833', '#3c3946', '#56525e'),     // 검은 현무암 (둥지)
  [Mat.STRAW]: ramp('#3a2e24', '#6b5436', '#9a7c4a', '#c4a468', '#e2c98e'),      // 밀짚 (둥지)
  [Mat.SHELL]: ramp('#2e2420', '#5a4634', '#8a6c4c', '#b49068', '#d6b88c'),      // 바위거북 등껍질 (사암빛 바위)
  [Mat.HIDE]: ramp('#24221e', '#46423a', '#6c6656', '#928a74', '#b8ae94'),      // 바위거북 살 (회갈색 가죽)
  [Mat.SULFUR]: ramp('#4a4018', '#7e6c1c', '#b8a024', '#dcc840', '#f4ec8c'),      // 유황 (웅덩이, 결정)
  [Mat.CAMEL]: ramp('#33261f', '#664532', '#9a6c46', '#c49662', '#e2bd88'),       // 낙타 털 (모래빛 황갈색)
};

const TONE = [42, 37, 53];                  // 지형 그늘과 같은 보랏빛
const mix = (a: number[], b: number[], t: number) => a.map((v, i) => Math.round(v * (1 - t) + b[i] * t));

/** 나라 색 → 5단계 (옷·깃발). */
export function nationRamp(c: number[]): number[][] {
  return [mix(c, TONE, 0.78), mix(c, TONE, 0.5), mix(c, TONE, 0.2), c.map((v) => Math.round(v)), mix(c, [250, 238, 214], 0.35)];
}

/** 지붕: 기와와 나라 색을 섞는다 (멀리서도 누구 건물인지 보이게, 지형과 어울리게). */
export function roofRamp(c: number[]): number[][] {
  const n = nationRamp(c), t = RAMPS[Mat.TILE];
  return n.map((v, i) => mix(t[i], v, 0.6));
}

export class Vol {
  readonly mat: Uint8Array;
  readonly bias: Int8Array;
  constructor(readonly W: number, readonly D: number, readonly H: number) {
    this.mat = new Uint8Array(W * D * H);
    this.bias = new Int8Array(W * D * H);
  }

  private idx(x: number, y: number, z: number) { return (z * this.D + y) * this.W + x; }
  inside(x: number, y: number, z: number) { return x >= 0 && y >= 0 && z >= 0 && x < this.W && y < this.D && z < this.H; }
  get(x: number, y: number, z: number) { return this.inside(x, y, z) ? this.mat[this.idx(x, y, z)] : 0; }

  set(x: number, y: number, z: number, m: Mat, b = 0) {
    x = Math.round(x); y = Math.round(y); z = Math.round(z);
    if (!this.inside(x, y, z)) return;
    const i = this.idx(x, y, z);
    this.mat[i] = m;
    this.bias[i] = b;
  }

  /** 상자 (양 끝 포함). */
  box(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number, m: Mat, b = 0) {
    for (let z = z0; z <= z1; z++) for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) this.set(x, y, z, m, b);
  }

  /** 속이 빈 벽 상자 (두께 1). */
  walls(x0: number, y0: number, z0: number, x1: number, y1: number, z1: number, m: Mat, b = 0) {
    for (let z = z0; z <= z1; z++) for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) {
      if (x === x0 || x === x1 || y === y0 || y === y1) this.set(x, y, z, m, b);
    }
  }

  /** 맞배지붕: 용마루가 x 방향 (alongX) 또는 y 방향. 처마가 h만큼 올라간다. */
  gable(x0: number, y0: number, x1: number, y1: number, z0: number, m: Mat, alongX = true, b = 0) {
    const span = alongX ? y1 - y0 : x1 - x0;
    const half = span / 2;
    for (let s = 0; s <= span; s++) {
      const up = Math.floor(Math.min(s, span - s) * 0.8);
      const edge = s === 0 || s === span;
      for (let dz = 0; dz <= up; dz++) {
        for (let t = alongX ? x0 : y0; t <= (alongX ? x1 : y1); t++) {
          const x = alongX ? t : x0 + s, y = alongX ? y0 + s : t;
          // 속까지 채운다 (껍데기만이면 비스듬히 볼 때 계단 사이로 비쳐 검은 줄이 생긴다)
          this.set(x, y, z0 + dz, m, (edge ? -1 : 0) + (Math.abs(s - half) < 0.6 ? 1 : 0) + b);
        }
      }
    }
  }

  /** 세운 원기둥 (가운데 cx, cy, 반지름 r). */
  cyl(cx: number, cy: number, r: number, z0: number, z1: number, m: Mat, b = 0, hollow = false) {
    for (let z = z0; z <= z1; z++) for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
      const d = Math.hypot(x + 0.5 - cx, y + 0.5 - cy);
      if (d <= r && (!hollow || d > r - 1.2)) this.set(x, y, z, m, b);
    }
  }

  /** 원뿔 (지붕): 아래 반지름 r에서 위로 좁아진다. */
  cone(cx: number, cy: number, r: number, z0: number, h: number, m: Mat, b = 0) {
    for (let dz = 0; dz < h; dz++) this.cyl(cx, cy, r * (1 - dz / h), z0 + dz, z0 + dz, m, b);
  }

  /** 누운 통나무 (x 방향). */
  log(x0: number, x1: number, y: number, z: number, m: Mat = Mat.WOOD) {
    for (let x = x0; x <= x1; x++) {
      this.set(x, y, z, m, x === x0 || x === x1 ? 1 : 0);
      this.set(x, y + 1, z, m, -1);
    }
  }
}
