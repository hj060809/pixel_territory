// 계절 칠하기 (CPU): engine/bake/client_ref.py의 BundleRenderer.paint를 그대로 옮겼다.
// numpy에서 float32로 계산하는 곳은 f32(...)로, float64로 계산하는 곳은 JS 배정밀도 그대로 둔다.

import type { Bundle } from '../bundle/tsb.ts';
import { bayer, clip, f32 } from '../noise/numeric.ts';

export interface Painted {
  rgb: Uint8Array;        // (H*W*3) 낮 이미지
  ice: Uint8Array;        // (H*W) 바다 얼음 1
  mat: Uint8Array;        // (H*W) 지금 재질 (눈·얼음 포함, 게임 규칙의 '지금 재질'과 같다)
}

export class SeasonPainter {
  readonly H: number;
  readonly W: number;
  private meta: any;
  private pal: Uint8Array;
  private nMat: number;
  private nShade: number;
  private mat0: Uint8Array;
  private idx0: Uint8Array;
  private idxLand: Uint8Array;
  private amp: Float32Array;
  private ampIce: Float32Array;
  private dither: Float64Array;
  private snowOk: Uint8Array;
  private iceZone: Uint8Array;
  private waterL: Uint8Array;
  private foam: Uint8Array;
  private snowCover: Float32Array;
  private snowOld: Float32Array;
  private seaIce: Float32Array;
  private veg: Uint8Array;
  private tint: Float64Array | null;      // (H*W*3)
  private noise: Float64Array | null;     // (H*W*3)

  constructor(bundle: Bundle, noiseDelta: Float64Array | null) {
    const m = (this.meta = bundle.meta);
    const A = bundle.arrays;
    const H = (this.H = m.H), W = (this.W = m.W), N = H * W;
    const F = m.flags, M = m.materials, s = m.shader;
    this.pal = A.palettes.data as Uint8Array;
    this.nMat = M.n_mat;
    this.nShade = M.n_shade;
    this.mat0 = A.pre.data as Uint8Array;
    this.idx0 = A.idx.data as Uint8Array;
    this.idxLand = A.idx_land.data as Uint8Array;
    const fl = A.flags.data as Uint8Array;
    const T = A.temperature.data as Uint16Array;
    const q16 = m.quant.unit16.scale, qm = m.quant.margin.scale;
    this.amp = new Float32Array(N);
    this.ampIce = new Float32Array(N);
    this.waterL = new Uint8Array(N);
    this.iceZone = new Uint8Array(N);
    this.snowOk = new Uint8Array(N);
    this.foam = new Uint8Array(N);
    this.snowCover = new Float32Array(N);
    this.snowOld = new Float32Array(N);
    this.seaIce = new Float32Array(N);
    const sc = A.snow_cover.data as Int16Array, so = A.snow_old.data as Int16Array, si = A.sea_ice.data as Int16Array;
    for (let i = 0; i < N; i++) {
      const t = f32(T[i] / q16);
      this.amp[i] = clip(f32(f32(f32(0.85) - t) / f32(0.35)), 0, 1);
      this.ampIce[i] = clip(f32(f32(f32(0.35) - t) / f32(0.25)), 0, 1);
      this.waterL[i] = fl[i] & F.water ? 1 : 0;
      this.iceZone[i] = fl[i] & F.ice_zone ? 1 : 0;
      this.snowOk[i] = !this.waterL[i] && this.mat0[i] !== M.ICE ? 1 : 0;
      this.foam[i] = this.waterL[i] && fl[i] & F.near_land ? 1 : 0;
      this.snowCover[i] = sc[i] / qm;
      this.snowOld[i] = so[i] / qm;
      this.seaIce[i] = si[i] / qm;
    }
    this.dither = bayer(m, H, W, 1, 3);
    this.veg = new Uint8Array(this.nMat);
    for (const v of M.vegetation) this.veg[v] = 1;
    if (s.altitude_tint > 0) {
      const alt = A.alt.data as Uint16Array;
      this.tint = new Float64Array(N * 3);
      for (let i = 0; i < N; i++) {
        const a = f32(f32(alt[i] / q16) - f32(0.3));           // float32 고도 - 0.3 (float32)
        for (let c = 0; c < 3; c++) this.tint[i * 3 + c] = a * s.cool[c] * s.altitude_tint;
      }
    } else this.tint = null;
    this.noise = noiseDelta;
  }

  /** weights: (봄, 여름, 가을, 겨울) 비중. null이면 계절 효과 없이 (원래 렌더). */
  paint(weights: number[] | null): Painted {
    const { H, W, meta } = this;
    const N = H * W, M = meta.materials, s = meta.shader;
    const neutral = weights === null;
    const w = neutral ? [0, 1, 0, 0] : weights!;
    const shiftK = (w[3] * 1.0 + w[2] * 0.25 + w[0] * 0.3 - w[1] * 0.3);
    const iceK = (w[3] - 0.6 * w[1] + 0.2 * w[2] + 0.2 * w[0]);
    const rgb = new Uint8Array(N * 3);
    const ice = new Uint8Array(N);
    const matOut = new Uint8Array(N);
    const foamCol = s.foam_color;
    const snowBlend = s.snow_blend, snowBlend4 = 4 * s.snow_blend;
    for (let i = 0; i < N; i++) {
      let mat = this.mat0[i], idx = this.idx0[i], variant = 1;
      const a = this.amp[i];
      if (!neutral) {
        const u = this.dither[i];
        const pWi = w[3] * a, pAu = w[2] * a, pSp = w[0] * a;
        variant = u < pWi ? 3 : u < pWi + pAu ? 2 : u < pWi + pAu + pSp ? 0 : 1;
      }
      const shift = neutral ? 0 : a * shiftK * 0.10;
      const cover = this.snowCover[i] + shift / snowBlend;
      const old = this.snowOld[i] - shift / snowBlend4;
      if (this.snowOk[i] && cover > 0) {
        mat = this.iceZone[i] ? M.ICE : old > 0 ? M.SNOW_OLD : M.SNOW;
        variant = 1;
      }
      const iceShift = neutral ? 0 : this.ampIce[i] * iceK * 0.4;
      const isIce = this.waterL[i] && this.seaIce[i] + iceShift > 0;
      if (isIce) {
        mat = M.SEA_ICE;
        idx = this.idxLand[i];
        variant = 1;
        ice[i] = 1;
      }
      matOut[i] = mat;
      const p = ((variant * this.nMat + mat) * this.nShade + idx) * 3;
      for (let c = 0; c < 3; c++) {
        let v = this.foam[i] && !isIce && s.foam ? foamCol[c] : this.pal[p + c];
        if (this.noise) v += this.noise[i * 3 + c];
        if (this.tint && this.veg[mat]) v += this.tint[i * 3 + c];
        rgb[i * 3 + c] = v <= 0 ? 0 : v >= 255 ? 255 : Math.trunc(v);
      }
    }
    return { rgb, ice, mat: matOut };
  }
}
