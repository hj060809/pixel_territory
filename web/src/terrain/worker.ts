// 지형 CPU 단계 워커: 계절 칠하기 + 물결 (화면 스레드를 막지 않게).
// 받는 것  {type:'init', raw: ArrayBuffer(압축 푼 묶음)}  → {type:'progress', text} … {type:'ready', ms}
//          {type:'frame', id, season: number[]|null, waveT: number|null}  → {type:'frame', id, rgba, ice}
// 계절은 바뀌었을 때만 다시 칠하고(한 번에 수십 ms), 물결은 요청마다 입힌다.

import { parseBundle } from '../bundle/tsb.ts';
import { colorNoiseDelta } from '../noise/fields.ts';
import { SeasonPainter, type Painted } from './season.ts';
import { WaterAnimator } from './water.ts';

let painter: SeasonPainter | null = null;
let water: WaterAnimator | null = null;
let painted: Painted | null = null;
let paintedKey = '';

const post = (msg: any, transfer: Transferable[] = []) => (self as any).postMessage(msg, transfer);

self.onmessage = (ev: MessageEvent) => {
  const m = ev.data;
  if (m.type === 'init') {
    const t0 = performance.now();
    const bundle = parseBundle(m.raw);
    post({ type: 'progress', text: '색 노이즈 만드는 중...' });
    const noise = colorNoiseDelta(bundle.meta);
    painter = new SeasonPainter(bundle, noise);
    water = new WaterAnimator(bundle, (text) => post({ type: 'progress', text }));
    painted = null;
    paintedKey = '';
    post({ type: 'ready', ms: performance.now() - t0 });
  } else if (m.type === 'frame' && painter && water) {
    const key = m.season === null ? 'neutral' : m.season.join(',');
    if (!painted || key !== paintedKey) {
      painted = painter.paint(m.season);
      paintedKey = key;
    }
    const { rgb, ice } = painted;
    const base = rgb.slice();
    if (m.waveT !== null) {
      water.apply(base, m.waveT);
      if (m.season !== null) {
        for (let i = 0; i < ice.length; i++) {
          if (ice[i]) { const k = i * 3; base[k] = rgb[k]; base[k + 1] = rgb[k + 1]; base[k + 2] = rgb[k + 2]; }
        }
      }
    }
    const n = ice.length;
    const rgba = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) {
      rgba[i * 4] = base[i * 3]; rgba[i * 4 + 1] = base[i * 3 + 1]; rgba[i * 4 + 2] = base[i * 3 + 2]; rgba[i * 4 + 3] = 255;
    }
    const iceCopy = ice.slice(), matCopy = painted.mat.slice();
    post({ type: 'frame', id: m.id, rgba, ice: iceCopy, mat: matCopy }, [rgba.buffer, iceCopy.buffer, matCopy.buffer]);
  }
};
