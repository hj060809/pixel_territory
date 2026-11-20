// 비교 페이지: 데모 지도마다 기준 그림(파이썬 engine.render.frame)과 같은 순간을 브라우저로 그려 칸 단위로 비교한다.
// 주소: /parity.html[?maps=default,continent]   결과: window.__parity = { done, results: [...] }

import { TerrainScene } from '../terrain/scene.ts';

interface Result { map: string; ref: string; diff: number; total: number; maxd: number; ms: number }

async function decodePng(url: string): Promise<Uint8ClampedArray> {
  const bmp = await createImageBitmap(await (await fetch(url)).blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  const c = new OffscreenCanvas(bmp.width, bmp.height);
  const g = c.getContext('2d', { colorSpace: 'srgb' })!;
  g.drawImage(bmp, 0, 0);
  return g.getImageData(0, 0, bmp.width, bmp.height).data;
}

async function main() {
  const out: Result[] = [];
  (window as any).__parity = { done: false, results: out };
  const log = document.createElement('pre');
  document.body.appendChild(log);
  const listing = await (await fetch('/assets/maps/maps.json')).json();
  const want = new URLSearchParams(location.search).get('maps')?.split(',');
  const canvas = document.createElement('canvas');
  const gl = canvas.getContext('webgl2', { antialias: false })!;
  for (const m of listing.maps) {
    if (want && !want.includes(m.key)) continue;
    const scene = await TerrainScene.load(gl, `/assets/maps/${m.key}/bundle.tsb`);
    for (const r of listing.reference) {
      const t0 = performance.now();
      const got = await scene.renderAt(r.season, r.wave_t, r.hour);
      const ms = performance.now() - t0;
      const ref = await decodePng(`/assets/maps/${m.key}/ref/${r.name}.png`);
      let diff = 0, maxd = 0;
      for (let i = 0; i < m.W * m.H; i++) {
        const d = Math.max(Math.abs(got[i * 4] - ref[i * 4]), Math.abs(got[i * 4 + 1] - ref[i * 4 + 1]),
                           Math.abs(got[i * 4 + 2] - ref[i * 4 + 2]));
        if (d) { diff++; maxd = Math.max(maxd, d); }
      }
      out.push({ map: m.key, ref: r.name, diff, total: m.W * m.H, maxd, ms });
      log.textContent += `${m.key} ${r.name}: 다른 칸 ${diff} (최대 ${maxd}), ${ms.toFixed(0)} ms\n`;
    }
    scene.dispose();
  }
  (window as any).__parity.done = true;
}

main().catch((e) => { (window as any).__parity = { done: true, error: String(e), results: [] }; console.error(e); });
