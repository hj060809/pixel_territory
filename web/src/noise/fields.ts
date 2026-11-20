// 지도 내용과 상관없는 노이즈 (지도 크기와 고정 시드로만 정해진다). 파이썬과 같은 값:
// - fbm: engine/render/shader.py의 _fbm (색 노이즈)
// - gridNoise: engine/render/water.py의 grid_noise (물결 흐름, 마루 텍스처)

import { OpenSimplex } from './opensimplex.ts';

/** shader._fbm: 칸 (y, x) = Σ amp·noise2(x/scale·freq + offset·freq, ...) / Σ amp. 반환 Float64Array(H*W). */
export function fbm(gen: OpenSimplex, H: number, W: number, scale: number, octaves: number, offset: number): Float64Array {
  const out = new Float64Array(H * W);
  const xs = new Float64Array(W), ys = new Float64Array(H);
  for (let x = 0; x < W; x++) xs[x] = x / scale + offset;
  for (let y = 0; y < H; y++) ys[y] = y / scale + offset;
  let amp = 1.0, freq = 1.0, total = 0.0;
  for (let o = 0; o < octaves; o++) {
    for (let y = 0; y < H; y++) {
      const yy = ys[y] * freq;
      const row = y * W;
      for (let x = 0; x < W; x++) out[row + x] += amp * gen.noise2(xs[x] * freq, yy);
    }
    total += amp;
    amp *= 0.5;
    freq *= 2.0;
  }
  for (let i = 0; i < out.length; i++) out[i] /= total;
  return out;
}

/** water.grid_noise: ax = x / (scale·stretch) + off, ay = y / scale + off, 옥타브마다 두 배. 반환 Float64Array(h*w). */
export function gridNoise(gen: OpenSimplex, h: number, w: number, scale: number, off: number,
                          octaves = 1, stretch = 1.0): Float64Array {
  const out = new Float64Array(h * w);
  const ax = new Float64Array(w), ay = new Float64Array(h);
  for (let x = 0; x < w; x++) ax[x] = x / (scale * stretch) + off;
  for (let y = 0; y < h; y++) ay[y] = y / scale + off;
  let amp = 1.0, total = 0.0;
  for (let o = 0; o < octaves; o++) {
    for (let y = 0; y < h; y++) {
      const yy = ay[y];
      const row = y * w;
      for (let x = 0; x < w; x++) out[row + x] += amp * gen.noise2(ax[x], yy);
    }
    total += amp;
    for (let x = 0; x < w; x++) ax[x] *= 2;
    for (let y = 0; y < h; y++) ay[y] *= 2;
    amp *= 0.5;
  }
  for (let i = 0; i < out.length; i++) out[i] /= total;
  return out;
}

/** 셰이더 색 노이즈 RGB 변화량 (layers['noise_delta']와 같다, 배정밀도). 반환 Float64Array(H*W*3). */
export function colorNoiseDelta(meta: any): Float64Array | null {
  const s = meta.shader;
  const H = meta.H, W = meta.W;
  if (!(s.color_noise > 0)) return null;
  const gen = new OpenSimplex(s.seed);
  const warm = fbm(gen, H, W, s.color_noise_scale, 3, 0.0);
  const bright = fbm(gen, H, W, s.color_noise_scale * 0.7, 3, 1000.0);
  const out = new Float64Array(H * W * 3);
  for (let i = 0; i < H * W; i++) {
    for (let c = 0; c < 3; c++) {
      // (warm·WARM + bright·BRIGHT·0.6)·color_noise  (numpy와 같은 순서)
      out[i * 3 + c] = (warm[i] * s.warm[c] + bright[i] * s.bright[c] * 0.6) * s.color_noise;
    }
  }
  return out;
}

export const WATER_FIELDS = ['angle_a', 'angle_b', 'speed', 'phase', 'phase2', 'density', 'surf'] as const;
export type WaterFieldName = typeof WATER_FIELDS[number];

/** water.water_noise_fields: 이름 → Float64Array(H*W). */
export function waterNoiseFields(H: number, W: number, p: any): Record<WaterFieldName, Float64Array> {
  const gen = new OpenSimplex(p.seed + 31);
  const fs = p.flow_scale;
  return {
    angle_a: gridNoise(gen, H, W, fs, 100.0, 2),
    angle_b: gridNoise(gen, H, W, fs * 3, 150.0),
    speed: gridNoise(gen, H, W, fs * 0.7, 200.0),
    phase: gridNoise(gen, H, W, 60.0, 300.0),
    phase2: gridNoise(gen, H, W, 45.0, 350.0),
    density: gridNoise(gen, H, W, 90.0, 450.0, 2),
    surf: gridNoise(gen, H, W, 22.0, 800.0, 2),
  };
}

/** water.ridge_noise: 마루 텍스처의 바탕 노이즈 (side, side). */
export function ridgeNoise(side: number, size: number, length: number, off: number, p: any): Float64Array {
  return gridNoise(new OpenSimplex(p.seed + 31), side, side, size, off, 2, length);
}
