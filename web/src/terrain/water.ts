// 물결과 해안 거품 (CPU): engine/bake/client_ref.py의 BundleRenderer(_water_prepare, waves)를 옮겼다.
// numba/numpy의 float32·float64 섞인 계산을 그대로 따른다 (f32 = float32 한 번, 나머지는 배정밀도).

import type { Bundle } from '../bundle/tsb.ts';
import { WATER_FIELDS, ridgeNoise, waterNoiseFields } from '../noise/fields.ts';
import { bayer, clip, f32, rint } from '../noise/numeric.ts';

export class WaterAnimator {
  readonly empty: boolean;
  private meta: any;
  private n = 0;
  private flat!: Int32Array;              // 물결 칸의 지도 위치 (y*W + x)
  private vx!: Float32Array;
  private vy!: Float32Array;
  private phase!: Float32Array;
  private phase2!: Float32Array;
  private ow!: Float32Array;
  private off0!: Int32Array;
  private off1!: Int32Array;
  private base!: Int32Array;
  private density!: Float32Array;
  private dissolve!: Float32Array;
  private surfPhase!: Float32Array;
  private depthN!: Float32Array;
  private foamZone!: Uint8Array;
  private rimZone!: Uint8Array;
  private widx!: Uint8Array;
  private wdelta!: Int16Array;            // (n*3)
  private wThresh!: Float32Array;
  private ramp!: number[][];
  private tex1!: Float32Array;
  private tex2!: Float32Array;
  private tw = 0;
  private jumpMask = 0;
  private cut = 0;
  private band = 0;
  private r1!: Float32Array;
  private r2!: Float32Array;

  constructor(bundle: Bundle, progress: (t: string) => void = () => {}) {
    const m = (this.meta = bundle.meta);
    const Wm = m.water, sc = Wm.scalars;
    this.empty = !!sc.empty;
    if (this.empty) return;
    const p = Wm.params, A = bundle.arrays;
    const H = m.H, W = m.W;
    const fl = A.flags.data as Uint8Array;
    const flat: number[] = [];
    for (let i = 0; i < H * W; i++) if (fl[i] & m.flags.wave) flat.push(i);
    const n = (this.n = flat.length);
    this.flat = Int32Array.from(flat);
    progress('물결 노이즈 만드는 중...');
    const F = waterNoiseFields(H, W, p);
    const at: Record<string, Float32Array> = {};
    for (const name of WATER_FIELDS) {
      const src = F[name], dst = new Float32Array(n);
      for (let k = 0; k < n; k++) dst[k] = src[flat[k]];
      at[name] = dst;
    }
    const PI = f32(Math.PI);
    this.vx = new Float32Array(n); this.vy = new Float32Array(n);
    this.phase = new Float32Array(n); this.phase2 = new Float32Array(n);
    this.ow = new Float32Array(n); this.density = new Float32Array(n); this.surfPhase = new Float32Array(n);
    const k0 = new Int32Array(n);
    const nOr = Wm.n_orient;
    const piOver = f32(Math.PI / nOr), halfPi = f32(Math.PI / 2);
    for (let k = 0; k < n; k++) {
      // angle = at_a·π·1.6 + at_b·π  (float32)
      const angle = f32(f32(f32(at.angle_a[k] * PI) * f32(1.6)) + f32(at.angle_b[k] * PI));
      const speed = f32(f32(p.flow_speed) * f32(f32(0.9) + f32(f32(0.4) * at.speed[k])));
      const travel = f32(speed * f32(p.flow_period));
      this.vx[k] = f32(Math.cos(angle)) * travel;
      this.vy[k] = f32(Math.sin(angle)) * travel;
      this.phase[k] = f32(f32(at.phase[k] * f32(0.5)) + f32(0.5));
      this.phase2[k] = f32(f32(at.phase2[k] * f32(0.5)) + f32(0.5));
      let crest = f32(angle + halfPi);
      crest = f32(((crest % PI) + PI) % PI);
      const pos = f32(crest / piOver);
      const fl0 = Math.floor(pos);
      k0[k] = ((fl0 % nOr) + nOr) % nOr;
      this.ow[k] = f32(pos - fl0);
      this.density[k] = clip(f32(f32(0.6) + f32(at.density[k] * f32(1.2))), f32(0.15), 1);
      this.surfPhase[k] = f32(f32(at.surf[k] * f32(0.6)) + f32(0.5));
    }
    const margin = sc.margin, jump = Wm.jump;
    const th = H + 2 * margin + jump, tw = W + 2 * margin + jump;
    this.tw = tw;
    this.jumpMask = jump - 1;
    const tsize = th * tw;
    progress('물결 마루 텍스처 만드는 중...');
    this.tex1 = this.crest(th, tw, p.ripple_size, p.ripple_length, 400.0, sc.std1, nOr, p);
    this.tex2 = this.crest(th, tw, p.ripple_size * 1.8, p.ripple_length * 0.8, 600.0, sc.std2, nOr, p);
    this.base = new Int32Array(n); this.off0 = new Int32Array(n); this.off1 = new Int32Array(n);
    const diss = bayer(m, H, W, 2, 1), thr = bayer(m, H, W);
    this.dissolve = new Float32Array(n); this.wThresh = new Float32Array(n);
    this.depthN = new Float32Array(n); this.foamZone = new Uint8Array(n); this.rimZone = new Uint8Array(n);
    this.widx = new Uint8Array(n); this.wdelta = new Int16Array(n * 3);
    const wshore = A.wshore.data as Uint8Array, wdepth = A.wdepth.data as Float32Array;
    const widx = A.widx.data as Uint8Array, wdelta = A.wdelta.data as Int8Array;
    const dref = 0.35 * sc.d_ref;
    for (let k = 0; k < n; k++) {
      const i = flat[k], y = (i / W) | 0, x = i % W;
      this.base[k] = (y + margin) * tw + (x + margin);
      this.off0[k] = k0[k] * tsize;
      this.off1[k] = ((k0[k] + 1) % nOr) * tsize;
      this.dissolve[k] = diss[i];
      this.wThresh[k] = thr[i];
      this.foamZone[k] = wshore[i] <= 3 ? 1 : 0;
      this.rimZone[k] = wshore[i] <= 5 ? 1 : 0;
      this.depthN[k] = f32(wdepth[i] / dref);
      this.widx[k] = widx[i];
      for (let c = 0; c < 3; c++) this.wdelta[k * 3 + c] = wdelta[c * H * W + i];
    }
    this.ramp = Wm.ramp;
    this.cut = sc.cut;
    this.band = sc.band;
    this.r1 = new Float32Array(n);
    this.r2 = new Float32Array(n);
  }

  /** client_ref._crest: 바탕 노이즈로 가는 마루를 만들고 N방향으로 돌려 읽는다. 반환 (nOr * th * tw). */
  private crest(th: number, tw: number, size: number, length: number, off: number, std: number, nOr: number, p: any) {
    const side = Math.ceil(Math.hypot(th, tw)) + 4;
    const n = ridgeNoise(side, size, length, off, p);
    const ridge = new Float32Array(side * side);          // 저장은 float32 (out[k] = ridge[sy, sx])
    const lim = std * 1.2;
    for (let i = 0; i < n.length; i++) {
      const r = clip(1.0 - Math.abs(n[i]) / lim, 0, 1);
      ridge[i] = r * r;
    }
    const out = new Float32Array(nOr * th * tw);
    const hy = f32(th / 2), hx = f32(tw / 2), half = side / 2;
    for (let k = 0; k < nOr; k++) {
      const b = (Math.PI * k) / nOr;
      const cb = Math.cos(b), sb = Math.sin(b);
      const base = k * th * tw;
      for (let y = 0; y < th; y++) {
        const yy = f32(y - hy);
        for (let x = 0; x < tw; x++) {
          const xx = f32(x - hx);
          const u = xx * cb + yy * sb;
          const v = -xx * sb + yy * cb;
          const sx = clip(rint(u + half), 0, side - 1);
          const sy = clip(rint(v + half), 0, side - 1);
          out[base + y * tw + x] = ridge[sy * side + sx];
        }
      }
    }
    return out;
  }

  /** water._sample_loop 한 겹. */
  private layer(tex: Float32Array, phase: Float32Array, t: number, speedMul: number, out: Float32Array) {
    const period = this.meta.water.params.flow_period;
    const uAdd = f32((t / period) * speedMul);
    const sm = f32(speedMul);
    const { base, off0, off1, ow, vx, vy, dissolve, tw, jumpMask } = this;
    for (let i = 0; i < this.n; i++) {
      let best = 0, wFirst = 0;
      const ph = f32(phase[i] + uAdd);
      for (let s = 0; s < 2; s++) {
        const v = ph + 0.5 * s;
        const cf = Math.floor(v);
        const c = cf | 0;
        const f = v - cf;
        const w = 1.0 - Math.abs(2.0 * f - 1.0);
        const jx = (c * 97 + 53 * s) & jumpMask;
        const jy = (c * 61 + 29 * s) & jumpMask;
        const d = (f - 0.5) * sm;
        const ox = rint(vx[i] * d), oy = rint(vy[i] * d);
        const idx = base[i] + (jy - oy) * tw + (jx - ox);
        const val = tex[idx + off0[i]] * (1.0 - ow[i]) + tex[idx + off1[i]] * ow[i];
        if (s === 0) { wFirst = w; best = val; }
        else if (!(wFirst > dissolve[i])) best = val;
      }
      out[i] = best;            // float32로 저장
    }
  }

  /** rgb(낮 이미지, H*W*3)에 t초 순간의 물결과 해안 거품을 입힌다 (제자리). */
  apply(rgb: Uint8Array, t: number): void {
    if (this.empty) return;
    const p = this.meta.water.params;
    this.layer(this.tex1, this.phase, t, 1.0, this.r1);
    this.layer(this.tex2, this.phase2, t, 0.6, this.r2);
    const cut = f32(this.cut), band = f32(this.band), k85 = f32(0.85);
    const tAdd = f32(t / p.surf_period);
    const k03 = f32(1 / 0.3), k07 = f32(1 / 0.7), k035 = f32(1 / 0.35), c03 = f32(0.3), reach = f32(p.surf_reach);
    const c13 = f32(1.3);
    const ramp = this.ramp, nShades = ramp.length;
    const foamCol = this.meta.shader.foam_color;
    for (let k = 0; k < this.n; k++) {
      const r = Math.max(this.r1[k], f32(this.r2[k] * k85));
      const pr = f32(clip(f32(f32(r - cut) / band), 0, 1) * this.density[k]);
      const thr = this.wThresh[k];
      let lift = pr > thr ? 1 : 0;
      let s = f32(this.surfPhase[k] + tAdd);
      s = f32(s - Math.floor(s));
      let breath = s < 0.3 ? f32(s * k03) : f32(f32(1.0 - s) * k07);
      breath = f32(breath * f32(Math.sqrt(breath)));
      const wet = f32(f32(f32(c03 + f32(reach * breath)) * k035) - this.depthN[k]);
      const foam = this.foamZone[k] && wet > thr;
      const rim = this.rimZone[k] && !foam && wet > f32(thr - c13);
      if (rim) lift = 1;
      const i = this.flat[k] * 3;
      if (foam) {
        rgb[i] = foamCol[0]; rgb[i + 1] = foamCol[1]; rgb[i + 2] = foamCol[2];
        continue;
      }
      const w0 = this.widx[k];
      const kk = Math.min(w0 + lift, nShades - 1);
      if (kk !== w0) {
        for (let c = 0; c < 3; c++) rgb[i + c] = clip(ramp[kk][c] + this.wdelta[k * 3 + c], 0, 255);
      }
    }
  }
}
