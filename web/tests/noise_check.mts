// 옮긴 노이즈가 파이썬과 같은 값을 내는지: node --experimental-strip-types tests/noise_check.mts
import { OpenSimplex } from '../src/noise/opensimplex.ts';
import { readFileSync } from 'node:fs';
const v = JSON.parse(readFileSync(new URL('../../assets/test/noise_vectors.json', import.meta.url), 'utf8'));
const gens: Record<number, OpenSimplex> = {};
let exact = 0, maxd = 0;
for (const e of v.noise2) {
  const g = (gens[e.seed] ??= new OpenSimplex(e.seed));
  const r = g.noise2(e.x, e.y);
  if (r === e.v) exact++;
  maxd = Math.max(maxd, Math.abs(r - e.v));
}
console.log(`noise2: ${exact}/${v.noise2.length} 같음, 가장 큰 차이 ${maxd}`);
const t0 = performance.now();
const g = new OpenSimplex(0);
let acc = 0;
for (let i = 0; i < 2_000_000; i++) acc += g.noise2(i * 0.013, i * 0.007);
console.log(`속도: 200만 번 ${(performance.now() - t0).toFixed(0)} ms (${acc.toFixed(3)})`);
