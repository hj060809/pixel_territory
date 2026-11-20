// 격자 계산 도우미 (scipy.ndimage 대신): 유클리드 거리 변환, 가우시안 흐림, 기울기.

/** distance_transform_edt: 칸마다 가장 가까운 0 칸까지의 거리 (mask가 1인 칸에서). Felzenszwalb 방법. */
export function edt(mask: Uint8Array, W: number, H: number): Float64Array {
  const INF = 1e20;
  const f = new Float64Array(W * H);
  for (let i = 0; i < W * H; i++) f[i] = mask[i] ? INF : 0;
  const line = (src: Float64Array, n: number, d: Float64Array) => {
    const v = new Int32Array(n), z = new Float64Array(n + 1);
    let k = 0;
    v[0] = 0; z[0] = -INF; z[1] = INF;
    for (let q = 1; q < n; q++) {
      let s = ((src[q] + q * q) - (src[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]);
      while (s <= z[k]) { k--; s = ((src[q] + q * q) - (src[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k]); }
      k++; v[k] = q; z[k] = s; z[k + 1] = INF;
    }
    k = 0;
    for (let q = 0; q < n; q++) {
      while (z[k + 1] < q) k++;
      d[q] = (q - v[k]) * (q - v[k]) + src[v[k]];
    }
  };
  const col = new Float64Array(H), colOut = new Float64Array(H);
  for (let x = 0; x < W; x++) {
    for (let y = 0; y < H; y++) col[y] = f[y * W + x];
    line(col, H, colOut);
    for (let y = 0; y < H; y++) f[y * W + x] = colOut[y];
  }
  const row = new Float64Array(W), rowOut = new Float64Array(W);
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) row[x] = f[y * W + x];
    line(row, W, rowOut);
    for (let x = 0; x < W; x++) f[y * W + x] = Math.sqrt(rowOut[x]);
  }
  return f;
}

/** gaussian_filter (반사 가장자리, 4σ에서 자른다). */
export function gaussian(src: Float64Array, W: number, H: number, sigma: number): Float64Array {
  const r = Math.floor(4 * sigma + 0.5);
  const k = new Float64Array(2 * r + 1);
  let sum = 0;
  for (let i = -r; i <= r; i++) { k[i + r] = Math.exp(-0.5 * (i / sigma) ** 2); sum += k[i + r]; }
  for (let i = 0; i < k.length; i++) k[i] /= sum;
  const refl = (i: number, n: number) => { while (i < 0 || i >= n) i = i < 0 ? -i - 1 : 2 * n - i - 1; return i; };
  const tmp = new Float64Array(W * H), out = new Float64Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let s = 0;
    for (let i = -r; i <= r; i++) s += k[i + r] * src[y * W + refl(x + i, W)];
    tmp[y * W + x] = s;
  }
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    let s = 0;
    for (let i = -r; i <= r; i++) s += k[i + r] * tmp[refl(y + i, H) * W + x];
    out[y * W + x] = s;
  }
  return out;
}

/** np.gradient: (gy, gx) 가운데 차분, 가장자리는 한쪽 차분. */
export function gradient(a: Float64Array, W: number, H: number): [Float64Array, Float64Array] {
  const gy = new Float64Array(W * H), gx = new Float64Array(W * H);
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const i = y * W + x;
    gx[i] = x === 0 ? a[i + 1] - a[i] : x === W - 1 ? a[i] - a[i - 1] : (a[i + 1] - a[i - 1]) / 2;
    gy[i] = y === 0 ? a[i + W] - a[i] : y === H - 1 ? a[i] - a[i - W] : (a[i + W] - a[i - W]) / 2;
  }
  return [gy, gx];
}

/** 씨앗을 주는 난수 (mulberry32) + 정규분포. */
export class Rng {
  private s: number;
  constructor(seed: number) { this.s = seed >>> 0; }
  next(): number {
    let t = (this.s += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }
  uniform(a: number, b: number) { return a + (b - a) * this.next(); }
  int(a: number, b: number) { return a + Math.floor(this.next() * (b - a)); }     // [a, b)
  normal(mu = 0, sd = 1) {
    const u = 1 - this.next(), v = this.next();
    return mu + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
}
