// 웹 CPU 단계(계절 칠하기 + 물결)가 파이썬 사양(client_ref)과 같은지.
// 먼저: python tools/make_terrain_vectors.py   그다음: node --experimental-strip-types web/tests/terrain_check.mts [지도]
import { readFileSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { parseBundle } from '../src/bundle/tsb.ts';
import { colorNoiseDelta } from '../src/noise/fields.ts';
import { SeasonPainter } from '../src/terrain/season.ts';
import { WaterAnimator } from '../src/terrain/water.ts';

const name = process.argv[2] ?? 'default';
const root = new URL(`../../assets/`, import.meta.url);
const raw = gunzipSync(readFileSync(new URL(`maps/${name}/bundle.tsb`, root)));
const bundle = parseBundle(raw.buffer.slice(raw.byteOffset, raw.byteOffset + raw.byteLength));
let t0 = performance.now();
const noise = colorNoiseDelta(bundle.meta);
console.log(`색 노이즈 ${(performance.now() - t0).toFixed(0)} ms`);
t0 = performance.now();
const painter = new SeasonPainter(bundle, noise);
console.log(`계절 칠하기 준비 ${(performance.now() - t0).toFixed(0)} ms`);
t0 = performance.now();
const water = new WaterAnimator(bundle);
console.log(`물결 준비 ${(performance.now() - t0).toFixed(0)} ms`);
const states = JSON.parse(readFileSync(new URL(`test/terrain/${name}/states.json`, root), 'utf8'));
let allExact = true;
for (const st of states) {
  let t1 = performance.now();
  const { rgb, ice } = painter.paint(st.season);
  const tPaint = performance.now() - t1;
  const base = rgb.slice();
  let tWave = 0;
  if (st.wave_t !== null) {
    t1 = performance.now();
    water.apply(base, st.wave_t);
    tWave = performance.now() - t1;
    if (st.season !== null) for (let i = 0; i < ice.length; i++) if (ice[i]) for (let c = 0; c < 3; c++) base[i * 3 + c] = rgb[i * 3 + c];
  }
  const ref = readFileSync(new URL(`test/terrain/${name}/${st.name}.rgb`, root));
  let diff = 0;
  for (let i = 0; i < base.length; i += 3) if (base[i] !== ref[i] || base[i + 1] !== ref[i + 1] || base[i + 2] !== ref[i + 2]) diff++;
  allExact &&= diff === 0;
  console.log(`${st.name.padEnd(14)} 다른 칸 ${diff} / ${base.length / 3}  (칠하기 ${tPaint.toFixed(1)} ms, 물결 ${tWave.toFixed(1)} ms)`);
}
console.log(allExact ? '결과: 모두 같다' : '결과: 다른 칸이 있다');
